"""Converte um despejo hexadecimal da câmera (um byte por pixel) em PNG.

Também mostra quais bits do barramento de dados D0..D7 variaram, o que
ajuda a achar fios soltos (um bit sempre 0 ou sempre 1).

    python ferramentas/hex_para_png.py ../experimentos/capturas-iniciais/captura-ov7670-640x480-hex.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capsula.imagem import configurar_saida_utf8, salvar_png  # noqa: E402

DIMENSOES_CONHECIDAS = {640 * 480: (640, 480), 320 * 240: (320, 240), 160 * 120: (160, 120)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entrada", type=Path, help="arquivo de texto com bytes em hexadecimal")
    parser.add_argument("--saida", type=Path, help="PNG de saída (padrão: mesmo nome, extensão .png)")
    parser.add_argument("--largura", type=int)
    parser.add_argument("--altura", type=int)
    args = parser.parse_args()
    configurar_saida_utf8()

    texto = "".join(args.entrada.read_text(encoding="ascii", errors="ignore").split())
    dados = bytes.fromhex(texto)
    if args.largura and args.altura:
        largura, altura = args.largura, args.altura
    elif len(dados) in DIMENSOES_CONHECIDAS:
        largura, altura = DIMENSOES_CONHECIDAS[len(dados)]
    else:
        sys.exit(f"{len(dados)} bytes: informe --largura e --altura")
    dados = dados[: largura * altura]

    ou_total, e_total = 0, 0xFF
    for byte in dados:
        ou_total |= byte
        e_total &= byte
    print(f"{len(dados)} bytes -> {largura}x{altura}")
    for bit in range(8):
        if not ou_total & (1 << bit):
            print(f"  D{bit}: sempre 0  <- verifique este fio")
        elif e_total & (1 << bit):
            print(f"  D{bit}: sempre 1  <- verifique este fio")

    saida = args.saida or args.entrada.with_suffix(".png")
    salvar_png(saida, largura, altura, dados)
    print(f"PNG salvo em {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
