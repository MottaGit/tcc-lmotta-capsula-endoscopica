"""Simula o transmissor + enlace de rádio, sem hardware.

Gera um arquivo com exatamente os bytes que o Arduino receptor enviaria ao
PC. Serve para demonstrar e testar o pipeline (empacotamento, RLE, perdas,
duplicações e reordenação, como na Etapa 2 do TCC)::

    python -m capsula.simular --saida demo.bin --quadros 2 --perda 0.03
    python -m capsula.receber --arquivo demo.bin --saida capturas-demo
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path
from typing import List, Optional

from . import imagem
from . import protocolo as p
from .imagem import configurar_saida_utf8


def cena_sintetica(quadro: int = 0, ruido: float = 2.0, semente: int = 0) -> bytes:
    """Imagem 320x240 que lembra uma cena endoscópica: luz central, vinheta e dobras.

    ``ruido`` é o desvio-padrão do ruído do sensor, em níveis de cinza. Com o
    padrão (2.0) o RLE reduz o quadro em ~40%; com 3.0, em ~15% -- a mesma
    faixa observada na Etapa 4 do TCC para cenas homogêneas e ruidosas.
    """
    rng = random.Random(semente + quadro)
    cx, cy = p.LARGURA / 2 + 6 * math.sin(quadro), p.ALTURA / 2
    raio_max = math.hypot(cx, cy)
    pixels = bytearray(p.LARGURA * p.ALTURA)
    for y in range(p.ALTURA):
        for x in range(p.LARGURA):
            r = math.hypot(x - cx, y - cy) / raio_max
            luz = max(0.0, 1.0 - r * 1.15) ** 0.8
            dobra = 0.5 + 0.5 * math.sin(r * 22 - quadro * 0.6 + math.atan2(y - cy, x - cx) * 2)
            valor = 20 + 200 * luz * (0.75 + 0.25 * dobra)
            if ruido:
                valor += rng.gauss(0, ruido)
            pixels[y * p.LARGURA + x] = max(0, min(255, int(valor) // 8 * 8))
    return bytes(pixels)


def ordem_entrelacada(passo: int) -> List[int]:
    """Ordem em que o firmware tende a enviar as linhas (ver docs/protocolo.md)."""
    return [y for inicio in range(passo) for y in range(inicio, p.ALTURA, passo)]


def pacotes_do_quadro(pixels: bytes, quadro_id: int, comprimir: bool, passo: int) -> List[p.Pacote]:
    emp = p.Empacotador(quadro_id)
    ordem = ordem_entrelacada(passo)
    pacotes: List[p.Pacote] = []
    for i, y in enumerate(ordem):
        linha = pixels[y * p.LARGURA:(y + 1) * p.LARGURA]
        pacotes += emp.linha(y, linha, ultima=(i == len(ordem) - 1), comprimir=comprimir)
    return pacotes


def canal(pacotes: List[p.Pacote], perda: float, duplicar: float, reordenar: float,
          rng: random.Random) -> List[p.Pacote]:
    """Aplica perdas, duplicações e trocas de ordem artificiais."""
    saida: List[p.Pacote] = []
    for pacote in pacotes:
        if rng.random() < perda:
            continue
        saida.append(pacote)
        if rng.random() < duplicar:
            saida.append(pacote)
    for i in range(len(saida) - 1):
        if rng.random() < reordenar:
            saida[i], saida[i + 1] = saida[i + 1], saida[i]
    return saida


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Gera um fluxo de pacotes como o do receptor, sem hardware.")
    parser.add_argument("--saida", type=Path, required=True, help="arquivo .bin a gerar")
    parser.add_argument("--quadros", type=int, default=1, help="quantidade de imagens (padrão: 1)")
    parser.add_argument("--imagem", type=Path, help="imagem PGM (P5) para usar no lugar da cena sintética")
    parser.add_argument("--sem-rle", action="store_true", help="desliga a compressão RLE")
    parser.add_argument("--perda", type=float, default=0.0, help="probabilidade de perder cada pacote (ex.: 0.03)")
    parser.add_argument("--duplicar", type=float, default=0.0, help="probabilidade de duplicar um pacote")
    parser.add_argument("--reordenar", type=float, default=0.0, help="probabilidade de trocar dois pacotes vizinhos")
    parser.add_argument("--ruido", type=float, default=2.0,
                        help="ruído do sensor (desvio-padrão em níveis de cinza; padrão: 2.0)")
    parser.add_argument("--passo", type=int, default=4, help="entrelaçamento das linhas (padrão: 4)")
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args(argv)
    configurar_saida_utf8()

    rng = random.Random(args.semente)
    base = None
    if args.imagem:
        largura, altura, px = imagem.ler_pgm(args.imagem)
        base = imagem.redimensionar(largura, altura, px, p.LARGURA, p.ALTURA)

    total = enviados = 0
    with open(args.saida, "wb") as saida:
        saida.write(b"Receptor da capsula pronto\r\n")  # o PC deve ignorar texto solto
        for n in range(args.quadros):
            pixels = base if base is not None else cena_sintetica(n, args.ruido, args.semente)
            pacotes = pacotes_do_quadro(pixels, n & 0xFF, not args.sem_rle, args.passo)
            recebidos = canal(pacotes, args.perda, args.duplicar, args.reordenar, rng)
            total += len(pacotes)
            enviados += len(recebidos)
            for pacote in recebidos:
                saida.write(p.enquadrar(pacote))
    print(f"{args.quadros} quadro(s), {total} pacotes gerados, {enviados} gravados em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
