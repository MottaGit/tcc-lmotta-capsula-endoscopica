# Software de PC (Python)

Recebe os dados do Arduino, valida o CRC-8, reordena, descarta duplicados,
descomprime (RLE ou DPCM + Rice) e salva cada imagem em PNG, com métricas de
entrega. Inclui um **simulador** do transmissor e do canal (perdas,
duplicação, reordenação) e a **comparação de algoritmos de compressão**.

Usa só a biblioteca padrão do Python 3.9+. O `pyserial` é necessário apenas
para ler a porta serial ao vivo.

```bash
cd software
```

```bash
pip install -r requirements.txt
```

## Comandos

| Comando | O que faz |
|---|---|
| `python -m capsula.receber --porta COM5` | recebe ao vivo do Uno (etapas 3 e 4) ou do Mega (etapa 2) |
| `python -m capsula.receber --porta COM3 --bruto` | etapa 1: quadros brutos do Mega |
| `python -m capsula.receber --arquivo demo.bin` | reprocessa uma gravação ou saída do simulador |
| `python -m capsula.simular --saida demo.bin --perda 0.03` | gera o fluxo de bytes do receptor, sem hardware |
| `python -m capsula.compressao` | compara RLE, DPCM + RLE, DPCM + Rice, MED + Rice e DEFLATE |
| `python ferramentas/gerar_figuras.py` | recria as figuras do README em `docs/imagens/` |
| `python ferramentas/hex_para_png.py arquivo.txt` | converte um despejo hexadecimal da câmera e aponta bits presos |
| `python -m unittest discover -s tests` | roda os 29 testes |

Opções do `receber`: `--saida pasta` (PNG), `--csv metricas.csv` (uma linha
por quadro), `--faltantes anterior` (repete o quadro anterior nas linhas
perdidas), `--gravar sessao.bin` (bytes brutos para reprocessar) e
`--quadros N`.

Opções do `simular`: `--quadros N`, `--compressao bruto|rle|rice`,
`--perda`, `--duplicar`, `--reordenar`, `--ruido 2.5`, `--imagem foto.pgm`
e `--bruto` (etapa 1).

## Exemplo

```bash
python -m capsula.simular --saida demo.bin --quadros 2 --perda 0.03 --duplicar 0.005 --reordenar 0.01
```

```bash
python -m capsula.receber --arquivo demo.bin --csv metricas.csv
```

```
Quadro   0: 1736/1782 pacotes (97.4%), linhas 200 completas / 31 parciais / 9 faltantes, RLE/Rice em 231/0 linhas (39.8% menor), 8 duplicados -> quadro_0001.png
```

## Organização

| Arquivo | Conteúdo |
|---|---|
| `capsula/protocolo.py` | pacote, CRC-8, empacotador (igual ao firmware), leitores da serial |
| `capsula/rle.py`, `capsula/rice.py` | codificadores usados no firmware |
| `capsula/compressao.py` | comparação de algoritmos (inclui DPCM + RLE, MED + Rice e DEFLATE) |
| `capsula/remontagem.py` | remontagem dos quadros e métricas |
| `capsula/receber.py`, `capsula/simular.py` | linha de comando |
| `capsula/imagem.py` | PNG/PGM em tons de cinza sem dependências |
| `tests/` | testes do protocolo, da compressão e da remontagem |
