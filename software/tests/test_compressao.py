import random
import unittest

from capsula import compressao, rice, rle
from capsula import protocolo as p
from capsula.remontagem import Remontador
from capsula.simular import cena_sintetica, pacotes_do_quadro


def linhas_de_teste():
    rng = random.Random(3)
    yield bytes(320)                                                  # uniforme
    yield bytes(range(256)) + bytes(range(64))                        # gradiente
    yield bytes(rng.randrange(256) for _ in range(320))              # ruído puro (pior caso)
    yield bytes(min(255, 100 + int(rng.gauss(0, 3))) for _ in range(320))  # ruído de sensor
    yield bytes([0, 255] * 160)                                       # saltos máximos (escape)
    cena = cena_sintetica(0, passo=1)
    yield cena[120 * 320:121 * 320]


class TestRice(unittest.TestCase):
    def test_ida_e_volta(self):
        for linha in linhas_de_teste():
            codificado = rice.codificar_linha(linha)
            pixels, usados = rice.decodificar_linha(codificado, len(linha))
            self.assertEqual(pixels, linha)
            self.assertEqual(usados, len(codificado))
            self.assertEqual(rice.tamanho_linha(linha), len(codificado))

    def test_zigzag(self):
        self.assertEqual([rice.zigzag(d) for d in (0, -1, 1, -2, 2)], [0, 1, 2, 3, 4])
        for d in range(-255, 256):
            self.assertEqual(rice.dezigzag(rice.zigzag(d)), d)

    def test_dados_truncados_devolvem_o_que_da_para_ler(self):
        linha = bytes(i // 3 for i in range(320))
        codificado = rice.codificar_linha(linha)
        pixels, _ = rice.decodificar_linha(codificado[: len(codificado) // 2], len(linha))
        self.assertGreater(len(pixels), 0)
        self.assertLess(len(pixels), len(linha))
        self.assertEqual(pixels, linha[: len(pixels)])

    def test_k_pela_regra_do_loco_i(self):
        self.assertEqual(rice.escolher_k([0] * 10), 0)
        self.assertEqual(rice.escolher_k([4] * 10), 2)
        self.assertEqual(rice.escolher_k([1000] * 10), rice.K_MAX)


class TestOutrosAlgoritmos(unittest.TestCase):
    def test_dpcm_e_med_sao_reversiveis(self):
        acima = None
        for linha in linhas_de_teste():
            self.assertEqual(compressao.desfazer_dpcm(compressao.dpcm(linha)), linha)
            codificado = compressao.med_rice_codificar(linha, acima)
            self.assertEqual(compressao.med_rice_decodificar(codificado, len(linha), acima), linha)
            acima = linha

    def test_rice_ganha_do_rle_com_ruido_e_rle_ganha_em_areas_uniformes(self):
        uniforme = compressao.avaliar(cena_sintetica(0, ruido=2.0, passo=8))
        ruidosa = compressao.avaliar(cena_sintetica(0, ruido=2.5, passo=1))
        self.assertGreater(uniforme["RLE"].reducao(), 0.3)
        self.assertLess(ruidosa["RLE"].reducao(), 0.05)
        self.assertGreater(ruidosa["DPCM + Rice"].reducao(), 0.4)
        self.assertLess(ruidosa["DPCM + Rice"].pacotes_quadro, ruidosa["RLE"].pacotes_quadro)


class TestProtocoloComRice(unittest.TestCase):
    def test_escolhe_a_menor_codificacao(self):
        self.assertEqual(p.escolher_codificacao(bytes(320), "rice")[0], p.COD_RLE)
        ruido = cena_sintetica(0, ruido=2.5, passo=1)[100 * 320:101 * 320]
        self.assertEqual(p.escolher_codificacao(ruido, "rle")[0], p.COD_BRUTO)
        self.assertEqual(p.escolher_codificacao(ruido, "rice")[0], p.COD_RICE)
        self.assertEqual(p.escolher_codificacao(ruido, "bruto")[0], p.COD_BRUTO)

    def test_quadro_com_rice_remonta_identico_e_usa_menos_pacotes(self):
        cena = cena_sintetica(0, ruido=2.5, passo=1)
        com_rice = pacotes_do_quadro(cena, 5, "rice")
        so_rle = pacotes_do_quadro(cena, 5, "rle")
        self.assertLess(len(com_rice), 0.7 * len(so_rle))
        rem = Remontador()
        prontos = []
        for pacote in com_rice:
            prontos += rem.adicionar(pacote)
        self.assertEqual(len(prontos), 1)  # entregue assim que o último pacote chega
        q = prontos[0]
        self.assertEqual(bytes(q.pixels), cena)
        self.assertGreater(q.linhas_rice, 200)
        self.assertGreater(q.reducao, 0.4)

    def test_perda_em_linha_rice_preserva_o_comeco_da_linha(self):
        cena = cena_sintetica(0, ruido=2.5, passo=1)
        pacotes = pacotes_do_quadro(cena, 0, "rice", passo=1)
        # segundo pacote da linha 0 (que tem vários pacotes) se perde
        alvo = pacotes[1]
        self.assertFalse(alvo.tem(p.SOL))
        rem = Remontador()
        for pacote in pacotes:
            if pacote is not alvo:
                rem.adicionar(pacote)
        q = rem.finalizar()
        self.assertEqual(q.linhas_parciais, 1)
        self.assertEqual(q.pixels[:40], cena[:40])
        self.assertEqual(q.pixels[320:], cena[320:])


if __name__ == "__main__":
    unittest.main()
