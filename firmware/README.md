# Firmware (Arduino)

| Sketch | Placa | Para que serve |
|---|---|---|
| [`transmissor_capsula`](transmissor_capsula) | Mega 2560 | A "cápsula": captura a OV7670, aplica RLE, empacota e transmite |
| [`receptor_base`](receptor_base) | Uno / Nano | A "estação externa": repassa os pacotes do rádio para o PC pela USB |
| [`diagnostico_camera`](diagnostico_camera) | Mega 2560 | Confere XCLK, I2C, VSYNC, HREF, PCLK e cada bit D0–D7 da câmera |
| [`teste_radio_emissor`](teste_radio_emissor) + [`teste_radio_receptor`](teste_radio_receptor) | qualquer uma | Mede entrega de pacotes, retransmissões e vazão do enlace |

Ligações: [`docs/hardware.md`](../docs/hardware.md). Protocolo:
[`docs/protocolo.md`](../docs/protocolo.md).

## Como gravar

1. Instale a [Arduino IDE](https://www.arduino.cc/en/software) (2.x).
2. *Ferramentas › Gerenciar Bibliotecas…* e instale **RF24** (de TMRh20,
   versão 1.4 ou mais nova). O driver da câmera já vem junto do transmissor,
   em `transmissor_capsula/src/LiveOV7670`.
3. Abra a pasta do sketch (o `.ino` tem o mesmo nome da pasta), escolha a
   placa e a porta e clique em *Carregar*.

Pela linha de comando, com o [arduino-cli](https://arduino.github.io/arduino-cli/):

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

## Ordem sugerida em bancada

1. **`diagnostico_camera`** no Mega com a câmera ligada: todos os itens
   devem aparecer como `[ OK ]` no Monitor Serial (115200 baud).
2. **`teste_radio_emissor`** (Mega) + **`teste_radio_receptor`** (Uno):
   confirma a fiação dos rádios e a taxa de entrega na distância desejada.
3. **`transmissor_capsula`** com `ENLACE_SERIAL` em `config.h` (Etapa 2):
   os pacotes vão direto pela USB do Mega. Rode o software de PC na porta
   do Mega e confira se a imagem é remontada.
4. **`transmissor_capsula`** com `ENLACE_RADIO` + **`receptor_base`**
   (Etapas 3 e 4): rode o software de PC na porta do Uno. O Monitor Serial
   do Mega (115200 baud) mostra as estatísticas de cada imagem.

## Ajustes em `transmissor_capsula/config.h`

| Opção | Padrão | Efeito |
|---|---|---|
| `ENLACE` | `ENLACE_RADIO` | `ENLACE_SERIAL` manda os pacotes pela USB, sem rádio |
| `USAR_RLE` | `1` | `0` desliga a compressão (comparação da Etapa 4) |
| `PERDA_SIMULADA_POR_MIL` | `0` | descarta pacotes de propósito para testar a remontagem |
| `CAMERA_PRESCALER` | `5` | velocidade da câmera; não use menos que 4 |
| `BYTES_IGNORADOS_INICIO_LINHA` | `1` | alinhamento do primeiro Y da linha (teste 0 ou 2 se a imagem sair listrada) |
| `CANAL_RADIO`, `TAXA_RADIO`, `ENDERECO_RADIO` | 76, 1 Mbps, `CAPS1` | precisam ser iguais no `receptor_base` |

O protocolo do firmware é o mesmo do software de PC
([`software/capsula/protocolo.py`](../software/capsula/protocolo.py)), que
tem testes automatizados. Se mudar um, mude o outro.
