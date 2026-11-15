// =============================================================================
//  Configuração do transmissor (Arduino Mega 2560)
//  Tudo o que normalmente se ajusta em bancada está aqui.
// =============================================================================
#pragma once

// ----------------------------------------------------------------------------
// Etapa do experimento
// ----------------------------------------------------------------------------
// ENLACE_RADIO  -> pacotes vão pelo nRF24L01+ (Etapas 3 e 4 do TCC). A USB
//                  fica livre para mensagens de depuração a BAUD_DEPURACAO.
// ENLACE_SERIAL -> os mesmos pacotes vão direto pela USB, sem rádio (Etapa 2:
//                  valida o protocolo isolando o enlace sem fio). Abra o
//                  software de PC na porta do Mega em vez da porta do Uno.
#define ENLACE_RADIO  1
#define ENLACE_SERIAL 2
#define ENLACE        ENLACE_RADIO

// 1 = aplica RLE nas linhas em que ele reduz o tamanho (Etapa 4); 0 = só bruto.
#define USAR_RLE 1

// Descarta de propósito N pacotes a cada 1000 (teste de robustez da Etapa 2).
#define PERDA_SIMULADA_POR_MIL 0

// ----------------------------------------------------------------------------
// Câmera OV7670 (QVGA 320x240, YUV422, só a luminância Y é usada)
// ----------------------------------------------------------------------------
// Divisor do relógio interno da câmera: f = XCLK (8 MHz) / (N + 1).
// Menor = câmera mais rápida. Abaixo de 4 o laço de leitura não acompanha o PCLK.
#define CAMERA_PRESCALER 5

// Bytes descartados no começo de cada linha para alinhar com o primeiro Y.
// Se a imagem sair com textura "quadriculada"/listrada (lendo U/V no lugar de Y),
// teste 0 ou 2.
#define BYTES_IGNORADOS_INICIO_LINHA 1

// Os pinos da câmera são fixos (leitura direta de registradores, ver
// docs/hardware.md): D0..D7 -> 22..29 | VSYNC -> 2 | HREF -> 3 | PCLK -> 12 |
// XCLK -> 9 | SIOD -> 20 (SDA) | SIOC -> 21 (SCL)

// ----------------------------------------------------------------------------
// Rádio nRF24L01+ (SCK 52, MOSI 51, MISO 50 são os pinos SPI do Mega)
// ----------------------------------------------------------------------------
#define PINO_RADIO_CE  48
#define PINO_RADIO_CSN 53

// Precisam ser iguais no receptor (firmware/receptor_base/receptor_base.ino).
#define CANAL_RADIO    76            // 2400 + 76 = 2476 MHz
#define TAXA_RADIO     RF24_1MBPS    // compromisso entre alcance e vazão (Etapa 3)
#define POTENCIA_RADIO RF24_PA_LOW   // bancada a 1-3 m; evita quedas do regulador de 3,3 V
static const uint8_t ENDERECO_RADIO[6] = "CAPS1";

// ----------------------------------------------------------------------------
// Serial (USB)
// ----------------------------------------------------------------------------
#define BAUD_DEPURACAO     115200    // ENLACE_RADIO: mensagens de texto
#define BAUD_ENLACE_SERIAL 1000000   // ENLACE_SERIAL: mesmo formato e velocidade do receptor
