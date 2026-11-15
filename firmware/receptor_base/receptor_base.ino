// =============================================================================
//  Receptor (estação externa)  -  Arduino Uno / Nano
//
//  nRF24L01+ -> USB. Não interpreta a imagem: só repassa cada pacote de 32
//  bytes ao PC precedido de dois bytes de sincronismo (0xA5 0x5A). Quem
//  valida o CRC-8, reordena e remonta os quadros é o software de PC
//  (software/capsula/receber.py). O CRC físico do rádio já descarta pacotes
//  corrompidos no ar.
//
//  Biblioteca: RF24 (TMRh20) pelo Gerenciador de Bibliotecas.
//  Ligações: nRF24L01+ VCC->3V3, GND->GND, CE->9, CSN->10, SCK->13,
//            MOSI->11, MISO->12, IRQ sem ligação (ver docs/hardware.md).
// =============================================================================

#include <SPI.h>
#include <RF24.h>

const uint8_t PINO_CE  = 9;
const uint8_t PINO_CSN = 10;

// Precisam ser iguais aos de firmware/transmissor_capsula/config.h
#define CANAL_RADIO 76
#define TAXA_RADIO  RF24_1MBPS
static const uint8_t ENDERECO_RADIO[6] = "CAPS1";

// 1 Mbaud é exato com cristal de 16 MHz e transmite um pacote (34 bytes) em
// 0,34 ms, mais rápido do que o rádio entrega (~0,7 ms por pacote).
const uint32_t BAUD = 1000000;

const uint8_t TAMANHO_PACOTE = 32;
const uint8_t SYNC0 = 0xA5;
const uint8_t SYNC1 = 0x5A;

RF24 radio(PINO_CE, PINO_CSN);
uint8_t pacote[TAMANHO_PACOTE];

void setup() {
  Serial.begin(BAUD);
  if (!radio.begin()) {
    Serial.println(F("ERRO: nRF24L01+ nao encontrado (SPI, CE/CSN, 3,3 V)"));
    for (;;) {}
  }
  radio.setChannel(CANAL_RADIO);
  radio.setDataRate(TAXA_RADIO);
  radio.setPALevel(RF24_PA_LOW);  // potência dos ACKs
  radio.setPayloadSize(TAMANHO_PACOTE);
  radio.setCRCLength(RF24_CRC_16);
  radio.setAutoAck(true);
  radio.openReadingPipe(1, ENDERECO_RADIO);
  radio.startListening();
  // Texto solto é ignorado pelo software de PC (não contém o SYNC).
  Serial.println(F("Receptor da capsula pronto"));
}

void loop() {
  while (radio.available()) {
    radio.read(pacote, TAMANHO_PACOTE);
    Serial.write(SYNC0);
    Serial.write(SYNC1);
    Serial.write(pacote, TAMANHO_PACOTE);
  }
}
