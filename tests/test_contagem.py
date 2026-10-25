"""overflow/visao/contador.py: contagem por travessia de linha (sem OpenCV, webcam nem banco)."""
import unittest

from overflow.visao.contador import Contador


def passar(contador, tid, ys, t0=0.0):
    """Um rastro descendo/subindo pelo centro de um frame 640x480 (linha em y=240, faixa morta de 24 px)."""
    eventos = []
    for i, y in enumerate(ys):
        _, ev = contador.atualizar(t0 + i * 0.1, [(tid, (300, y - 50, 340, y + 50))], 640, 480)
        eventos += ev
    return eventos


class ContadorTest(unittest.TestCase):
    def test_entrada_e_saida(self):
        c = Contador()
        ev = passar(c, 1, [100, 150, 200, 300, 350])
        self.assertEqual((c.entradas, c.saidas, c.dentro), (1, 0, 1))
        self.assertIn("abrir", [e.tipo for e in ev])
        ev = passar(c, 1, [350, 300, 200, 150], t0=1.0)
        self.assertEqual((c.entradas, c.saidas, c.dentro), (1, 1, 0))
        self.assertIn("fechar", [e.tipo for e in ev])

    def test_parado_na_faixa_morta_nao_conta(self):
        c = Contador()
        passar(c, 1, [235, 240, 245, 238, 242])
        self.assertEqual((c.entradas, c.saidas), (0, 0))

    def test_caixa_pequena_ignorada(self):
        c = Contador()
        for i, y in enumerate([100, 150, 200, 300, 350]):
            c.atualizar(i * 0.1, [(1, (300, y - 10, 310, y + 10))], 640, 480)
        self.assertEqual(c.entradas, 0)


if __name__ == "__main__":
    unittest.main()
