// =============================================================================
//  Teste do enlace de rádio  -  RECEPTOR (Uno/Nano ou Mega 2560)
//
//  Recebe os pacotes numerados de teste_radio_emissor e, pelos saltos na
//  numeração, calcula a perda de pacotes a cada segundo. Monitor Serial a
//  115200 baud.
// =============================================================================

#include <SPI.h>
#include <RF24.h>

#if defined(__AVR_ATmega2560__)
const uint8_t PINO_CE = 48, PINO_CSN = 53;
#else
const uint8_t PINO_CE = 9, PINO_CSN = 10;
#endif

#define CANAL_RADIO 76
#define TAXA_RADIO  RF24_1MBPS
static const uint8_t ENDERECO_RADIO[6] = "CAPS1";

RF24 radio(PINO_CE, PINO_CSN);

uint32_t esperado = 0;
uint32_t recebidos = 0, perdidos = 0;
bool primeiro = true;
uint32_t ultimoRelatorio = 0;

void setup() {
  Serial.begin(115200);
  if (!radio.begin()) {
    Serial.println(F("ERRO: nRF24L01+ nao encontrado (SPI, CE/CSN, 3,3 V)"));
    for (;;) {}
  }
  radio.setChannel(CANAL_RADIO);
  radio.setDataRate(TAXA_RADIO);
  radio.setPALevel(RF24_PA_LOW);
  radio.setPayloadSize(32);
  radio.setCRCLength(RF24_CRC_16);
  radio.setAutoAck(true);
  radio.openReadingPipe(1, ENDERECO_RADIO);
  radio.startListening();
  Serial.println(F("Receptor de teste pronto."));
}

void loop() {
  while (radio.available()) {
    uint8_t pacote[32];
    radio.read(pacote, sizeof(pacote));
    uint32_t numero;
    memcpy(&numero, pacote, sizeof(numero));
    if (!primeiro && numero > esperado && numero - esperado < 100000UL) perdidos += numero - esperado;
    primeiro = false;
    esperado = numero + 1;
    recebidos++;
  }

  if (millis() - ultimoRelatorio >= 1000) {
    ultimoRelatorio = millis();
    if (recebidos) {
      Serial.print(F("Recebidos: "));
      Serial.print(recebidos);
      Serial.print(F(" | perdidos: "));
      Serial.print(perdidos);
      Serial.print(F(" | sucesso: "));
      Serial.print(100.0 * recebidos / (recebidos + perdidos), 1);
      Serial.println(F("%"));
    } else {
      Serial.println(F("Nenhum pacote neste segundo"));
    }
    recebidos = perdidos = 0;
  }
}
