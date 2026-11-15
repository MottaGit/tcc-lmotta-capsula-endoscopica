"""Remontagem dos quadros a partir dos pacotes recebidos.

Regras (Capítulo 4 da monografia):

* pacotes são ordenados pelo número de sequência, então chegar fora de
  ordem não é problema;
* pacotes duplicados são ignorados;
* pacotes perdidos deixam a linha (ou o trecho da linha) marcada como
  faltante, preenchida com preto ou com a linha do quadro anterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import protocolo as p
from . import rle

PACOTES_MAX_POR_LINHA = -(-(p.TAMANHO_CAB_LINHA + p.LARGURA) // p.TAMANHO_PAYLOAD)  # 12


@dataclass
class QuadroRemontado:
    quadro_id: int
    pixels: bytearray
    pacotes_esperados: int
    pacotes_recebidos: int
    duplicados: int
    linhas_completas: int
    linhas_parciais: int
    linhas_faltantes: int
    linhas_rle: int
    pixels_recebidos: int     # pixels que puderam ser reconstruídos
    bytes_dados: int          # bytes de imagem efetivamente transmitidos (após RLE)
    fim_recebido: bool        # o pacote EOF chegou

    @property
    def taxa_sucesso(self) -> float:
        return self.pacotes_recebidos / self.pacotes_esperados if self.pacotes_esperados else 0.0

    @property
    def reducao_rle(self) -> float:
        """Redução de tamanho em relação aos mesmos pixels sem compressão."""
        return 1 - self.bytes_dados / self.pixels_recebidos if self.pixels_recebidos else 0.0


@dataclass
class _QuadroEmMontagem:
    quadro_id: int
    pacotes: Dict[int, p.Pacote] = field(default_factory=dict)
    duplicados: int = 0
    seq_fim: Optional[int] = None


class Remontador:
    def __init__(self, largura: int = p.LARGURA, altura: int = p.ALTURA, faltantes: str = "preto") -> None:
        if faltantes not in ("preto", "anterior"):
            raise ValueError("faltantes deve ser 'preto' ou 'anterior'")
        self.largura = largura
        self.altura = altura
        self.faltantes = faltantes
        self._atual: Optional[_QuadroEmMontagem] = None
        self._ultimo_id: Optional[int] = None
        self._anterior = bytearray(largura * altura)
        self.pacotes_atrasados = 0

    # ------------------------------------------------------------------ entrada
    def adicionar(self, pacote: p.Pacote) -> List[QuadroRemontado]:
        """Processa um pacote; devolve os quadros que ficaram prontos."""
        prontos: List[QuadroRemontado] = []
        atual = self._atual

        novo_quadro = atual is None or pacote.quadro != atual.quadro_id
        # mesmo id, mas um novo SOF depois de já termos o seq 0: o id deu a volta (256 quadros)
        if not novo_quadro and pacote.tem(p.SOF) and 0 in atual.pacotes and pacote.seq == 0 \
                and pacote.payload != atual.pacotes[0].payload:
            novo_quadro = True

        if novo_quadro:
            if atual is None and pacote.quadro == self._ultimo_id and not pacote.tem(p.SOF):
                self.pacotes_atrasados += 1  # sobra de um quadro já entregue
                return prontos
            if atual is not None:
                prontos.append(self._fechar())
            self._atual = atual = _QuadroEmMontagem(pacote.quadro)

        if pacote.seq in atual.pacotes:
            atual.duplicados += 1
        else:
            atual.pacotes[pacote.seq] = pacote
        if pacote.tem(p.EOF):
            atual.seq_fim = pacote.seq
        if atual.seq_fim is not None and len(atual.pacotes) == atual.seq_fim + 1:
            prontos.append(self._fechar())
        return prontos

    def finalizar(self) -> Optional[QuadroRemontado]:
        """Entrega o quadro em montagem (mesmo incompleto), se houver."""
        return self._fechar() if self._atual is not None else None

    # ------------------------------------------------------------------ montagem
    def _fechar(self) -> QuadroRemontado:
        atual = self._atual
        assert atual is not None
        self._atual = None
        self._ultimo_id = atual.quadro_id

        pixels = bytearray(self._anterior) if self.faltantes == "anterior" else bytearray(self.largura * self.altura)
        completas = parciais = rle_linhas = bytes_dados = pixels_recebidos = 0
        vistas = set()

        for seq in sorted(atual.pacotes):
            pacote = atual.pacotes[seq]
            cab = p.ler_cabecalho_linha(pacote)
            if cab is None:
                continue
            y, codificacao = cab
            if y >= self.altura or y in vistas:
                continue
            vistas.add(y)
            pedacos = self._pacotes_da_linha(atual.pacotes, seq)
            if codificacao == p.COD_RLE:
                linha, conhecidos, usados = self._decodificar_rle(pedacos)
                rle_linhas += 1
            else:
                linha, conhecidos, usados = self._decodificar_bruto(pedacos)
            bytes_dados += usados
            pixels_recebidos += sum(conhecidos)
            inicio = y * self.largura
            for x in range(self.largura):
                if conhecidos[x]:
                    pixels[inicio + x] = linha[x]
            if all(conhecidos):
                completas += 1
            else:
                parciais += 1

        if atual.seq_fim is not None:
            esperados = atual.seq_fim + 1
        else:
            esperados = max(atual.pacotes) + 1 if atual.pacotes else 0
        self._anterior = bytearray(pixels)
        return QuadroRemontado(
            quadro_id=atual.quadro_id,
            pixels=pixels,
            pacotes_esperados=max(esperados, len(atual.pacotes)),
            pacotes_recebidos=len(atual.pacotes),
            duplicados=atual.duplicados,
            linhas_completas=completas,
            linhas_parciais=parciais,
            linhas_faltantes=self.altura - completas - parciais,
            linhas_rle=rle_linhas,
            pixels_recebidos=pixels_recebidos,
            bytes_dados=bytes_dados,
            fim_recebido=atual.seq_fim is not None,
        )

    @staticmethod
    def _pacotes_da_linha(pacotes: Dict[int, p.Pacote], seq_inicio: int) -> List[Optional[p.Pacote]]:
        """Pacotes da linha que começa em ``seq_inicio``; ``None`` marca um pacote perdido."""
        resultado: List[Optional[p.Pacote]] = [pacotes[seq_inicio]]
        if pacotes[seq_inicio].tem(p.EOL):
            return resultado
        for seq in range(seq_inicio + 1, seq_inicio + PACOTES_MAX_POR_LINHA):
            pacote = pacotes.get(seq)
            if pacote is not None and pacote.tem(p.SOL):
                break  # a próxima linha começou: o EOL desta se perdeu
            resultado.append(pacote)
            if pacote is not None and pacote.tem(p.EOL):
                break
        # remove perdas no final: não sabemos se esses pacotes eram desta linha
        while resultado and resultado[-1] is None:
            resultado.pop()
        return resultado

    def _decodificar_bruto(self, pedacos: List[Optional[p.Pacote]]):
        linha = bytearray(self.largura)
        conhecidos = [False] * self.largura
        usados = 0
        for k, pacote in enumerate(pedacos):
            if pacote is None:
                continue
            dados = pacote.payload[p.TAMANHO_CAB_LINHA:] if k == 0 else pacote.payload
            deslocamento = 0 if k == 0 else (p.TAMANHO_PAYLOAD - p.TAMANHO_CAB_LINHA) + (k - 1) * p.TAMANHO_PAYLOAD
            n = max(0, min(len(dados), self.largura - deslocamento))
            linha[deslocamento:deslocamento + n] = dados[:n]
            for x in range(deslocamento, deslocamento + n):
                conhecidos[x] = True
            usados += n
        return linha, conhecidos, usados

    def _decodificar_rle(self, pedacos: List[Optional[p.Pacote]]):
        linha = bytearray(self.largura)
        conhecidos = [False] * self.largura
        decodificado = bytearray()
        usados = 0
        for k, pacote in enumerate(pedacos):
            if pacote is None:
                break  # sem o pacote anterior não dá para saber a posição dos próximos
            dados = pacote.payload[p.TAMANHO_CAB_LINHA:] if k == 0 else pacote.payload
            trecho = rle.decodificar(dados)
            usados += 2 * self._pares_validos(dados)
            decodificado += trecho
            if len(decodificado) >= self.largura:
                break
        n = min(len(decodificado), self.largura)
        linha[:n] = decodificado[:n]
        for x in range(n):
            conhecidos[x] = True
        return linha, conhecidos, usados

    @staticmethod
    def _pares_validos(dados: bytes) -> int:
        pares = 0
        for i in range(0, len(dados) - 1, 2):
            if dados[i] == 0:
                break
            pares += 1
        return pares
