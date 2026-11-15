// =============================================================================
//  Teste do enlace de rádio  -  EMISSOR (Mega 2560 ou Uno/Nano)
//
//  Envia pacotes de 32 bytes numerados, com as mesmas configurações do
//  firmware da cápsula, e mede o que importa na Etapa 3 do TCC: taxa de
//  entrega (pelos ACKs), retransmissões e vazão. Use junto com
//  teste_radio_receptor para validar a fiação e a distância antes de ligar
//  a câmera. Monitor Serial a 115200 baud.
//
//  Os endereços têm 5 bytes: o nRF24 ignora o que passar disso, então
//  endereços como "ADDRESS01" e "ADDRESS02" seriam, na prática, iguais.
// =============================================================================

#include <SPI.h>
#include <RF24.h>

#if defined(__AVR_ATmega2560__)
const uint8_t PINO_CE = 48, PINO_CSN = 53;  // mesma ligação do transmissor da cápsula
#else
const uint8_t PINO_CE = 9, PINO_CSN = 10;
#endif

#define CANAL_RADIO 76
#define TAXA_RADIO  RF24_1MBPS
static const uint8_t ENDERECO_RADIO[6] = "CAPS1";
const uint16_t PACOTES_POR_RODADA = 1000;

RF24 radio(PINO_CE, PINO_CSN);
uint32_t contador = 0;

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
  radio.setRetries(1, 15);
  radio.openWritingPipe(ENDERECO_RADIO);
  radio.stopListening();
  Serial.println(F("Emissor de teste pronto. Rodadas de 1000 pacotes:"));
}

void loop() {
  uint8_t pacote[32] = {0};
  uint16_t confirmados = 0;
  uint32_t retransmissoes = 0;
  const uint32_t inicio = micros();

  for (uint16_t i = 0; i < PACOTES_POR_RODADA; i++) {
    memcpy(pacote, &contador, sizeof(contador));
    contador++;
    if (radio.write(pacote, sizeof(pacote))) confirmados++;
    retransmissoes += radio.getARC();
  }
  const float segundos = (micros() - inicio) / 1e6;

  Serial.print(F("Entregues: "));
  Serial.print(100.0 * confirmados / PACOTES_POR_RODADA, 1);
  Serial.print(F("% | retransmissoes/pacote: "));
  Serial.print((float)retransmissoes / PACOTES_POR_RODADA, 2);
  Serial.print(F(" | "));
  Serial.print(PACOTES_POR_RODADA / segundos, 0);
  Serial.print(F(" pacotes/s ("));
  Serial.print(confirmados * 28.0 * 8 / segundos / 1000, 1);  // 28 bytes úteis por pacote
  Serial.println(F(" kbit/s de imagem)"));
  delay(500);
}
