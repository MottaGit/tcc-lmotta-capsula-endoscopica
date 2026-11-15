#include "protocolo.h"

namespace protocolo {

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

uint8_t Empacotador::enviarLinha(uint8_t y, const uint8_t *pixels, bool comprimir, bool ultima) {
  falhas_ = 0;
  ultimaRle_ = comprimir && tamanhoRle(pixels, LARGURA) < LARGURA;

  uint8_t *payload = pacote_ + TAMANHO_CABECALHO;
  flags_ = FLAG_SOL;
  usados_ = 0;
  payload[usados_++] = y;
  payload[usados_++] = ultimaRle_ ? COD_RLE : COD_BRUTO;

  if (ultimaRle_) {
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
  } else {
    for (uint16_t i = 0; i < LARGURA; i++) {
      if (usados_ == TAMANHO_PAYLOAD) despachar();
      payload[usados_++] = pixels[i];
    }
  }

  flags_ |= FLAG_EOL | (ultima ? FLAG_EOF : 0);
  despachar();
  return falhas_;
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
