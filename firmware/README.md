# Firmware (Arduino)

| Sketch | Placa | Para que serve |
|---|---|---|
| [`transmissor_capsula`](transmissor_capsula) | Mega 2560 | A "cápsula": captura a OV7670, comprime, empacota e transmite |
| [`receptor_base`](receptor_base) | Uno / Nano | A "estação externa": repassa os pacotes do rádio para o PC pela USB |
| [`diagnostico_camera`](diagnostico_camera) | Mega 2560 | Confere XCLK, I2C, VSYNC, HREF, PCLK e cada bit D0–D7 da câmera |
| [`teste_radio_emissor`](teste_radio_emissor) + [`teste_radio_receptor`](teste_radio_receptor) | qualquer uma | Mede entrega de pacotes, retransmissões e vazão do enlace |

Ligações: [`docs/hardware.md`](../docs/hardware.md) · Protocolo:
[`docs/protocolo.md`](../docs/protocolo.md) · Compressão:
[`docs/compressao.md`](../docs/compressao.md)

## Como gravar

1. Instale a [Arduino IDE](https://www.arduino.cc/en/software) 2.x.
2. Em *Ferramentas › Gerenciar Bibliotecas…*, instale **RF24** (TMRh20, 1.4+).
   O driver da câmera já vem em `transmissor_capsula/src/LiveOV7670`.
3. Abra a pasta do sketch, escolha a placa e a porta e clique em *Carregar*.

Com o [arduino-cli](https://arduino.github.io/arduino-cli/):

```bash
arduino-cli core install arduino:avr
```

```bash
arduino-cli lib install RF24
```

```bash
arduino-cli compile --fqbn arduino:avr:mega firmware/transmissor_capsula
```

```bash
arduino-cli compile --fqbn arduino:avr:uno firmware/receptor_base
```

## Reproduzindo as etapas do TCC

Em `transmissor_capsula/config.h`, uma única linha escolhe a etapa:

```c
#define ETAPA 4
```

| `ETAPA` | O que o Mega faz | Onde ligar o PC | Comando no PC (pasta `software/`) |
|---|---|---|---|
| 1 | quadros brutos pela USB, sem cabeçalho (câmera mais lenta, ~2 s/quadro) | Mega | `python -m capsula.receber --porta COM3 --bruto` |
| 2 | pacotes pela USB, descartando 2% e trocando a ordem de 1% de propósito | Mega | `python -m capsula.receber --porta COM3` |
| 3 | pacotes pelo rádio, sem compressão | Uno (`receptor_base`) | `python -m capsula.receber --porta COM5 --csv etapa3.csv` |
| 4 | pacotes pelo rádio com RLE | Uno (`receptor_base`) | `python -m capsula.receber --porta COM5 --csv etapa4.csv` |

Nas etapas 3 e 4, o Monitor Serial do Mega (115200 baud) mostra, a cada
imagem, os pacotes sem ACK, quantas linhas foram brutas/RLE/Rice e quantos
quadros da câmera foram usados.

## Ordem sugerida em bancada

1. **`diagnostico_camera`** no Mega: todos os itens devem aparecer como
   `[ OK ]` no Monitor Serial (115200 baud).
2. **`teste_radio_emissor`** (Mega) + **`teste_radio_receptor`** (Uno):
   confirma a fiação dos rádios e a taxa de entrega na distância desejada.
3. **`transmissor_capsula`** nas etapas 1 → 4, nessa ordem.

## Outros ajustes em `config.h`

| Opção | Padrão | Efeito |
|---|---|---|
| `COMPRESSAO` | da etapa | `COMP_RICE` ativa o DPCM + Golomb-Rice: cada linha vai bruta, em RLE ou em Rice, o que for menor |
| `PERDA_SIMULADA_POR_MIL` / `REORDENACAO_SIMULADA_POR_MIL` | 20 / 10 na etapa 2 | perdas e trocas de ordem artificiais |
| `CAMERA_PRESCALER` | 20 na etapa 1, 5 nas outras | velocidade da câmera; não use menos que 4 |
| `BYTES_IGNORADOS_INICIO_LINHA` | `1` | alinhamento do primeiro Y da linha (teste 0 ou 2 se a imagem sair listrada) |
| `CANAL_RADIO`, `TAXA_RADIO`, `ENDERECO_RADIO` | 76, 1 Mbps, `CAPS1` | precisam ser iguais no `receptor_base` |

O protocolo do firmware é o mesmo do software de PC
([`software/capsula/protocolo.py`](../software/capsula/protocolo.py) e
[`rice.py`](../software/capsula/rice.py)), que tem testes automatizados e
vetores de referência em [`docs/protocolo.md`](../docs/protocolo.md). Se mudar
um, mude o outro.
