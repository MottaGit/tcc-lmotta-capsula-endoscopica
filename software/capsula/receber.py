"""Recebe pacotes do receptor (ou de um arquivo gravado) e salva os quadros em PNG.

Exemplos::

    # ao vivo, lendo o Arduino Uno receptor
    python -m capsula.receber --porta COM5

    # offline, a partir de uma gravação (ou de uma saída do simulador)
    python -m capsula.receber --arquivo demo.bin

    # etapa 1: quadros brutos direto do Mega
    python -m capsula.receber --porta COM3 --bruto
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import BinaryIO, Iterable, Optional, Tuple

from . import imagem
from . import protocolo as p
from .imagem import configurar_saida_utf8
from .remontagem import QuadroRemontado, Remontador


def _fonte_serial(porta: str, baud: int, gravar: Optional[BinaryIO]) -> Iterable[bytes]:
    try:
        import serial  # pyserial
    except ImportError:  # pragma: no cover - depende do ambiente
        sys.exit("pyserial não instalado. Rode: pip install -r requirements.txt")
    with serial.Serial(porta, baud, timeout=0.1) as conexao:
        conexao.reset_input_buffer()
        print(f"Ouvindo {porta} a {baud} baud. Ctrl+C para parar.")
        while True:
            dados = conexao.read(4096)
            if gravar is not None and dados:
                gravar.write(dados)
            yield dados


def _fonte_arquivo(caminho: Path) -> Iterable[bytes]:
    with open(caminho, "rb") as arquivo:
        while True:
            dados = arquivo.read(4096)
            if not dados:
                return
            yield dados


def _resumo(q: QuadroRemontado, destino: Path, intervalo: Optional[float]) -> str:
    texto = (
        f"Quadro {q.quadro_id:3d}: {q.pacotes_recebidos}/{q.pacotes_esperados} pacotes "
        f"({100 * q.taxa_sucesso:.1f}%), linhas {q.linhas_completas} completas / "
        f"{q.linhas_parciais} parciais / {q.linhas_faltantes} faltantes"
    )
    if q.linhas_rle or q.linhas_rice:
        texto += f", RLE/Rice em {q.linhas_rle}/{q.linhas_rice} linhas ({100 * q.reducao:.1f}% menor)"
    if q.duplicados:
        texto += f", {q.duplicados} duplicados"
    if intervalo:
        texto += f", {intervalo:.2f} s ({1 / intervalo:.2f} FPS)"
    return texto + f" -> {destino.name}"


CAMPOS_CSV = ["quadro", "id", "pacotes_recebidos", "pacotes_esperados", "taxa_sucesso", "duplicados",
              "linhas_completas", "linhas_parciais", "linhas_faltantes", "linhas_rle", "linhas_rice",
              "bytes_dados", "reducao", "intervalo_s"]


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Remonta e salva os quadros enviados pela cápsula.")
    fonte = parser.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--porta", help="porta serial do receptor (ex.: COM5 ou /dev/ttyACM0)")
    fonte.add_argument("--arquivo", type=Path, help="arquivo .bin gravado ou gerado pelo simulador")
    parser.add_argument("--bruto", action="store_true",
                        help="etapa 1: quadros brutos (marcador + 76.800 bytes), sem pacotes")
    parser.add_argument("--baud", type=int, default=1_000_000, help="velocidade da serial (padrão: 1000000)")
    parser.add_argument("--saida", type=Path, default=Path("capturas"), help="pasta dos PNG (padrão: capturas)")
    parser.add_argument("--csv", type=Path, help="grava as métricas de cada quadro neste arquivo CSV")
    parser.add_argument("--faltantes", choices=("preto", "anterior"), default="preto",
                        help="como preencher linhas perdidas (padrão: preto, para depuração)")
    parser.add_argument("--gravar", type=Path, help="grava os bytes brutos da serial neste arquivo")
    parser.add_argument("--quadros", type=int, default=0, help="para depois de N quadros (0 = sem limite)")
    parser.add_argument("--timeout-quadro", type=float, default=3.0,
                        help="segundos sem pacotes para entregar um quadro incompleto (padrão: 3)")
    args = parser.parse_args(argv)
    configurar_saida_utf8()

    args.saida.mkdir(parents=True, exist_ok=True)
    leitor = p.LeitorSerial()
    leitor_bruto = p.LeitorQuadrosBrutos()
    remontador = Remontador(faltantes=args.faltantes)
    gravacao = open(args.gravar, "wb") if args.gravar and args.porta else None
    planilha = open(args.csv, "w", newline="", encoding="utf-8") if args.csv else None
    escritor_csv = csv.writer(planilha) if planilha else None
    if escritor_csv:
        escritor_csv.writerow(CAMPOS_CSV)
    fonte = _fonte_serial(args.porta, args.baud, gravacao) if args.porta else _fonte_arquivo(args.arquivo)

    entregues = 0
    ultimo_pacote = ultimo_quadro = time.monotonic()
    soma_sucesso = 0.0

    def proximo_destino() -> Tuple[Path, Optional[float]]:
        nonlocal entregues, ultimo_quadro
        entregues += 1
        agora = time.monotonic()
        intervalo = agora - ultimo_quadro if args.porta and entregues > 1 else None
        ultimo_quadro = agora
        return args.saida / f"quadro_{entregues:04d}.png", intervalo

    def entregar(q: QuadroRemontado) -> None:
        nonlocal soma_sucesso
        destino, intervalo = proximo_destino()
        imagem.salvar_png(destino, p.LARGURA, p.ALTURA, bytes(q.pixels))
        soma_sucesso += q.taxa_sucesso
        print(_resumo(q, destino, intervalo))
        if escritor_csv:
            escritor_csv.writerow([entregues, q.quadro_id, q.pacotes_recebidos, q.pacotes_esperados,
                                   f"{q.taxa_sucesso:.4f}", q.duplicados, q.linhas_completas, q.linhas_parciais,
                                   q.linhas_faltantes, q.linhas_rle, q.linhas_rice, q.bytes_dados,
                                   f"{q.reducao:.4f}", f"{intervalo:.3f}" if intervalo else ""])

    def entregar_bruto(pixels: bytes) -> None:
        destino, intervalo = proximo_destino()
        imagem.salvar_png(destino, p.LARGURA, p.ALTURA, pixels)
        tempo = f", {intervalo:.2f} s/quadro" if intervalo else ""
        print(f"Quadro bruto {entregues}: {len(pixels)} bytes{tempo} -> {destino.name}")

    try:
        for dados in fonte:
            agora = time.monotonic()
            if args.bruto:
                for pixels in leitor_bruto.alimentar(dados):
                    entregar_bruto(pixels)
            else:
                for pacote in leitor.alimentar(dados):
                    ultimo_pacote = agora
                    for quadro in remontador.adicionar(pacote):
                        entregar(quadro)
                if args.porta and agora - ultimo_pacote > args.timeout_quadro:
                    pendente = remontador.finalizar()
                    if pendente is not None:
                        entregar(pendente)
                    ultimo_pacote = agora
            if args.quadros and entregues >= args.quadros:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if gravacao is not None:
            gravacao.close()

    if not args.bruto and not (args.quadros and entregues >= args.quadros):
        pendente = remontador.finalizar()
        if pendente is not None:
            entregar(pendente)
    if planilha:
        planilha.close()

    if args.bruto:
        print(f"\n{entregues} quadro(s) brutos salvos em {args.saida}/ | bytes descartados: "
              f"{leitor_bruto.bytes_descartados}")
    else:
        print(
            f"\n{entregues} quadro(s) salvos em {args.saida}/ | pacotes válidos: {leitor.pacotes_validos}, "
            f"erros de CRC: {leitor.erros_crc}, bytes descartados: {leitor.bytes_descartados}"
            + (f", sucesso médio: {100 * soma_sucesso / entregues:.1f}%" if entregues else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
