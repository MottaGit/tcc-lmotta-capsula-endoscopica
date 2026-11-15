// =============================================================================
//  Protocolo lógico de empacotamento (ver docs/protocolo.md)
//
//  Mesma especificação de software/capsula/protocolo.py e rice.py: qualquer
//  mudança aqui precisa ser feita também lá (os testes do Python são a
//  referência, com vetores conferidos em docs/protocolo.md).
// =============================================================================
#pragma once
#include <Arduino.h>

namespace protocolo {

const uint8_t  TAMANHO_PACOTE    = 32;  // payload máximo do nRF24L01+
const uint8_t  TAMANHO_CABECALHO = 4;
const uint8_t  TAMANHO_PAYLOAD   = TAMANHO_PACOTE - TAMANHO_CABECALHO;  // 28
const uint16_t LARGURA           = 320;
const uint8_t  ALTURA            = 240;

// 4 bits altos do byte 0 (o nome EOF já é usado pela biblioteca C)
const uint8_t FLAG_SOF = 0x80;  // primeiro pacote da imagem
const uint8_t FLAG_EOF = 0x40;  // último pacote da imagem
const uint8_t FLAG_SOL = 0x20;  // primeiro pacote de uma linha
const uint8_t FLAG_EOL = 0x10;  // último pacote de uma linha

// Codificação de cada linha (2º byte do primeiro pacote da linha)
const uint8_t COD_BRUTO = 0;    // 320 bytes de luminância
const uint8_t COD_RLE   = 1;    // pares (repetições 1..255, valor)
const uint8_t COD_RICE  = 2;    // DPCM + Golomb-Rice (fluxo de bits)

// Quais codificações o transmissor pode usar. Em cada linha vai a menor
// delas, e só se for menor que a bruta.
enum Compressao : uint8_t { COMP_NENHUMA = 0, COMP_RLE = 1, COMP_RICE = 2 };

// Enquadramento na serial: SYNC0 SYNC1 + 32 bytes do pacote
const uint8_t SYNC0 = 0xA5;
const uint8_t SYNC1 = 0x5A;

// Etapa 1 (dados brutos): marcador antes de cada quadro de 76.800 bytes
const uint8_t MARCADOR_QUADRO_BRUTO[8] = {0x00, 0xFF, 0x00, 0xFF, 'Q', 'V', 'G', 'A'};

// CRC-8, polinômio 0x07, valor inicial `crc` (CRC-8/SMBUS quando crc = 0).
uint8_t crc8(const uint8_t *dados, uint8_t n, uint8_t crc = 0);

// Tamanho em bytes da linha codificada (sem gerar a codificação).
uint16_t tamanhoRle(const uint8_t *pixels, uint16_t n);
uint8_t  escolherKRice(const uint8_t *pixels, uint16_t n);
uint16_t tamanhoRice(const uint8_t *pixels, uint16_t n, uint8_t k);

// Envia um pacote de 32 bytes. Devolve false se ele não foi entregue.
typedef bool (*FuncaoEnvio)(const uint8_t *pacote);

class Empacotador {
 public:
  explicit Empacotador(FuncaoEnvio envio) : envio_(envio) {}

  void novoQuadro(uint8_t id) { quadro_ = id; seq_ = 0; }

  // Codifica uma linha e envia os pacotes. Cada linha começa em um pacote
  // novo; o primeiro leva [y, codificação] antes dos dados. `ultima` marca
  // EOF. Devolve quantos pacotes não foram entregues.
  uint8_t enviarLinha(uint8_t y, const uint8_t *pixels, uint8_t compressao, bool ultima);

  uint16_t pacotesNoQuadro() const { return seq_; }
  uint8_t ultimaCodificacao() const { return ultimaCodificacao_; }

 private:
  void adicionarByte(uint8_t valor);
  void adicionarBits(uint16_t valor, uint8_t quantidade);
  void codificarRice(const uint8_t *pixels, uint8_t k);
  void despachar();

  FuncaoEnvio envio_;
  uint8_t  pacote_[TAMANHO_PACOTE];
  uint8_t  usados_ = 0;   // bytes de payload já preenchidos
  uint8_t  flags_ = 0;
  uint8_t  quadro_ = 0;
  uint16_t seq_ = 0;      // 12 bits; o pior caso é 240 x 12 = 2880 pacotes
  uint8_t  falhas_ = 0;
  uint8_t  ultimaCodificacao_ = COD_BRUTO;
  uint8_t  acumulador_ = 0;  // escrita de bits (Rice)
  uint8_t  bitsNoAcumulador_ = 0;
};

}  // namespace protocolo
