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


def ler_png(caminho: str | Path) -> Tuple[int, int, bytes]:
    """Lê um PNG de 8 bits (cinza, RGB, paleta, com ou sem alfa) e devolve em tons de cinza.

    Retorna ``(largura, altura, pixels)``. Transparência é composta sobre branco.
    """
    dados = Path(caminho).read_bytes()
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é um arquivo PNG")
    pos = 8
    idat = bytearray()
    paleta = b""
    largura = altura = tipo = 0
    while pos < len(dados):
        tamanho, nome = struct.unpack(">I4s", dados[pos:pos + 8])
        conteudo = dados[pos + 8:pos + 8 + tamanho]
        pos += 12 + tamanho
        if nome == b"IHDR":
            largura, altura, bits, tipo, _, _, entrelacado = struct.unpack(">IIBBBBB", conteudo)
            if bits != 8 or entrelacado:
                raise ValueError("apenas PNG de 8 bits sem entrelaçamento é suportado")
        elif nome == b"PLTE":
            paleta = conteudo
        elif nome == b"IDAT":
            idat += conteudo
        elif nome == b"IEND":
            break
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipo]
    bruto = zlib.decompress(bytes(idat))
    passo = largura * canais
    anterior = bytearray(passo)
    cinza = bytearray(largura * altura)
    i = 0
    for y in range(altura):
        filtro = bruto[i]
        linha = bytearray(bruto[i + 1:i + 1 + passo])
        i += 1 + passo
        for x in range(passo):
            a = linha[x - canais] if x >= canais else 0
            b = anterior[x]
            c = anterior[x - canais] if x >= canais else 0
            if filtro == 1:
                linha[x] = (linha[x] + a) & 0xFF
            elif filtro == 2:
                linha[x] = (linha[x] + b) & 0xFF
            elif filtro == 3:
                linha[x] = (linha[x] + (a + b) // 2) & 0xFF
            elif filtro == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                linha[x] = (linha[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        anterior = linha
        for x in range(largura):
            px = linha[x * canais:(x + 1) * canais]
            if tipo == 3:
                px = paleta[px[0] * 3:px[0] * 3 + 3]
            if len(px) >= 3:
                valor = (299 * px[0] + 587 * px[1] + 114 * px[2]) // 1000
            else:
                valor = px[0]
            if canais in (2, 4):  # alfa sobre fundo branco
                alfa = px[-1]
                valor = (valor * alfa + 255 * (255 - alfa)) // 255
            cinza[y * largura + x] = valor
    return largura, altura, bytes(cinza)


def recortar(largura: int, pixels: bytes, x0: int, y0: int, x1: int, y1: int) -> bytes:
    """Recorte retangular [x0, x1) x [y0, y1)."""
    return b"".join(pixels[y * largura + x0:y * largura + x1] for y in range(y0, y1))


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
