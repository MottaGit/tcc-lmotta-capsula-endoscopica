"""Run-Length Encoding (RLE) usado na Etapa 4 do TCC.

Formato: sequência de pares ``(repetições, valor)``, com ``repetições`` de
1 a 255. Um par com ``repetições == 0`` é preenchimento e encerra a leitura
do pacote atual.
"""

from __future__ import annotations

MAX_REPETICOES = 255


def codificar(pixels: bytes) -> bytes:
    saida = bytearray()
    i = 0
    n = len(pixels)
    while i < n:
        valor = pixels[i]
        repeticoes = 1
        while i + repeticoes < n and repeticoes < MAX_REPETICOES and pixels[i + repeticoes] == valor:
            repeticoes += 1
        saida += bytes((repeticoes, valor))
        i += repeticoes
    return bytes(saida)


def tamanho_codificado(pixels: bytes) -> int:
    """Tamanho em bytes que ``codificar`` produziria (sem alocar)."""
    tamanho = 0
    i = 0
    n = len(pixels)
    while i < n:
        valor = pixels[i]
        repeticoes = 1
        while i + repeticoes < n and repeticoes < MAX_REPETICOES and pixels[i + repeticoes] == valor:
            repeticoes += 1
        tamanho += 2
        i += repeticoes
    return tamanho


def decodificar(dados: bytes, limite: int | None = None) -> bytes:
    """Decodifica pares até o fim, até um par de preenchimento ou até ``limite`` bytes."""
    saida = bytearray()
    for i in range(0, len(dados) - 1, 2):
        repeticoes, valor = dados[i], dados[i + 1]
        if repeticoes == 0:
            break
        saida += bytes((valor,)) * repeticoes
        if limite is not None and len(saida) >= limite:
            return bytes(saida[:limite])
    return bytes(saida)
