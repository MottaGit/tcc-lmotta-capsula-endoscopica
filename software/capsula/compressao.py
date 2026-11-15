"""Comparação de algoritmos de compressão sem perdas para a cápsula.

Todos os codificadores por linha são reversíveis (conferido nos testes). Para
cada algoritmo a comparação mede:

* bytes por quadro e redução em relação ao bruto (76.800 bytes);
* pacotes de rádio por quadro, com a mesma regra do firmware: cada linha vai
  codificada só se ficar menor que a bruta, com 2 bytes de cabeçalho de linha
  e 28 bytes de dados por pacote;
* ganho estimado de quadros/s, supondo tempo proporcional ao número de
  pacotes (o rádio é o gargalo).

Uso::

    python -m capsula.compressao                 # duas cenas sintéticas
    python -m capsula.compressao --imagem x.pgm  # inclui uma imagem própria
"""

from __future__ import annotations

import argparse
import math
import zlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import protocolo as p
from . import rice, rle

# ------------------------------------------------------------------ DPCM + RLE


def dpcm(linha: bytes) -> bytes:
    """Diferença entre vizinhos (módulo 256); o primeiro pixel vai como está."""
    anterior = 0
    saida = bytearray(len(linha))
    for i, valor in enumerate(linha):
        saida[i] = (valor - anterior) & 0xFF
        anterior = valor
    return bytes(saida)


def desfazer_dpcm(residuos: bytes) -> bytes:
    valor = 0
    saida = bytearray(len(residuos))
    for i, r in enumerate(residuos):
        valor = (valor + r) & 0xFF
        saida[i] = valor
    return bytes(saida)


# ------------------------------------------ MED (preditor do JPEG-LS) + Rice


def med(a: int, b: int, c: int) -> int:
    """Preditor de mediana do JPEG-LS: a = esquerda, b = acima, c = acima-esquerda."""
    if c >= max(a, b):
        return min(a, b)
    if c <= min(a, b):
        return max(a, b)
    return a + b - c


def med_rice_codificar(linha: bytes, acima: Optional[bytes]) -> bytes:
    acima = acima if acima is not None else bytes(len(linha))
    valores = []
    for i, valor in enumerate(linha):
        a = linha[i - 1] if i else acima[0]
        c = acima[i - 1] if i else acima[0]
        valores.append(rice.zigzag(valor - med(a, acima[i], c)))
    return rice.codificar_valores(valores)


def med_rice_decodificar(dados: bytes, n: int, acima: Optional[bytes]) -> bytes:
    acima = acima if acima is not None else bytes(n)
    valores, _ = rice.decodificar_valores(dados, n)
    saida = bytearray()
    for i, v in enumerate(valores):
        a = saida[i - 1] if i else acima[0]
        c = acima[i - 1] if i else acima[0]
        saida.append(med(a, acima[i], c) + rice.dezigzag(v))
    return bytes(saida)


# ------------------------------------------------------------------ comparação


@dataclass(frozen=True)
class Algoritmo:
    nome: str
    descricao: str
    ram_extra: str
    no_firmware: bool


ALGORITMOS: List[Algoritmo] = [
    Algoritmo("Bruto", "sem compressão", "0", True),
    Algoritmo("RLE", "pares (repetições, valor), usado no TCC", "0", True),
    Algoritmo("DPCM + RLE", "RLE sobre a diferença entre vizinhos", "0", False),
    Algoritmo("DPCM + Rice", "diferença entre vizinhos + Golomb-Rice", "0", True),
    Algoritmo("MED + Rice", "preditor do JPEG-LS (precisa da linha de cima) + Rice", "320 B", False),
    Algoritmo("DEFLATE", "zlib no quadro inteiro, referência de PC", "~32 kB", False),
]


def _bytes_linha(nome: str, linha: bytes, acima: Optional[bytes]) -> int:
    if nome == "Bruto":
        return len(linha)
    if nome == "RLE":
        return rle.tamanho_codificado(linha)
    if nome == "DPCM + RLE":
        return rle.tamanho_codificado(dpcm(linha))
    if nome == "DPCM + Rice":
        return rice.tamanho_linha(linha)
    if nome == "MED + Rice":
        return len(med_rice_codificar(linha, acima))
    raise ValueError(nome)


@dataclass
class Resultado:
    algoritmo: Algoritmo
    bytes_quadro: int
    pacotes_quadro: int

    def reducao(self, bruto: int = p.LARGURA * p.ALTURA) -> float:
        return 1 - self.bytes_quadro / bruto

    def ganho_fps(self, pacotes_bruto: int) -> float:
        return pacotes_bruto / self.pacotes_quadro - 1


def avaliar(pixels: bytes, largura: int = p.LARGURA, altura: int = p.ALTURA) -> Dict[str, Resultado]:
    resultados: Dict[str, Resultado] = {}
    for alg in ALGORITMOS:
        if alg.nome == "DEFLATE":
            total = len(zlib.compress(pixels, 9))
            pacotes = math.ceil(total / p.TAMANHO_PAYLOAD)
        else:
            total = pacotes = 0
            for y in range(altura):
                linha = pixels[y * largura:(y + 1) * largura]
                acima = pixels[(y - 1) * largura:y * largura] if y else None
                usado = min(_bytes_linha(alg.nome, linha, acima), largura)  # codifica só se ficar menor
                total += usado
                pacotes += math.ceil((p.TAMANHO_CAB_LINHA + usado) / p.TAMANHO_PAYLOAD)
        resultados[alg.nome] = Resultado(alg, total, pacotes)
    return resultados


def cenas_de_teste() -> List[Tuple[str, bytes]]:
    """Cenas sintéticas: com áreas uniformes (como as da Etapa 4) e com ruído de sensor."""
    from .simular import cena_sintetica
    return [
        ("áreas uniformes", cena_sintetica(0, ruido=2.0, passo=8)),
        ("ruído de sensor", cena_sintetica(0, ruido=2.5, passo=1)),
    ]


def main(argv: Optional[list] = None) -> int:
    from .imagem import configurar_saida_utf8, ler_pgm, redimensionar

    parser = argparse.ArgumentParser(description="Compara algoritmos de compressão sem perdas.")
    parser.add_argument("--imagem", action="append", default=[], help="imagem PGM (P5) adicional")
    args = parser.parse_args(argv)
    configurar_saida_utf8()

    cenas = cenas_de_teste()
    for caminho in args.imagem:
        w, h, px = ler_pgm(caminho)
        cenas.append((caminho, redimensionar(w, h, px, p.LARGURA, p.ALTURA)))

    for nome, pixels in cenas:
        resultados = avaliar(pixels)
        pacotes_bruto = resultados["Bruto"].pacotes_quadro
        print(f"\nCena: {nome}")
        print("| Algoritmo | Bytes/quadro | Redução | Pacotes/quadro | FPS estimado | RAM extra | No firmware |")
        print("|---|---:|---:|---:|---:|---:|:---:|")
        for r in resultados.values():
            print(f"| {r.algoritmo.nome} | {r.bytes_quadro:,} | {100 * r.reducao():.1f}% | {r.pacotes_quadro:,} | "
                  f"{100 * r.ganho_fps(pacotes_bruto):+.0f}% | {r.algoritmo.ram_extra} | "
                  f"{'sim' if r.algoritmo.no_firmware else '-'} |".replace(",", "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
