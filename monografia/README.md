# Monografia (código-fonte LaTeX)

Fonte da monografia do TCC II, no modelo `ufrgscca` da Escola de
Engenharia da UFRGS (classe de Alceu Frigeri, na pasta `tex/`). O PDF final
está em [`docs/monografia-tcc2.pdf`](../docs/monografia-tcc2.pdf).

| Arquivo | Conteúdo |
|---|---|
| `monografia.tex` | texto completo |
| `local.tex` | dados da capa: autor, orientador, banca, coordenação |
| `referencias.bib` | referências (biblatex/biber, ABNT) |
| `figuras/` | figuras (as usadas no texto e as de versões anteriores) |
| `tex/` | classe e estilos da UFRGS |

## Compilar

Precisa de uma distribuição TeX com `biber` (TeX Live, MiKTeX ou Overleaf).
O `latexmkrc` já adiciona a pasta `tex/` ao caminho de busca:

```bash
cd monografia
```

```bash
latexmk -pdf monografia.tex
```

No Overleaf: envie a pasta inteira, defina `monografia.tex` como documento
principal e mude o compilador de bibliografia para *Biber*.

> Os nomes dos arquivos foram trocados na reorganização do repositório
> (`ModeloTCC.tex` -> `monografia.tex`, `modeloTCC.bib` -> `referencias.bib`,
> `images/` -> `figuras/`). O conteúdo do texto é o da versão entregue.
