"""Scripts de manutencao do banco: migracao segura, consulta e verificacao de conta."""
import hashlib
import unittest

from tests import BANCO
from tests import helpers as h


class MigracaoTest(unittest.TestCase):
    def setUp(self):
        h.apagar_banco()

    def test_sem_senha_de_admin_nao_altera_nada(self):
        h.rodar_script("estrutura_banco.py")
        antes = hashlib.sha256(BANCO.read_bytes()).hexdigest()
        r = h.rodar_script("migrar_banco.py", checar=False, OVERFLOW_ADMIN_PASSWORD="")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(hashlib.sha256(BANCO.read_bytes()).hexdigest(), antes)

    def test_senha_curta_recusada(self):
        h.rodar_script("estrutura_banco.py")
        r = h.rodar_script("migrar_banco.py", checar=False, OVERFLOW_ADMIN_PASSWORD="curta")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("curta", r.stdout + r.stderr)

    def test_sem_banco_nao_cria_arquivo(self):
        r = h.rodar_script("migrar_banco.py", checar=False, OVERFLOW_ADMIN_PASSWORD=h.SENHA_ADMIN)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(BANCO.exists())

    def test_senha_do_admin_gravada_como_hash(self):
        h.criar_banco(1)
        senha = h.consultar("SELECT senha FROM usuario WHERE email = ?", (h.EMAIL_ADMIN,))[0][0]
        self.assertNotEqual(senha, h.SENHA_ADMIN)
        self.assertRegex(senha, r"^(scrypt|pbkdf2):")


class ConsultaTest(unittest.TestCase):
    def test_consultar_e_indices(self):
        h.criar_banco(1)
        h.inserir_movimentacoes(1, h.MES_ATUAL, 2)
        h.rodar_script("indice_banco.py")                      # idempotente
        r = h.rodar_script("consultar.py")
        self.assertEqual(r.stdout.count("Movimentação:"), 2)

    def test_redefinir_senha_verificar_e_somente_leitura(self):
        h.criar_banco(1)
        antes = hashlib.sha256(BANCO.read_bytes()).hexdigest()
        r = h.rodar_script("redefinir_senha.py", "--email", h.EMAIL_ADMIN, "--verificar")
        self.assertIn("integrity_check: ok", r.stdout)
        self.assertNotIn(h.SENHA_ADMIN, r.stdout + r.stderr)
        self.assertEqual(hashlib.sha256(BANCO.read_bytes()).hexdigest(), antes)


if __name__ == "__main__":
    unittest.main()
