// =============================================================================
//  Transmissor da cápsula endoscópica  -  Arduino Mega 2560
//
//  OV7670 (QVGA, luminância) -> compressão + pacotes -> nRF24L01+ (ou USB)
//
//  A etapa do TCC (1 a 4) é escolhida em config.h com #define ETAPA.
//
//  Bibliotecas: RF24 (TMRh20) pelo Gerenciador de Bibliotecas. O driver da
//  câmera (LiveOV7670, de Indrek Luuk) já vem junto em src/LiveOV7670.
//  Ajustes de bancada: config.h. Ligações: docs/hardware.md.
//
//  Como a captura funciona
//  -----------------------
//  O Mega não tem memória para um quadro inteiro (76,8 kB contra 8 kB de RAM)
//  e o rádio é mais lento que a câmera. Por isso o firmware trabalha linha a
//  linha: lê uma linha, envia, e enquanto envia uma interrupção no HREF conta
//  as linhas que passam. Terminado o envio, ele pega a próxima linha ainda não
//  enviada que a câmera for entregar. As linhas puladas são capturadas nos
//  quadros seguintes da câmera, até a imagem estar completa (EOF). Assim a
//  captura nunca perde o sincronismo, mesmo quando o rádio retransmite, e a
//  compressão (envio mais curto) se traduz diretamente em mais quadros por
//  segundo. Na etapa 1 (sem cabeçalho) as linhas precisam sair em ordem, então
//  só a próxima linha da sequência é aceita.
// =============================================================================

#include <SPI.h>
#include <Wire.h>
#include <RF24.h>

#include "config.h"
#include "protocolo.h"
#include "src/LiveOV7670/CameraOV7670.h"

#if !defined(__AVR_ATmega2560__)
#error "Este firmware é para o Arduino Mega 2560 (Ferramentas > Placa > Arduino Mega or Mega 2560)."
#endif

using namespace protocolo;

// ---- Leitura direta dos pinos da câmera (digitalRead seria lento demais) ----
#define CAM_VSYNC() (PINE & (1 << 4))  // pino 2  = PE4 (INT4)
#define CAM_HREF()  (PINE & (1 << 5))  // pino 3  = PE5 (INT5)
#define CAM_PCLK()  (PINB & (1 << 6))  // pino 12 = PB6
#define CAM_DADOS() (PINA)             // pinos 22..29 = PA0..PA7 = D0..D7
const uint8_t PINO_VSYNC = 2;
const uint8_t PINO_HREF  = 3;

#if ENLACE != ENLACE_RADIO
#define LOG(...)                       // a USB transporta os dados binários
#define LOGLN(...)
#else
#define LOG(...)   Serial.print(__VA_ARGS__)
#define LOGLN(...) Serial.println(__VA_ARGS__)
#endif

CameraOV7670 camera(CameraOV7670::RESOLUTION_QVGA_320x240, CameraOV7670::PIXEL_YUV422, CAMERA_PRESCALER);
const uint8_t LINHAS_DE_AJUSTE = CameraOV7670Registers::QVGA_VERTICAL_PADDING;  // linhas iniciais descartadas

RF24 radio(PINO_RADIO_CE, PINO_RADIO_CSN);

// ---- Estado ----------------------------------------------------------------
volatile uint8_t  g_linhasIniciadas = 0;  // bordas de HREF desde o último VSYNC
volatile uint16_t g_quadrosCamera = 0;    // VSYNCs (quadros entregues pela câmera)

uint8_t linha[LARGURA];                   // luminância da linha capturada
uint8_t pendentes[(ALTURA + 7) / 8];      // 1 bit por linha ainda não enviada
uint8_t idImagem = 0;
int16_t somenteLinha = -1;                // etapa 1: só aceita esta linha (ordem)

// ---- Interrupções: contam as linhas enquanto o rádio está ocupado ----------
void aoVsync() { g_linhasIniciadas = 0; g_quadrosCamera++; }
void aoHref()  { if (g_linhasIniciadas < 255) g_linhasIniciadas++; }

inline void contagemPorInterrupcao(bool ligada) {
  if (ligada) {
    EIFR = (1 << INTF4) | (1 << INTF5);  // descarta bordas já contadas por varredura
    EIMSK |= (1 << INT4) | (1 << INT5);
  } else {
    EIMSK &= ~((1 << INT4) | (1 << INT5));
  }
}

inline bool estaPendente(uint8_t y) { return pendentes[y >> 3] & (1 << (y & 7)); }
inline void marcarEnviada(uint8_t y) { pendentes[y >> 3] &= ~(1 << (y & 7)); }

// ---- Envio -----------------------------------------------------------------
static bool transmitir(const uint8_t *pacote) {
#if ENLACE == ENLACE_RADIO
  return radio.write(pacote, TAMANHO_PACOTE);  // auto-ack + até 15 retransmissões
#else
  Serial.write(SYNC0);
  Serial.write(SYNC1);
  Serial.write(pacote, TAMANHO_PACOTE);
  return true;
#endif
}

#if REORDENACAO_SIMULADA_POR_MIL > 0
uint8_t pacoteAdiado[TAMANHO_PACOTE];
bool temPacoteAdiado = false;
#endif

// Envia um pacote; na etapa 2 descarta ou atrasa alguns de propósito.
bool enviarPacote(const uint8_t *pacote) {
#if PERDA_SIMULADA_POR_MIL > 0
  if (random(1000) < PERDA_SIMULADA_POR_MIL) return false;
#endif
#if REORDENACAO_SIMULADA_POR_MIL > 0
  if (!temPacoteAdiado && random(1000) < REORDENACAO_SIMULADA_POR_MIL) {
    memcpy(pacoteAdiado, pacote, TAMANHO_PACOTE);  // vai depois do próximo
    temPacoteAdiado = true;
    return true;
  }
  const bool ok = transmitir(pacote);
  if (temPacoteAdiado) {
    transmitir(pacoteAdiado);
    temPacoteAdiado = false;
  }
  return ok;
#else
  return transmitir(pacote);
#endif
}

static void descarregarPacoteAdiado() {
#if REORDENACAO_SIMULADA_POR_MIL > 0
  if (temPacoteAdiado) {
    transmitir(pacoteAdiado);
    temPacoteAdiado = false;
  }
#endif
}

Empacotador empacotador(enviarPacote);

// ---- Captura ---------------------------------------------------------------
// Espera a próxima borda de subida do PCLK (o dado é válido nela).
#define ESPERAR_BORDA_PCLK() do { while (CAM_PCLK()) {} while (!CAM_PCLK()) {} } while (0)

// Chamada com interrupções desligadas, logo após a subida do HREF.
// YUV422 chega como Y U Y V ...: guarda os Y e descarta U/V.
static void lerLinha(uint8_t *destino) {
  for (uint8_t i = 0; i < BYTES_IGNORADOS_INICIO_LINHA; i++) ESPERAR_BORDA_PCLK();
  uint8_t *p = destino;
  uint8_t *const fim = destino + LARGURA;
  while (p < fim) {
    ESPERAR_BORDA_PCLK();
    *p++ = CAM_DADOS();  // Y
    ESPERAR_BORDA_PCLK();  // U ou V: descartado
  }
}

// Espera VSYNC por varredura. Devolve false se a câmera não der sinal em ~2 s.
static bool sincronizarComQuadro() {
  const uint32_t inicio = millis();
  while (!CAM_VSYNC()) if (millis() - inicio > 2000) return false;
  while (CAM_VSYNC())  if (millis() - inicio > 2000) return false;
  return true;
}

// Sincroniza com o início de um quadro e liga a contagem de linhas por interrupção.
static bool ressincronizar() {
  contagemPorInterrupcao(false);
  const bool ok = sincronizarComQuadro();
  g_linhasIniciadas = 0;
  contagemPorInterrupcao(true);  // também descarta bordas antigas pendentes
  return ok;
}

// Captura a próxima linha ainda pendente. Devolve o índice (0..239), ou -1 se
// a câmera parar de responder.
static int16_t capturarProximaLinhaPendente() {
  // Assume a contagem de linhas (antes feita pelas interrupções).
  noInterrupts();
  contagemPorInterrupcao(false);
  uint8_t linhas = g_linhasIniciadas;
  if (EIFR & (1 << INTF4)) linhas = 0;                  // bordas que chegaram entre
  if ((EIFR & (1 << INTF5)) && linhas < 255) linhas++;  // o último ISR e o cli()
  EIFR = (1 << INTF4) | (1 << INTF5);
  interrupts();

  const uint32_t inicio = millis();
  while (CAM_HREF()) {}  // no meio de uma linha: espera ela acabar

  for (;;) {
    if (millis() - inicio > 3000) return -1;

    // HREF está em nível baixo: a próxima subida é a linha número `linhas`.
    const int16_t y = (int16_t)linhas - LINHAS_DE_AJUSTE;
    const bool queremos = y >= 0 && y < ALTURA && estaPendente((uint8_t)y) &&
                          (somenteLinha < 0 || y == somenteLinha);
    if (linhas == 255) {  // contagem saturou (um quadro tem ~245 linhas): ressincroniza
      if (!sincronizarComQuadro()) return -1;
      linhas = 0;
      continue;
    }

    if (queremos) noInterrupts();  // nada pode atrasar a leitura dos pixels
    uint32_t guarda = 0;
    bool novoQuadro = false;
    while (!CAM_HREF()) {
      if (CAM_VSYNC()) { novoQuadro = true; break; }
      if (++guarda == 8000000UL) { interrupts(); return -1; }  // ~3 s sem HREF
    }
    if (novoQuadro) {
      interrupts();
      while (CAM_VSYNC()) {}
      linhas = 0;
      continue;
    }

    if (queremos) {
      lerLinha(linha);
      interrupts();
      g_linhasIniciadas = ++linhas;
      contagemPorInterrupcao(true);  // o rádio vai ocupar a CPU por alguns ms
      return y;
    }

    if (linhas < 255) linhas++;
    while (CAM_HREF()) {}  // linha já enviada: pula
  }
}

// ---- Programa --------------------------------------------------------------
static void parar(const __FlashStringHelper *mensagem) {
  LOGLN(mensagem);
  pinMode(LED_BUILTIN, OUTPUT);
  for (;;) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    delay(150);
  }
}

void setup() {
#if ENLACE == ENLACE_RADIO
  Serial.begin(BAUD_DEPURACAO);
#else
  Serial.begin(BAUD_ENLACE_SERIAL);
#endif
  LOGLN(F("\nTransmissor da capsula endoscopica"));

  // Autoteste do CRC: valor de verificação do CRC-8/SMBUS (igual ao Python).
  if (crc8((const uint8_t *)"123456789", 9) != 0xF4) parar(F("ERRO: CRC-8 inconsistente"));

  if (!camera.init()) parar(F("ERRO: a camera nao respondeu no I2C (SIOD/SIOC, 3,3 V, XCLK)"));
  // O Mega já tem pull-ups de 10k no SDA/SCL; os internos (5 V) não são necessários.
  digitalWrite(SDA, LOW);
  digitalWrite(SCL, LOW);
  LOGLN(F("Camera OV7670 configurada (QVGA, YUV422)"));

#if ENLACE == ENLACE_RADIO
  if (!radio.begin()) parar(F("ERRO: nRF24L01+ nao encontrado (SPI, CE/CSN, 3,3 V)"));
  radio.setChannel(CANAL_RADIO);
  radio.setDataRate(TAXA_RADIO);
  radio.setPALevel(POTENCIA_RADIO);
  radio.setPayloadSize(TAMANHO_PACOTE);
  radio.setCRCLength(RF24_CRC_16);
  radio.setAutoAck(true);
  radio.setRetries(1, 15);  // espera 500 us entre tentativas, até 15 retransmissões
  radio.openWritingPipe(ENDERECO_RADIO);
  radio.stopListening();
  LOGLN(F("nRF24L01+ pronto"));
#endif

  attachInterrupt(digitalPinToInterrupt(PINO_VSYNC), aoVsync, RISING);
  attachInterrupt(digitalPinToInterrupt(PINO_HREF), aoHref, RISING);

  if (!ressincronizar()) parar(F("ERRO: sem VSYNC da camera (verifique XCLK e VSYNC)"));
  randomSeed(micros());
  LOGLN(F("Transmitindo..."));
}

// Etapa 1: o quadro inteiro, linha por linha e em ordem, sem cabeçalho.
static void enviarQuadroBruto() {
  memset(pendentes, 0xFF, sizeof(pendentes));
  Serial.write(MARCADOR_QUADRO_BRUTO, sizeof(MARCADOR_QUADRO_BRUTO));
  for (int16_t y = 0; y < ALTURA;) {
    somenteLinha = y;
    if (capturarProximaLinhaPendente() < 0) {
      ressincronizar();
      continue;
    }
    Serial.write(linha, LARGURA);
    y++;
  }
  somenteLinha = -1;
}

void loop() {
#if ENLACE == ENLACE_SERIAL_BRUTO
  enviarQuadroBruto();
  return;
#endif

  memset(pendentes, 0xFF, sizeof(pendentes));
  uint8_t restantes = ALTURA;
  uint16_t falhas = 0;
  uint8_t linhasPorCodificacao[3] = {0, 0, 0};
  const uint16_t quadrosCameraInicio = g_quadrosCamera;
  empacotador.novoQuadro(idImagem);

  while (restantes > 0) {
    const int16_t y = capturarProximaLinhaPendente();
    if (y < 0) {
      LOGLN(F("Aviso: camera sem sinal, tentando de novo"));
      ressincronizar();
      continue;
    }
    marcarEnviada((uint8_t)y);
    restantes--;
    falhas += empacotador.enviarLinha((uint8_t)y, linha, COMPRESSAO, restantes == 0);
    linhasPorCodificacao[empacotador.ultimaCodificacao()]++;
  }
  descarregarPacoteAdiado();

  const uint16_t pacotes = empacotador.pacotesNoQuadro();
  LOG(F("Imagem "));
  LOG(idImagem);
  LOG(F(": "));
  LOG(pacotes);
  LOG(F(" pacotes, "));
  LOG(falhas);
  LOG(F(" sem ACK ("));
  LOG(100.0 * (pacotes - falhas) / pacotes, 1);
  LOG(F("% entregues) | linhas bruto/RLE/Rice: "));
  LOG(linhasPorCodificacao[COD_BRUTO]);
  LOG('/');
  LOG(linhasPorCodificacao[COD_RLE]);
  LOG('/');
  LOG(linhasPorCodificacao[COD_RICE]);
  LOG(F(" | "));
  LOG((uint16_t)(g_quadrosCamera - quadrosCameraInicio));
  LOGLN(F(" quadros da camera"));

  idImagem++;
}
