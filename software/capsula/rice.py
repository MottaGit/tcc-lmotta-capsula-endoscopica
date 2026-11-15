"""DPCM + Golomb-Rice: compressão sem perdas mais eficiente que o RLE em cenas com ruído.

1. **DPCM:** cada pixel vira a diferença para o vizinho da esquerda. Em
   imagens naturais as diferenças são pequenas, mesmo quando os valores
   variam (ruído, gradientes), que é onde o RLE falha.
2. **Zigue-zague:** 0, -1, 1, -2, 2… viram 0, 1, 2, 3, 4… (inteiros sem sinal).
3. **Golomb-Rice com parâmetro k:** cada valor ``v`` é escrito como
   ``v >> k`` em unário (uns seguidos de um zero) + os ``k`` bits baixos.
   Valores pequenos ocupam poucos bits. ``k`` é escolhido por linha pela regra
   do LOCO-I/JPEG-LS (menor k com ``N * 2^k >= soma``), em uma única passada.

Formato de uma linha: 3 bits de ``k`` + os códigos, bits do mais
significativo para o menos significativo, completando o último byte com
zeros. Quocientes >= 24 viram 24 uns + o valor literal em 9 bits (escape).
O firmware (``protocolo.cpp``) gera exatamente os mesmos bits.
"""

from __future__ import annotations

from typing import List, Tuple

ESCAPE = 24
K_MAX = 7


def zigzag(diferenca: int) -> int:
    return 2 * diferenca if diferenca >= 0 else -2 * diferenca - 1


def dezigzag(valor: int) -> int:
    return valor >> 1 if valor % 2 == 0 else -((valor + 1) >> 1)


def residuos_dpcm(linha: bytes) -> List[int]:
    anterior = 0
    residuos = []
    for valor in linha:
        residuos.append(zigzag(valor - anterior))
        anterior = valor
    return residuos


def escolher_k(valores: List[int]) -> int:
    soma, n, k = sum(valores), len(valores), 0
    while k < K_MAX and (n << k) < soma:
        k += 1
    return k


def bits_codificados(valores: List[int], k: int) -> int:
    total = 3
    for v in valores:
        q = v >> k
        total += ESCAPE + 9 if q >= ESCAPE else q + 1 + k
    return total


class _Escritor:
    def __init__(self) -> None:
        self.saida = bytearray()
        self.acc = 0
        self.n = 0

    def bits(self, valor: int, quantidade: int) -> None:
        for i in range(quantidade - 1, -1, -1):
            self.acc = (self.acc << 1) | ((valor >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.saida.append(self.acc)
                self.acc = self.n = 0

    def fechar(self) -> bytes:
        if self.n:
            self.saida.append(self.acc << (8 - self.n))
            self.acc = self.n = 0
        return bytes(self.saida)


def codificar_valores(valores: List[int]) -> bytes:
    k = escolher_k(valores)
    w = _Escritor()
    w.bits(k, 3)
    for v in valores:
        q = v >> k
        if q >= ESCAPE:
            w.bits((1 << ESCAPE) - 1, ESCAPE)
            w.bits(v, 9)
        else:
            w.bits((1 << q) - 1, q)
            w.bits(0, 1)
            w.bits(v & ((1 << k) - 1), k)
    return w.fechar()


def decodificar_valores(dados: bytes, n: int) -> Tuple[List[int], int]:
    """Decodifica até ``n`` valores. Para antes se os dados acabarem (pacote perdido).

    Retorna ``(valores, bytes_consumidos)``.
    """
    total_bits = len(dados) * 8
    pos = 0

    def ler(quantidade: int) -> int:
        nonlocal pos
        if pos + quantidade > total_bits:
            raise EOFError
        valor = 0
        for _ in range(quantidade):
            valor = (valor << 1) | ((dados[pos >> 3] >> (7 - (pos & 7))) & 1)
            pos += 1
        return valor

    valores: List[int] = []
    try:
        k = ler(3)
        while len(valores) < n:
            inicio = pos
            try:
                q = 0
                while q < ESCAPE and ler(1) == 1:
                    q += 1
                valores.append(ler(9) if q == ESCAPE else (q << k) | ler(k))
            except EOFError:
                pos = inicio
                break
    except EOFError:
        pass
    return valores, (pos + 7) // 8


def codificar_linha(linha: bytes) -> bytes:
    return codificar_valores(residuos_dpcm(linha))


def tamanho_linha(linha: bytes) -> int:
    valores = residuos_dpcm(linha)
    return (bits_codificados(valores, escolher_k(valores)) + 7) // 8


def decodificar_linha(dados: bytes, n: int) -> Tuple[bytes, int]:
    """Pixels recuperados (podem ser menos que ``n``) e bytes consumidos."""
    valores, usados = decodificar_valores(dados, n)
    anterior = 0
    pixels = bytearray()
    for v in valores:
        anterior = (anterior + dezigzag(v)) & 0xFF
        pixels.append(anterior)
    return bytes(pixels), usados
