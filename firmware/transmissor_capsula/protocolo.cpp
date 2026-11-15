#include "protocolo.h"

namespace protocolo {

namespace {
const uint8_t RICE_ESCAPE = 24;  // quocientes >= 24 vão como literal de 9 bits
const uint8_t RICE_K_MAX = 7;

// Diferença para o vizinho, mapeada para inteiro sem sinal: 0,-1,1,-2.. -> 0,1,2,3..
inline uint16_t zigzag(int16_t diferenca) {
  return diferenca >= 0 ? (uint16_t)(2 * diferenca) : (uint16_t)(-2 * diferenca - 1);
}
}  // namespace

uint8_t crc8(const uint8_t *dados, uint8_t n, uint8_t crc) {
  while (n--) {
    crc ^= *dados++;
    for (uint8_t i = 0; i < 8; i++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

uint16_t tamanhoRle(const uint8_t *pixels, uint16_t n) {
  uint16_t tamanho = 0;
  uint16_t i = 0;
  while (i < n) {
    const uint8_t valor = pixels[i];
    uint16_t repeticoes = 1;
    while (i + repeticoes < n && repeticoes < 255 && pixels[i + repeticoes] == valor) repeticoes++;
    tamanho += 2;
    i += repeticoes;
  }
  return tamanho;
}

// Regra do LOCO-I/JPEG-LS: menor k com n * 2^k >= soma dos resíduos.
uint8_t escolherKRice(const uint8_t *pixels, uint16_t n) {
  uint32_t soma = 0;
  uint8_t anterior = 0;
  for (uint16_t i = 0; i < n; i++) {
    soma += zigzag((int16_t)pixels[i] - anterior);
    anterior = pixels[i];
  }
  uint8_t k = 0;
  while (k < RICE_K_MAX && ((uint32_t)n << k) < soma) k++;
  return k;
}

uint16_t tamanhoRice(const uint8_t *pixels, uint16_t n, uint8_t k) {
  uint32_t bits = 3;  // o próprio k
  uint8_t anterior = 0;
  for (uint16_t i = 0; i < n; i++) {
    const uint16_t q = zigzag((int16_t)pixels[i] - anterior) >> k;
    anterior = pixels[i];
    bits += (q >= RICE_ESCAPE) ? (RICE_ESCAPE + 9) : (q + 1 + k);
  }
  return (uint16_t)((bits + 7) / 8);
}

uint8_t Empacotador::enviarLinha(uint8_t y, const uint8_t *pixels, uint8_t compressao, bool ultima) {
  falhas_ = 0;

  // Escolhe a menor representação permitida (empate: a mais simples).
  uint8_t codificacao = COD_BRUTO;
  uint16_t melhor = LARGURA;
  if (compressao >= COMP_RLE) {
    const uint16_t t = tamanhoRle(pixels, LARGURA);
    if (t < melhor) { melhor = t; codificacao = COD_RLE; }
  }
  uint8_t k = 0;
  if (compressao >= COMP_RICE) {
    k = escolherKRice(pixels, LARGURA);
    const uint16_t t = tamanhoRice(pixels, LARGURA, k);
    if (t < melhor) { melhor = t; codificacao = COD_RICE; }
  }
  ultimaCodificacao_ = codificacao;

  uint8_t *payload = pacote_ + TAMANHO_CABECALHO;
  flags_ = FLAG_SOL;
  usados_ = 0;
  payload[usados_++] = y;
  payload[usados_++] = codificacao;

  if (codificacao == COD_RLE) {
    uint16_t i = 0;
    while (i < LARGURA) {
      const uint8_t valor = pixels[i];
      uint8_t repeticoes = 1;
      while (i + repeticoes < LARGURA && repeticoes < 255 && pixels[i + repeticoes] == valor) repeticoes++;
      if (usados_ > TAMANHO_PAYLOAD - 2) despachar();  // um par nunca é dividido
      payload[usados_++] = repeticoes;
      payload[usados_++] = valor;
      i += repeticoes;
    }
  } else if (codificacao == COD_RICE) {
    codificarRice(pixels, k);
  } else {
    for (uint16_t i = 0; i < LARGURA; i++) adicionarByte(pixels[i]);
  }

  flags_ |= FLAG_EOL | (ultima ? FLAG_EOF : 0);
  despachar();
  return falhas_;
}

// Fluxo: 3 bits de k + para cada pixel o resíduo zigue-zague em Golomb-Rice
// (quociente em unário terminado por 0, depois k bits). Bits do mais
// significativo para o menos; o último byte é completado com zeros.
void Empacotador::codificarRice(const uint8_t *pixels, uint8_t k) {
  acumulador_ = 0;
  bitsNoAcumulador_ = 0;
  adicionarBits(k, 3);
  uint8_t anterior = 0;
  for (uint16_t i = 0; i < LARGURA; i++) {
    const uint16_t v = zigzag((int16_t)pixels[i] - anterior);
    anterior = pixels[i];
    const uint16_t q = v >> k;
    if (q >= RICE_ESCAPE) {
      for (uint8_t j = 0; j < RICE_ESCAPE; j++) adicionarBits(1, 1);
      adicionarBits(v, 9);
    } else {
      for (uint16_t j = 0; j < q; j++) adicionarBits(1, 1);
      adicionarBits(0, 1);
      adicionarBits(v, k);  // só os k bits baixos são escritos
    }
  }
  if (bitsNoAcumulador_) adicionarByte(acumulador_ << (8 - bitsNoAcumulador_));
}

void Empacotador::adicionarBits(uint16_t valor, uint8_t quantidade) {
  while (quantidade--) {
    acumulador_ = (acumulador_ << 1) | ((valor >> quantidade) & 1);
    if (++bitsNoAcumulador_ == 8) {
      adicionarByte(acumulador_);
      acumulador_ = 0;
      bitsNoAcumulador_ = 0;
    }
  }
}

void Empacotador::adicionarByte(uint8_t valor) {
  if (usados_ == TAMANHO_PAYLOAD) despachar();
  pacote_[TAMANHO_CABECALHO + usados_++] = valor;
}

void Empacotador::despachar() {
  const uint8_t flags = flags_ | (seq_ == 0 ? FLAG_SOF : 0);
  memset(pacote_ + TAMANHO_CABECALHO + usados_, 0, TAMANHO_PAYLOAD - usados_);
  pacote_[0] = (flags & 0xF0) | ((seq_ >> 8) & 0x0F);
  pacote_[1] = seq_ & 0xFF;
  pacote_[2] = quadro_;
  pacote_[3] = crc8(pacote_ + TAMANHO_CABECALHO, TAMANHO_PAYLOAD, crc8(pacote_, 3));
  if (!envio_(pacote_)) falhas_++;
  seq_++;
  usados_ = 0;
  flags_ = 0;
}

}  // namespace protocolo
