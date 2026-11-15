/*
  Teste mínimo da câmera OV7670
  Valida sinais VSYNC, HREF, PCLK e leitura de pixels nos pinos A0–A3, 4–7
  Gera XCLK de ~8 MHz no pino 11
*/

#define VSYNC 3
#define PCLK 2
#define HREF 8

void setup() {
  Serial.begin(115200);
  Serial.println("Iniciando teste OV7670...");

  // Configura pinos de controle
  pinMode(VSYNC, INPUT);
  
  pinMode(PCLK, INPUT);
  pinMode(HREF, INPUT);

  // Pinos de dados
  for (int i = A0; i <= A3; i++) pinMode(i, INPUT);
  for (int i = 4; i <= 7; i++) pinMode(i, INPUT);

  // Gera clock XCLK de 8 MHz no pino 11 (Timer2 - OC2A)
  pinMode(11, OUTPUT);
  TCCR2A = _BV(COM2A0) | _BV(WGM21) | _BV(WGM20); // Toggle OC2A, Fast PWM
  TCCR2B = _BV(WGM22) | _BV(CS20);                // Sem prescaler
  OCR2A = 0;  // Frequência máxima (~8 MHz)

  delay(1000);
  Serial.println("Clock XCLK ativo. Aguardando VSYNC...");
}

void loop() {
  // Espera início de frame
  while (digitalRead(VSYNC) == LOW);
  while (digitalRead(VSYNC) == HIGH);

  Serial.println("Frame detectado. Lendo 10 linhas...");

  // Captura 10 linhas para teste
  for (int linha = 0; linha < 10; linha++) {
    while (digitalRead(HREF) == LOW);
    while (digitalRead(HREF) == HIGH) {
      while (digitalRead(PCLK) == LOW);
      byte pixel = 0;
      // Bits 0–3 em A0–A3
      for (int i = 0; i < 4; i++) {
        pixel |= (digitalRead(A0 + i) << i);
      }
      // Bits 4–7 em D4–D7
      for (int i = 0; i < 4; i++) {
        pixel |= (digitalRead(4 + i) << (i + 4));
      }
      Serial.print(pixel, HEX);
      Serial.print(" ");
      while (digitalRead(PCLK) == HIGH);
    }
    Serial.println();
  }

  Serial.println("Fim da leitura. Reiniciando em 1s...\n");
  delay(1000);
}
