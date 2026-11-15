# Driver da câmera OV7670 (LiveOV7670)

Subconjunto da biblioteca **LiveOV7670**, de Indrek Luuk
(<https://github.com/indrekluuk/LiveOV7670>), usado aqui só para configurar a
câmera via I2C/SCCB (QVGA, YUV422, divisor de clock) e gerar o XCLK de 8 MHz.
A leitura dos pixels, o empacotamento e a transmissão são do firmware deste
projeto.

Fica dentro de `src/` para que o sketch compile sem instalar nada além da
biblioteca RF24. Alteração em relação ao original: `CameraOV7670::setRegister`
não tinha `return` (comportamento indefinido em C++).
