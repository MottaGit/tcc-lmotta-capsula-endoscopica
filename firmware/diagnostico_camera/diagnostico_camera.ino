// =============================================================================
//  Diagnóstico da câmera OV7670  -  Arduino Mega 2560
//
//  Ler pixels com digitalRead (~4 us por leitura) é lento demais para o PCLK
//  e só produz ruído. Por isso este diagnóstico verifica cada sinal
//  separadamente, com a mesma ligação do transmissor (docs/hardware.md):
//
//    1. XCLK de 8 MHz no pino 9
//    2. I2C/SCCB: lê os registradores de identificação (PID 0x76, VER 0x73)
//    3. VSYNC: quadros por segundo
//    4. HREF: linhas por quadro
//    5. PCLK: alternando
//    6. Barramento D0..D7: aponta bits presos em 0 ou em 1 (fio solto)
//
//  Abra o Monitor Serial a 115200 baud. Não precisa de bibliotecas extras.
// =============================================================================

#include <Wire.h>

#if !defined(__AVR_ATmega2560__)
#error "Este diagnóstico usa a pinagem do Arduino Mega 2560."
#endif

#define CAM_VSYNC() (PINE & (1 << 4))  // pino 2
#define CAM_HREF()  (PINE & (1 << 5))  // pino 3
#define CAM_PCLK()  (PINB & (1 << 6))  // pino 12
#define CAM_DADOS() (PINA)             // pinos 22..29

const uint8_t ENDERECO_SCCB = 0x21;
const uint8_t REG_PID = 0x0A, REG_VER = 0x0B, REG_COM7 = 0x12, REG_CLKRC = 0x11;

void iniciarXclk() {
  // Timer2 em PWM rápido com TOP = 1: saída OC2B (pino 9) alterna a 16 MHz / 2 = 8 MHz.
  pinMode(9, OUTPUT);
  TCCR2A = _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
  TCCR2B = _BV(WGM22) | _BV(CS20);
  OCR2A = 1;
  OCR2B = 0;
}

int lerRegistrador(uint8_t reg) {
  Wire.beginTransmission(ENDERECO_SCCB);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return -1;  // o SCCB não aceita repeated start
  if (Wire.requestFrom(ENDERECO_SCCB, (uint8_t)1) != 1) return -1;
  return Wire.read();
}

bool escreverRegistrador(uint8_t reg, uint8_t valor) {
  Wire.beginTransmission(ENDERECO_SCCB);
  Wire.write(reg);
  Wire.write(valor);
  return Wire.endTransmission() == 0;
}

void resultado(bool ok, const __FlashStringHelper *texto) {
  Serial.print(ok ? F("[ OK ]  ") : F("[FALHA] "));
  Serial.print(texto);
}

// Conta bordas de subida de VSYNC durante `ms` milissegundos.
uint16_t contarQuadros(uint16_t ms) {
  uint16_t quadros = 0;
  bool anterior = CAM_VSYNC();
  const uint32_t inicio = millis();
  while (millis() - inicio < ms) {
    const bool agora = CAM_VSYNC();
    if (agora && !anterior) quadros++;
    anterior = agora;
  }
  return quadros;
}

// Conta HREFs entre dois VSYNCs e acumula os bits do barramento durante as linhas.
bool medirQuadro(uint16_t &linhas, uint8_t &bitsEmUm, uint8_t &bitsEmZero, bool &pclkAlterna) {
  linhas = 0;
  bitsEmUm = 0x00;    // OR de todas as amostras
  bitsEmZero = 0xFF;  // AND de todas as amostras
  uint8_t pclkVisto = 0;
  const uint32_t inicio = millis();
  while (!CAM_VSYNC()) if (millis() - inicio > 3000) return false;
  while (CAM_VSYNC())  if (millis() - inicio > 3000) return false;
  bool hrefAnterior = false;
  while (!CAM_VSYNC()) {
    if (millis() - inicio > 6000) return false;
    const bool href = CAM_HREF();
    if (href) {
      const uint8_t d = CAM_DADOS();
      bitsEmUm |= d;
      bitsEmZero &= d;
      pclkVisto |= CAM_PCLK() ? 2 : 1;
      if (!hrefAnterior) linhas++;
    }
    hrefAnterior = href;
  }
  pclkAlterna = pclkVisto == 3;
  return true;
}

void diagnosticar() {
  Serial.println(F("\n=== Diagnostico da camera OV7670 ==="));
  resultado(true, F("XCLK de 8 MHz gerado no pino 9 (confira o divisor para ~3,3 V)\n"));

  const int pid = lerRegistrador(REG_PID);
  const int ver = lerRegistrador(REG_VER);
  const bool i2cOk = pid == 0x76 && ver == 0x73;
  resultado(i2cOk, F("I2C/SCCB: PID=0x"));
  Serial.print(pid, HEX);
  Serial.print(F(" VER=0x"));
  Serial.print(ver, HEX);
  Serial.println(i2cOk ? F(" (OV7670)") : F(" -> esperado 0x76/0x73: SIOD->20, SIOC->21, pull-ups, 3,3 V, XCLK"));
  if (!i2cOk) return;

  // Configuração de fábrica (VGA, YUV) com o relógio interno dividido por 4:
  // ~2,5 quadros/s, devagar o bastante para medir tudo por varredura.
  escreverRegistrador(REG_COM7, 0x80);  // reset
  delay(300);
  escreverRegistrador(REG_CLKRC, 0x80 | 3);
  delay(300);

  const uint16_t quadros = contarQuadros(2000);
  resultado(quadros > 0, F("VSYNC: "));
  Serial.print(quadros / 2.0, 1);
  Serial.println(quadros ? F(" quadros/s") : F(" quadros/s -> sem VSYNC: confira o pino 2 e o XCLK"));
  if (!quadros) return;

  uint16_t linhas;
  uint8_t emUm, emZero;
  bool pclkOk;
  if (!medirQuadro(linhas, emUm, emZero, pclkOk)) {
    resultado(false, F("tempo esgotado medindo o quadro\n"));
    return;
  }
  resultado(linhas >= 470 && linhas <= 490, F("HREF: "));
  Serial.print(linhas);
  Serial.println(F(" linhas por quadro (esperado ~480 em VGA; pino 3)"));
  resultado(pclkOk, pclkOk ? F("PCLK alternando (pino 12)\n") : F("PCLK parado: confira o pino 12\n"));

  bool barramentoOk = true;
  for (uint8_t bit = 0; bit < 8; bit++) {
    const bool preso0 = !(emUm & (1 << bit));
    const bool preso1 = emZero & (1 << bit);
    if (preso0 || preso1) {
      barramentoOk = false;
      resultado(false, F("D"));
      Serial.print(bit);
      Serial.print(preso0 ? F(" sempre 0") : F(" sempre 1"));
      Serial.print(F(" -> confira o fio do pino "));
      Serial.println(22 + bit);
    }
  }
  if (barramentoOk) resultado(true, F("Barramento D0..D7: todos os bits variam\n"));
}

void setup() {
  Serial.begin(115200);
  iniciarXclk();
  Wire.begin();
  digitalWrite(SDA, LOW);  // sem pull-ups internos de 5 V
  digitalWrite(SCL, LOW);
  delay(100);
}

void loop() {
  diagnosticar();
  delay(5000);
}
