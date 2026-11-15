import unittest

from capsula import protocolo as p
from capsula import rle


def linha_gradiente(passo: int = 1) -> bytes:
    return bytes((x // passo) % 256 for x in range(p.LARGURA))


class TestCrc8(unittest.TestCase):
    def test_valor_de_verificacao_padrao(self):
        # valor de verificação oficial do CRC-8/SMBUS para "123456789"
        self.assertEqual(p.crc8(b"123456789"), 0xF4)

    def test_crc_incremental(self):
        self.assertEqual(p.crc8(b"6789", p.crc8(b"12345")), p.crc8(b"123456789"))


class TestPacote(unittest.TestCase):
    def test_ida_e_volta(self):
        original = p.Pacote(p.SOF | p.SOL, 0xABC, 7, bytes(range(28)))
        bruto = original.to_bytes()
        self.assertEqual(len(bruto), 32)
        self.assertEqual(bruto[0], 0xA0 | 0x0A)
        self.assertEqual(bruto[1], 0xBC)
        self.assertEqual(p.Pacote.from_bytes(bruto), original)

    def test_crc_detecta_corrupcao_no_cabecalho_e_no_payload(self):
        bruto = bytearray(p.Pacote(0, 5, 1, bytes(28)).to_bytes())
        for posicao in (0, 1, 2, 4, 31):
            corrompido = bytearray(bruto)
            corrompido[posicao] ^= 0x01
            with self.assertRaises(p.ErroPacote):
                p.Pacote.from_bytes(bytes(corrompido))

    def test_vetor_de_referencia(self):
        # Mesmo vetor usado em docs/protocolo.md para conferir o firmware.
        pacote = p.Pacote(p.SOF | p.SOL, 0, 0, bytes([0, p.COD_BRUTO]) + bytes(range(26)))
        esperado = "a0 00 00 97 00 00 " + " ".join(f"{i:02x}" for i in range(26))
        self.assertEqual(pacote.to_bytes().hex(" "), esperado)


class TestRle(unittest.TestCase):
    def test_ida_e_volta(self):
        for dados in (b"", b"\x05", bytes(320), linha_gradiente(), linha_gradiente(7), b"\x01\x01\x02" * 50):
            self.assertEqual(rle.decodificar(rle.codificar(dados)), dados)
            self.assertEqual(rle.tamanho_codificado(dados), len(rle.codificar(dados)))

    def test_repeticao_maxima_255(self):
        codificado = rle.codificar(bytes(320))
        self.assertEqual(codificado, bytes([255, 0, 65, 0]))

    def test_par_zero_e_preenchimento(self):
        self.assertEqual(rle.decodificar(bytes([3, 9, 0, 0, 5, 5])), b"\x09\x09\x09")


class TestEmpacotador(unittest.TestCase):
    def test_linha_bruta_usa_12_pacotes_com_flags_corretas(self):
        emp = p.Empacotador(3)
        pacotes = emp.linha(10, linha_gradiente(), comprimir=False)
        self.assertEqual(len(pacotes), 12)
        self.assertTrue(pacotes[0].tem(p.SOF) and pacotes[0].tem(p.SOL))
        self.assertEqual(pacotes[0].payload[:2], bytes([10, p.COD_BRUTO]))
        self.assertTrue(pacotes[-1].tem(p.EOL) and not pacotes[-1].tem(p.EOF))
        self.assertEqual([q.seq for q in pacotes], list(range(12)))
        self.assertTrue(all(q.quadro == 3 for q in pacotes))

    def test_ultima_linha_marca_eof_e_sof_so_no_primeiro(self):
        emp = p.Empacotador(0)
        primeiro = emp.linha(0, linha_gradiente(), comprimir=False)
        ultimo = emp.linha(1, linha_gradiente(), ultima=True, comprimir=False)
        self.assertTrue(ultimo[-1].tem(p.EOF))
        self.assertFalse(any(q.tem(p.SOF) for q in primeiro[1:] + ultimo))

    def test_rle_so_quando_for_menor(self):
        emp = p.Empacotador(0)
        uniforme = emp.linha(0, bytes(320))
        self.assertEqual(len(uniforme), 1)
        self.assertEqual(uniforme[0].payload[1], p.COD_RLE)
        ruidosa = emp.linha(1, linha_gradiente())  # nenhuma repetição: RLE dobraria o tamanho
        self.assertEqual(ruidosa[0].payload[1], p.COD_BRUTO)

    def test_pior_caso_cabe_em_12_bits_de_sequencia(self):
        emp = p.Empacotador(0)
        for y in range(p.ALTURA):
            emp.linha(y, linha_gradiente(), ultima=(y == p.ALTURA - 1))
        self.assertEqual(emp.seq, 240 * 12)
        self.assertLessEqual(emp.seq - 1, p.SEQ_MAX)


class TestLeitorSerial(unittest.TestCase):
    def test_ignora_texto_e_ressincroniza(self):
        pacotes = p.Empacotador(1).linha(0, linha_gradiente(), comprimir=False)
        fluxo = b"Receptor pronto\r\n" + b"".join(p.enquadrar(q) for q in pacotes)
        fluxo = fluxo[:60] + b"\xA5\x5Alixo" + fluxo[60:]  # SYNC falso no meio do caminho
        leitor = p.LeitorSerial()
        recebidos = []
        for i in range(0, len(fluxo), 7):  # chega aos pedaços, como na serial
            recebidos += list(leitor.alimentar(fluxo[i:i + 7]))
        self.assertGreaterEqual(len(recebidos), len(pacotes) - 1)
        self.assertTrue(set(q.seq for q in recebidos) >= set(range(2, 12)))


if __name__ == "__main__":
    unittest.main()
