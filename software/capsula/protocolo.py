"""Protocolo lógico de transmissão de quadros da cápsula.

Este módulo é a referência do protocolo: o firmware do transmissor
(``firmware/transmissor_capsula/protocolo.cpp``) gera exatamente os mesmos
bytes. A especificação completa está em ``docs/protocolo.md``.

Pacote (32 bytes = limite de payload do nRF24L01+)::

    byte 0   : [SOF|EOF|SOL|EOL] (4 bits altos) + seq[11:8] (4 bits baixos)
    byte 1   : seq[7:0]                número de sequência de 12 bits
    byte 2   : id do quadro            0..255, incrementa a cada imagem
    byte 3   : CRC-8                   sobre os bytes 0..2 e 4..31
    byte 4.. : payload (28 bytes)

O primeiro pacote de cada linha (SOL) começa com 2 bytes de cabeçalho de
linha: ``[número da linha, codificação]``. Cada linha começa em um pacote
novo, de modo que a perda de um pacote afeta no máximo uma linha.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional

from . import rice, rle

# --- Dimensões e formato -----------------------------------------------------

LARGURA = 320          # QVGA, apenas luminância (Y) -> 1 byte por pixel
ALTURA = 240

TAMANHO_PACOTE = 32    # payload máximo do nRF24L01+
TAMANHO_CABECALHO = 4
TAMANHO_PAYLOAD = TAMANHO_PACOTE - TAMANHO_CABECALHO   # 28
TAMANHO_CAB_LINHA = 2  # [linha, codificação] no primeiro pacote de cada linha

# --- Flags (4 bits altos do byte 0) -------------------------------------------

SOF = 0x80  # Start Of Frame: primeiro pacote da imagem
EOF = 0x40  # End Of Frame:   último pacote da imagem
SOL = 0x20  # Start Of Line:  primeiro pacote de uma linha
EOL = 0x10  # End Of Line:    último pacote de uma linha

# --- Codificação da linha -----------------------------------------------------

COD_BRUTO = 0  # 320 bytes de luminância
COD_RLE = 1    # pares (repetições, valor)
COD_RICE = 2   # DPCM + Golomb-Rice (ver rice.py)
# A codificação é escolhida por linha: a menor entre as permitidas pelo modo,
# e só se for menor que a bruta. Logo uma linha nunca passa de 12 pacotes.
MODOS = ("bruto", "rle", "rice")  # "rice" = escolhe entre bruto, RLE e Rice

SEQ_MAX = 0x0FFF  # 12 bits

# --- Enquadramento na serial (receptor -> PC) ---------------------------------

SYNC = b"\xA5\x5A"  # cada pacote vai na serial como SYNC + 32 bytes

# Etapa 1 (dados brutos, sem pacotes): marcador + 76.800 bytes por quadro
MARCADOR_QUADRO_BRUTO = b"\x00\xFF\x00\xFFQVGA"


class ErroPacote(ValueError):
    """Pacote com tamanho inválido ou CRC incorreto."""


def crc8(dados: bytes, crc: int = 0) -> int:
    """CRC-8 com polinômio 0x07 (CRC-8/SMBUS), valor inicial 0."""
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _crc_pacote(bruto: bytes) -> int:
    return crc8(bruto[4:TAMANHO_PACOTE], crc8(bruto[0:3]))


@dataclass(frozen=True)
class Pacote:
    flags: int
    seq: int
    quadro: int
    payload: bytes

    def __post_init__(self) -> None:
        if len(self.payload) != TAMANHO_PAYLOAD:
            raise ErroPacote(f"payload deve ter {TAMANHO_PAYLOAD} bytes")
        if not 0 <= self.seq <= SEQ_MAX:
            raise ErroPacote("seq fora de 12 bits")

    def to_bytes(self) -> bytes:
        cab = bytes([(self.flags & 0xF0) | (self.seq >> 8), self.seq & 0xFF, self.quadro & 0xFF, 0])
        bruto = bytearray(cab + self.payload)
        bruto[3] = _crc_pacote(bruto)
        return bytes(bruto)

    @classmethod
    def from_bytes(cls, bruto: bytes) -> "Pacote":
        if len(bruto) != TAMANHO_PACOTE:
            raise ErroPacote(f"pacote deve ter {TAMANHO_PACOTE} bytes")
        if _crc_pacote(bruto) != bruto[3]:
            raise ErroPacote("CRC-8 inválido")
        return cls(
            flags=bruto[0] & 0xF0,
            seq=((bruto[0] & 0x0F) << 8) | bruto[1],
            quadro=bruto[2],
            payload=bytes(bruto[4:]),
        )

    def tem(self, flag: int) -> bool:
        return bool(self.flags & flag)


def escolher_codificacao(pixels: bytes, modo: str) -> tuple:
    """``(codificação, bytes)`` da menor representação permitida pelo modo."""
    melhor = (COD_BRUTO, LARGURA)
    if modo in ("rle", "rice"):
        tamanho = rle.tamanho_codificado(pixels)
        if tamanho < melhor[1]:
            melhor = (COD_RLE, tamanho)
    if modo == "rice":
        tamanho = rice.tamanho_linha(pixels)
        if tamanho < melhor[1]:
            melhor = (COD_RICE, tamanho)
    return melhor


class Empacotador:
    """Divide linhas de imagem em pacotes (espelha o firmware do transmissor)."""

    def __init__(self, quadro: int) -> None:
        self.quadro = quadro & 0xFF
        self.seq = 0
        self._payload = bytearray()
        self._flags = 0
        self._saida: List[Pacote] = []

    def linha(self, y: int, pixels: bytes, ultima: bool = False, modo: str = "rle") -> List[Pacote]:
        """Gera os pacotes de uma linha. ``ultima`` marca EOF no último pacote."""
        if len(pixels) != LARGURA:
            raise ValueError(f"a linha deve ter {LARGURA} pixels")
        if modo not in MODOS:
            raise ValueError(f"modo deve ser um de {MODOS}")
        self._saida = []
        codificacao, tamanho = escolher_codificacao(pixels, modo)

        self._flags = SOL
        self._payload = bytearray([y, codificacao])
        if codificacao == COD_RLE:
            codificado = rle.codificar(pixels)
            for i in range(0, len(codificado), 2):
                if len(self._payload) > TAMANHO_PAYLOAD - 2:  # pares nunca são divididos
                    self._enviar()
                self._payload += codificado[i:i + 2]
        else:
            dados = rice.codificar_linha(pixels) if codificacao == COD_RICE else pixels
            for valor in dados:
                if len(self._payload) == TAMANHO_PAYLOAD:
                    self._enviar()
                self._payload.append(valor)
        self._flags |= EOL | (EOF if ultima else 0)
        self._enviar()
        return self._saida

    def _enviar(self) -> None:
        if self.seq > SEQ_MAX:
            raise OverflowError("quadro excedeu 4096 pacotes")
        flags = self._flags | (SOF if self.seq == 0 else 0)
        payload = bytes(self._payload) + bytes(TAMANHO_PAYLOAD - len(self._payload))
        self._saida.append(Pacote(flags, self.seq, self.quadro, payload))
        self.seq += 1
        self._payload = bytearray()
        self._flags = 0


class LeitorSerial:
    """Recupera pacotes de um fluxo de bytes (``SYNC`` + 32 bytes).

    Bytes que não formam um pacote válido (texto de depuração, ruído, um
    pacote cortado) são descartados e a sincronização é retomada no próximo
    ``SYNC``.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.pacotes_validos = 0
        self.erros_crc = 0
        self.bytes_descartados = 0

    def alimentar(self, dados: bytes) -> Iterator[Pacote]:
        self._buf += dados
        while True:
            inicio = self._buf.find(SYNC)
            if inicio < 0:
                # guarda o último byte: pode ser o início de um SYNC partido
                manter = 1 if self._buf[-1:] == SYNC[:1] else 0
                self.bytes_descartados += len(self._buf) - manter
                del self._buf[: len(self._buf) - manter]
                return
            if inicio:
                self.bytes_descartados += inicio
                del self._buf[:inicio]
            fim = len(SYNC) + TAMANHO_PACOTE
            if len(self._buf) < fim:
                return
            try:
                pacote = Pacote.from_bytes(bytes(self._buf[len(SYNC):fim]))
            except ErroPacote:
                self.erros_crc += 1
                self.bytes_descartados += 1
                del self._buf[:1]  # procura o próximo SYNC
                continue
            del self._buf[:fim]
            self.pacotes_validos += 1
            yield pacote


class LeitorQuadrosBrutos:
    """Etapa 1: recupera quadros brutos (marcador + 76.800 bytes) de um fluxo serial."""

    def __init__(self, largura: int = LARGURA, altura: int = ALTURA) -> None:
        self._buf = bytearray()
        self._tamanho = largura * altura
        self.bytes_descartados = 0

    def alimentar(self, dados: bytes) -> Iterator[bytes]:
        self._buf += dados
        marcador = MARCADOR_QUADRO_BRUTO
        while True:
            inicio = self._buf.find(marcador)
            if inicio < 0:
                manter = min(len(self._buf), len(marcador) - 1)
                self.bytes_descartados += len(self._buf) - manter
                del self._buf[: len(self._buf) - manter]
                return
            self.bytes_descartados += inicio
            del self._buf[:inicio]
            fim = len(marcador) + self._tamanho
            if len(self._buf) < fim:
                return
            quadro = bytes(self._buf[len(marcador):fim])
            del self._buf[:fim]
            yield quadro


def enquadrar(pacote: Pacote) -> bytes:
    """Bytes que o receptor envia ao PC para um pacote."""
    return SYNC + pacote.to_bytes()


def ler_cabecalho_linha(pacote: Pacote) -> Optional[tuple]:
    """``(linha, codificação)`` de um pacote SOL, ou ``None``."""
    if not pacote.tem(SOL):
        return None
    return pacote.payload[0], pacote.payload[1]
