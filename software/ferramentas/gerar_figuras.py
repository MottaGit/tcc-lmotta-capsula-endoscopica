"""Gera as figuras do README em docs/imagens/ (SVG e PNG, sem dependências).

    python ferramentas/gerar_figuras.py

Os resultados de bancada (etapas 3 e 4) vêm da monografia; as imagens das
etapas 1 e 2 vêm das figuras reais da monografia e do simulador; a comparação
de compressão é calculada na hora por capsula.compressao.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "software"))

from capsula import compressao, imagem  # noqa: E402
from capsula import protocolo as p  # noqa: E402
from capsula.remontagem import Remontador  # noqa: E402
from capsula.simular import canal, pacotes_do_quadro  # noqa: E402

SAIDA = RAIZ / "docs" / "imagens"
FIGURAS = RAIZ / "monografia" / "figuras"

# Resultados medidos em bancada (monografia, Capítulo 4)
ENTREGA = [("1 m", 97.4), ("3 m", 94.1)]
BYTES_SEM, BYTES_RLE = 76800, 50400
GANHO_FPS, ENTREGA_SEM, ENTREGA_RLE = 50.8, 97.4, 96.8

AZUL, LARANJA, VERDE, CINZA, ESCURO, SUAVE = "#2563eb", "#f59e0b", "#16a34a", "#9ca3af", "#111827", "#6b7280"
FONTE = "Segoe UI, Helvetica, Arial, sans-serif"


# ----------------------------------------------------------------- SVG básico

class Svg:
    def __init__(self, largura: int, altura: int, titulo: str, subtitulo: str = "") -> None:
        self.l, self.a = largura, altura
        self.itens: List[str] = [
            f'<rect x="0.5" y="0.5" width="{largura - 1}" height="{altura - 1}" rx="10" fill="#ffffff" stroke="#e5e7eb"/>',
        ]
        self.texto(24, 34, titulo, 18, ESCURO, peso="600")
        if subtitulo:
            self.texto(24, 56, subtitulo, 13, SUAVE)

    def texto(self, x: float, y: float, conteudo: str, tamanho: int = 13, cor: str = ESCURO,
              ancora: str = "start", peso: str = "400") -> None:
        conteudo = conteudo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.itens.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{tamanho}" fill="{cor}" '
                          f'text-anchor="{ancora}" font-weight="{peso}">{conteudo}</text>')

    def ret(self, x: float, y: float, w: float, h: float, cor: str, borda: str = "none", rx: float = 3) -> None:
        self.itens.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{h:.1f}" '
                          f'rx="{rx}" fill="{cor}" stroke="{borda}"/>')

    def linha(self, x1: float, y1: float, x2: float, y2: float, cor: str = "#d1d5db", largura: float = 1) -> None:
        self.itens.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke="{cor}" stroke-width="{largura}"/>')

    def salvar(self, nome: str) -> None:
        conteudo = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.l}" height="{self.a}" '
                    f'viewBox="0 0 {self.l} {self.a}" font-family="{FONTE}">\n  '
                    + "\n  ".join(self.itens) + "\n</svg>\n")
        (SAIDA / nome).write_text(conteudo, encoding="utf-8")
        print("  ", nome)


def barras_horizontais(svg: Svg, x0: float, y0: float, largura: float, itens: Sequence[Tuple[str, float, str, str]],
                       maximo: float, altura_barra: int = 26, espaco: int = 14, rotulo_l: int = 110) -> float:
    """itens = (rótulo, valor, cor, texto do valor). Devolve o y final."""
    y = y0
    for rotulo, valor, cor, texto_valor in itens:
        svg.texto(x0 + rotulo_l - 10, y + altura_barra * 0.68, rotulo, 13, ESCURO, "end")
        svg.ret(x0 + rotulo_l, y, largura - rotulo_l, altura_barra, "#f3f4f6")
        w = (largura - rotulo_l) * valor / maximo
        svg.ret(x0 + rotulo_l, y, w, altura_barra, cor)
        dentro = w > 70
        svg.texto(x0 + rotulo_l + (w - 8 if dentro else w + 8), y + altura_barra * 0.68, texto_valor, 13,
                  "#ffffff" if dentro else ESCURO, "end" if dentro else "start", "600")
        y += altura_barra + espaco
    return y


# ------------------------------------------------------------ imagens (PNG)

def bilinear(largura: int, altura: int, px: bytes, nova_l: int, nova_a: int) -> bytes:
    saida = bytearray(nova_l * nova_a)
    for y in range(nova_a):
        fy = y * (altura - 1) / (nova_a - 1)
        y0 = int(fy)
        y1 = min(y0 + 1, altura - 1)
        dy = fy - y0
        for x in range(nova_l):
            fx = x * (largura - 1) / (nova_l - 1)
            x0 = int(fx)
            x1 = min(x0 + 1, largura - 1)
            dx = fx - x0
            topo = px[y0 * largura + x0] * (1 - dx) + px[y0 * largura + x1] * dx
            base = px[y1 * largura + x0] * (1 - dx) + px[y1 * largura + x1] * dx
            saida[y * nova_l + x] = int(topo * (1 - dy) + base * dy + 0.5)
    return bytes(saida)


def lado_a_lado(paineis: List[bytes], largura: int, altura: int, espaco: int = 12) -> Tuple[int, bytes]:
    total = largura * len(paineis) + espaco * (len(paineis) - 1)
    saida = bytearray([255]) * (total * altura)
    for i, painel in enumerate(paineis):
        x0 = i * (largura + espaco)
        for y in range(altura):
            saida[y * total + x0:y * total + x0 + largura] = painel[y * largura:(y + 1) * largura]
    return total, bytes(saida)


def figuras_das_etapas_1_e_2() -> None:
    w, h, px = imagem.ler_png(FIGURAS / "exemplo.png")
    # Etapa 1: quadro real recebido pela serial (lado esquerdo da figura da monografia)
    real = imagem.recortar(w, px, 3, 2, 252, 164)
    imagem.salvar_png(SAIDA / "etapa1-quadro-real.png", 249, 162, real)
    print("   etapa1-quadro-real.png")
    # Etapa 2: quadro real com falhas por perda de pacotes (lado direito)
    falhas = imagem.recortar(w, px, 258, 2, 497, 164)
    imagem.salvar_png(SAIDA / "etapa2-falhas-reais.png", 239, 162, falhas)
    print("   etapa2-falhas-reais.png")

    # Etapa 2 simulada: o mesmo quadro (4:3, ampliado para 320x240) com 0%, 2% e 5% de perda
    recorte = imagem.recortar(249, real, 16, 0, 232, 162)
    cena = bilinear(216, 162, recorte, p.LARGURA, p.ALTURA)
    paineis = []
    for perda in (0.0, 0.02, 0.05):
        pacotes = canal(pacotes_do_quadro(cena, 0, "bruto", passo=1), perda, 0, 0, random.Random(7))
        rem = Remontador()
        prontos = []
        for pacote in pacotes:
            prontos += rem.adicionar(pacote)
        quadro = prontos[0] if prontos else rem.finalizar()
        paineis.append(bytes(quadro.pixels))
    total, composta = lado_a_lado(paineis, p.LARGURA, p.ALTURA)
    imagem.salvar_png(SAIDA / "etapa2-perdas-simuladas.png", total, p.ALTURA, composta)
    print("   etapa2-perdas-simuladas.png")


# ---------------------------------------------------------------- diagramas

def figura_pacote() -> None:
    svg = Svg(760, 222, "Pacote de 32 bytes (limite do nRF24L01+)",
          "4 bytes de cabeçalho + 28 de dados. Cada linha da imagem começa em um pacote novo.")
    x0, y0 = 24, 92
    campos = [("0", "flags+seq", 74, AZUL), ("1", "seq", 56, AZUL), ("2", "quadro", 64, "#1d4ed8"),
              ("3", "CRC-8", 64, "#7c3aed"), ("4", "linha", 58, LARANJA), ("5", "cód.", 52, LARANJA),
              ("6 … 31", "26 bytes de imagem (bruto, RLE ou Rice)", 712 - 368, "#93c5fd")]
    x = x0
    for indice, nome, largura, cor in campos:
        svg.texto(x + largura / 2, y0 - 8, f"byte {indice}" if len(indice) < 3 else f"bytes {indice}", 10, SUAVE, "middle")
        svg.ret(x, y0, largura - 3, 44, cor, rx=4)
        svg.texto(x + largura / 2 - 1, y0 + 27, nome, 12 if largura < 100 else 13,
                  "#ffffff" if largura < 100 else "#1e3a8a", "middle", "600")
        x += largura
    svg.linha(x0, y0 + 58, x0 + 255, y0 + 58, AZUL, 2)
    svg.texto(x0, y0 + 76, "Cabeçalho: início/fim de quadro e de linha, sequência de 12 bits, id do quadro, CRC-8",
              12, ESCURO)
    svg.linha(x0 + 258, y0 + 92, x0 + 365, y0 + 92, LARANJA, 2)
    svg.texto(x0 + 258, y0 + 110, "Só no 1º pacote de cada linha; os seguintes levam 28 bytes de imagem.", 12, "#b45309")
    svg.salvar("pacote.svg")


def figura_rle() -> None:
    svg = Svg(760, 268, "RLE: troca repetições por pares (quantidade, valor)",
          "Funciona em áreas uniformes; com ruído, cada pixel vira um par e o tamanho dobra.")

    def faixa(y: float, valores: List[int], rotulo: str, pares: str, resultado: str, cor_resultado: str) -> None:
        svg.texto(24, y + 22, rotulo, 13, ESCURO, peso="600")
        x = 150
        for v in valores:
            svg.ret(x, y, 34, 34, f"rgb({v},{v},{v})", "#d1d5db", 2)
            svg.texto(x + 17, y + 22, str(v), 11, "#ffffff" if v < 140 else ESCURO, "middle")
            x += 36
        svg.texto(150, y + 56, pares, 13, "#1d4ed8", peso="600")
        svg.texto(736, y + 56, resultado, 13, cor_resultado, "end", "600")

    faixa(76, [200] * 5 + [57] * 2 + [90] * 5, "Área uniforme", "(5, 200)  (2, 57)  (5, 90)", "12 bytes → 6 bytes", VERDE)
    faixa(166, [200, 202, 199, 201, 200, 198, 57, 59, 90, 91, 89, 90], "Com ruído",
          "(1,200) (1,202) (1,199) (1,201) …", "12 bytes → 24 bytes", "#dc2626")
    svg.salvar("rle.svg")


def figura_captura() -> None:
    svg = Svg(760, 284, "Captura entrelaçada: o rádio é mais lento que a câmera",
          "Enquanto uma linha é transmitida, a câmera entrega outras; elas são pegas nos quadros seguintes.")
    cores = [AZUL, LARANJA, VERDE, "#7c3aed"]
    y0, altura, n = 76, 9, 16
    for y in range(n):
        svg.ret(84, y0 + y * (altura + 3), 300, altura, cores[y % 4], rx=2)
        svg.texto(76, y0 + y * (altura + 3) + 8, f"linha {y}", 9, SUAVE, "end")
    for i, cor in enumerate(cores):
        svg.ret(420, 84 + i * 28, 16, 16, cor)
        svg.texto(444, 97 + i * 28, f"{i + 1}º quadro da câmera: linhas {i}, {i + 4}, {i + 8}, …", 12)
    svg.texto(420, 218, "Sem buffer de quadro: o Mega tem só 8 kB de RAM.", 12, SUAVE)
    svg.texto(420, 236, "Menos pacotes por linha = menos quadros da câmera.", 12, SUAVE)
    svg.salvar("captura-entrelacada.svg")


# --------------------------------------------------------- gráficos de resultados

def figura_etapa3() -> None:
    svg = Svg(760, 170, "Etapa 3: pacotes entregues pelo nRF24L01+ (1 Mbps)", "Medido em bancada, com linha de visada")
    barras_horizontais(svg, 24, 80, 712, [(rot, v, AZUL, f"{v:.1f}%".replace(".", ",")) for rot, v in ENTREGA], 100)
    svg.salvar("etapa3-entrega.svg")


def figura_etapa4() -> None:
    svg = Svg(760, 268, "Etapa 4: efeito do RLE no enlace sem fio", "Médias medidas em bancada (monografia, Capítulo 4)")
    y = barras_horizontais(svg, 24, 80, 712, [
        ("Bytes/quadro", 100, CINZA, "76.800 sem compressão"),
        ("", 100 * BYTES_RLE / BYTES_SEM, VERDE, "50.400 com RLE  (−34,4%)"),
    ], 100, altura_barra=24, espaco=6)
    barras_horizontais(svg, 24, y + 14, 712, [
        ("Quadros/s", 100 / (1 + GANHO_FPS / 100), CINZA, "1,00× sem compressão"),
        ("", 100, VERDE, "1,51× com RLE  (+50,8%)"),
    ], 100, altura_barra=24, espaco=6)
    svg.texto(24, 252, f"Pacotes entregues: {ENTREGA_SEM:.1f}% sem compressão e {ENTREGA_RLE:.1f}% com RLE".replace(".", ","),
              12, SUAVE)
    svg.salvar("etapa4-rle.svg")


def figura_compressao() -> None:
    cenas = compressao.cenas_de_teste()
    resultados = [compressao.avaliar(pixels) for _, pixels in cenas]
    nomes = [a.nome for a in compressao.ALGORITMOS if a.nome != "Bruto"]
    svg = Svg(760, 120 + 64 * len(nomes), "Comparação de compressão sem perdas (simulação)",
              "Redução de bytes por quadro em duas cenas sintéticas 320x240. ✔ = disponível no firmware.")
    cores = [LARANJA, AZUL]
    for i, (nome_cena, _) in enumerate(cenas):
        svg.ret(470 + i * 150, 70, 14, 14, cores[i])
        svg.texto(490 + i * 150, 82, nome_cena, 12)
    y = 100
    for nome in nomes:
        alg = next(a for a in compressao.ALGORITMOS if a.nome == nome)
        rotulo = ("✔ " if alg.no_firmware else "") + nome
        svg.texto(24, y + 26, rotulo, 13, ESCURO, peso="600")
        svg.texto(24, y + 42, f"RAM extra: {alg.ram_extra}", 11, SUAVE)
        for i, res in enumerate(resultados):
            reducao = 100 * res[nome].reducao()
            yb = y + i * 24
            svg.ret(180, yb + 4, 520, 18, "#f3f4f6")
            svg.ret(180, yb + 4, 520 * reducao / 100, 18, cores[i])
            svg.texto(180 + 520 * reducao / 100 + 6, yb + 18, f"{reducao:.0f}%", 12, ESCURO, peso="600")
        y += 64
    svg.salvar("compressao.svg")


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"Gerando figuras em {SAIDA}")
    figuras_das_etapas_1_e_2()
    figura_pacote()
    figura_rle()
    figura_captura()
    figura_etapa3()
    figura_etapa4()
    figura_compressao()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
