"""Leitura e escrita de imagens em tons de cinza sem dependências externas.

PNG (escrita) e PGM binário/P5 (leitura e escrita) bastam para o projeto:
o PNG é o formato final dos quadros e o PGM é a forma mais simples de
fornecer uma imagem própria ao simulador.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path
from typing import Tuple


def salvar_png(caminho: str | Path, largura: int, altura: int, pixels: bytes) -> None:
    if len(pixels) != largura * altura:
        raise ValueError("quantidade de pixels não confere com as dimensões")
    linhas = b"".join(b"\x00" + pixels[y * largura:(y + 1) * largura] for y in range(altura))

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0)  # 8 bits, tons de cinza
    Path(caminho).write_bytes(
        b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", zlib.compress(linhas, 9)) + bloco(b"IEND", b"")
    )


def ler_pgm(caminho: str | Path) -> Tuple[int, int, bytes]:
    """Lê um PGM binário (P5) de 8 bits. Retorna ``(largura, altura, pixels)``."""
    dados = Path(caminho).read_bytes()
    campos = []
    pos = 0
    while len(campos) < 4:
        while dados[pos:pos + 1].isspace():
            pos += 1
        if dados[pos:pos + 1] == b"#":
            pos = dados.index(b"\n", pos) + 1
            continue
        fim = pos
        while not dados[fim:fim + 1].isspace():
            fim += 1
        campos.append(dados[pos:fim])
        pos = fim
    if campos[0] != b"P5" or int(campos[3]) > 255:
        raise ValueError("apenas PGM binário (P5) de 8 bits é suportado")
    largura, altura = int(campos[1]), int(campos[2])
    pos += 1  # um único espaço separa o cabeçalho dos pixels
    return largura, altura, dados[pos:pos + largura * altura]


def redimensionar(largura: int, altura: int, pixels: bytes, nova_l: int, nova_a: int) -> bytes:
    """Redimensionamento por vizinho mais próximo."""
    saida = bytearray(nova_l * nova_a)
    for y in range(nova_a):
        origem = (y * altura // nova_a) * largura
        for x in range(nova_l):
            saida[y * nova_l + x] = pixels[origem + x * largura // nova_l]
    return bytes(saida)


def configurar_saida_utf8() -> None:
    """Evita acentos corrompidos quando a saída é redirecionada no Windows."""
    if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
