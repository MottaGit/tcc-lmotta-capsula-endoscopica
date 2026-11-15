import random
import unittest

from capsula import protocolo as p
from capsula.remontagem import Remontador
from capsula.simular import canal, cena_sintetica, pacotes_do_quadro


class TestRemontagem(unittest.TestCase):
    def setUp(self):
        self.cena = cena_sintetica(0)

    def remontar(self, pacotes, **kwargs):
        rem = Remontador(**kwargs)
        quadros = []
        for pacote in pacotes:
            quadros += rem.adicionar(pacote)
        final = rem.finalizar()
        if final:
            quadros.append(final)
        return quadros

    def test_sem_perdas_reconstroi_identico_com_e_sem_rle(self):
        for comprimir in (True, False):
            quadros = self.remontar(pacotes_do_quadro(self.cena, 9, comprimir, passo=4))
            self.assertEqual(len(quadros), 1)
            q = quadros[0]
            self.assertEqual(bytes(q.pixels), self.cena)
            self.assertEqual(q.quadro_id, 9)
            self.assertEqual(q.taxa_sucesso, 1.0)
            self.assertEqual(q.linhas_completas, 240)
            self.assertTrue(q.fim_recebido)
            if comprimir:
                self.assertGreater(q.linhas_rle, 0)
                self.assertGreater(q.reducao_rle, 0.2)
            else:
                self.assertEqual(q.linhas_rle, 0)
                self.assertAlmostEqual(q.reducao_rle, 0.0)

    def test_fora_de_ordem_e_duplicados(self):
        pacotes = pacotes_do_quadro(self.cena, 1, True, passo=1)
        rng = random.Random(1)
        embaralhados = pacotes + pacotes[:50]
        rng.shuffle(embaralhados)
        q = self.remontar(embaralhados)[0]
        self.assertEqual(bytes(q.pixels), self.cena)
        self.assertEqual(q.duplicados, 50)

    def test_perdas_afetam_so_as_linhas_atingidas(self):
        pacotes = pacotes_do_quadro(self.cena, 2, False, passo=1)
        # linha bruta = 12 pacotes: seq 5 está no meio da linha 0, seq 24 é o SOL da linha 2
        perdidos = {5, 24}
        restantes = [q for q in pacotes if q.seq not in perdidos]
        q = self.remontar(restantes)[0]
        self.assertEqual(q.pacotes_recebidos, len(pacotes) - 2)
        self.assertEqual(q.pacotes_esperados, len(pacotes))
        self.assertEqual((q.linhas_completas, q.linhas_parciais, q.linhas_faltantes), (238, 1, 1))
        # só o trecho perdido da linha 0 fica preto (pacote 5 = bytes 138..165)
        self.assertEqual(q.pixels[138:166], bytes(28))
        self.assertEqual(q.pixels[:138], self.cena[:138])
        self.assertEqual(q.pixels[166:640], self.cena[166:640])
        self.assertEqual(q.pixels[640:960], bytes(320))
        self.assertEqual(q.pixels[960:], self.cena[960:])

    def test_linha_perdida_usa_quadro_anterior_quando_pedido(self):
        primeiro = pacotes_do_quadro(self.cena, 0, True, passo=1)
        segundo = [q for q in pacotes_do_quadro(self.cena, 1, True, passo=1)
                   if not (q.tem(p.SOL) and q.payload[0] == 100)]
        quadros = self.remontar(primeiro + segundo, faltantes="anterior")
        self.assertEqual(len(quadros), 2)
        self.assertEqual(quadros[1].linhas_faltantes, 1)
        self.assertEqual(bytes(quadros[1].pixels), self.cena)

    def test_canal_com_perda_realista(self):
        rng = random.Random(7)
        pacotes = canal(pacotes_do_quadro(self.cena, 4, True, passo=4), 0.03, 0.01, 0.01, rng)
        q = self.remontar(pacotes)[0]
        self.assertGreater(q.taxa_sucesso, 0.9)
        self.assertLess(q.taxa_sucesso, 1.0)
        self.assertGreater(q.linhas_completas, 180)

    def test_varios_quadros_em_sequencia(self):
        pacotes = []
        for n in range(3):
            pacotes += pacotes_do_quadro(cena_sintetica(n), n, True, passo=4)
        quadros = self.remontar(pacotes)
        self.assertEqual([q.quadro_id for q in quadros], [0, 1, 2])
        for n, q in enumerate(quadros):
            self.assertEqual(bytes(q.pixels), cena_sintetica(n))


if __name__ == "__main__":
    unittest.main()
