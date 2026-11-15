// =============================================================================
//  Configuração do transmissor (Arduino Mega 2560)
//  Tudo o que normalmente se ajusta em bancada está aqui.
// =============================================================================
#pragma once

// ----------------------------------------------------------------------------
// Etapa do TCC a reproduzir (Capítulo 4 da monografia)
// ----------------------------------------------------------------------------
//  1 = dados brutos pela USB: 76.800 bytes por quadro, sem cabeçalho
//  2 = protocolo de pacotes pela USB, com perdas e reordenação artificiais
//  3 = rádio nRF24L01+, sem compressão
//  4 = rádio + RLE (configuração final do TCC)
// Nas etapas 1 e 2, rode o software de PC na porta do Mega; nas 3 e 4, na do Uno.
#define ETAPA 4

// Compressão por linha nas etapas 2 a 4. Padrão: RLE na etapa 4, nenhuma nas
// outras. COMP_RICE escolhe, linha a linha, o menor entre bruto, RLE e
// DPCM + Golomb-Rice (mais eficiente em cenas com ruído; ver docs/compressao.md).
// #define COMPRESSAO COMP_RICE

// ----------------------------------------------------------------------------
// Câmera OV7670 (QVGA 320x240, YUV422, só a luminância Y é usada)
// ----------------------------------------------------------------------------
// Divisor do relógio interno da câmera: f = XCLK (8 MHz) / (N + 1).
// Menor = câmera mais rápida. Abaixo de 4 o laço de leitura não acompanha o PCLK.
// Na etapa 1 a câmera precisa ser lenta o bastante para cada linha caber na
// serial antes da próxima (~2 s por quadro).
#define CAMERA_PRESCALER (ETAPA == 1 ? 20 : 5)

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
#define BAUD_DEPURACAO     115200    // etapas 3 e 4: mensagens de texto
#define BAUD_ENLACE_SERIAL 1000000   // etapas 1 e 2: mesmo formato e velocidade do receptor

// ============================================================================
// Derivado da etapa (normalmente não precisa mexer daqui para baixo)
// ============================================================================
#define ENLACE_RADIO        1
#define ENLACE_SERIAL       2
#define ENLACE_SERIAL_BRUTO 3

#if ETAPA == 1
#define ENLACE ENLACE_SERIAL_BRUTO
#elif ETAPA == 2
#define ENLACE ENLACE_SERIAL
#elif ETAPA == 3 || ETAPA == 4
#define ENLACE ENLACE_RADIO
#else
#error "ETAPA deve ser 1, 2, 3 ou 4"
#endif

#ifndef COMPRESSAO
#define COMPRESSAO (ETAPA == 4 ? COMP_RLE : COMP_NENHUMA)
#endif

// Etapa 2: descarta e troca a ordem de alguns pacotes de propósito (por mil).
#ifndef PERDA_SIMULADA_POR_MIL
#define PERDA_SIMULADA_POR_MIL (ETAPA == 2 ? 20 : 0)
#endif
#ifndef REORDENACAO_SIMULADA_POR_MIL
#define REORDENACAO_SIMULADA_POR_MIL (ETAPA == 2 ? 10 : 0)
#endif
