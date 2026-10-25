"""Painel web: autenticacao, CSRF, logout, limite de tentativas e isolamento entre empresas
no dashboard e na pagina de pessoas (em processo, com o banco temporario)."""
import unittest

from tests import helpers as h
from overflow.web import dashboard


class AutenticacaoTest(unittest.TestCase):
    def setUp(self):
        h.criar_banco(1)
        self.c = h.cliente(entrar=False)

    def entrar(self, senha):
        token = h.token_csrf(self.c.get("/login").get_data(as_text=True))
        return self.c.post("/login", data={"email": h.EMAIL_ADMIN, "senha": senha, "csrf_token": token})

    def test_sem_login_redireciona(self):
        for url in ("/", "/pessoas", "/resumos", f"/resumo/{h.MES_ATUAL}"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/login", r.headers["Location"])

    def test_login_sem_csrf_recusado(self):
        r = self.c.post("/login", data={"email": h.EMAIL_ADMIN, "senha": h.SENHA_ADMIN})
        self.assertEqual(r.status_code, 400)

    def test_senha_errada(self):
        r = self.entrar("errada")
        self.assertEqual(r.status_code, 200)
        self.assertIn("inválidos", r.get_data(as_text=True))
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_limite_de_tentativas(self):
        for _ in range(dashboard.LOGIN_MAX_FALHAS):
            self.entrar("errada")
        self.assertEqual(self.entrar(h.SENHA_ADMIN).status_code, 429)

    def test_logout(self):
        self.assertEqual(self.entrar(h.SENHA_ADMIN).status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)
        self.c.get("/logout")
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_post_sem_csrf_nao_executa(self):
        h.inserir_movimentacoes(1, h.MES_ATUAL, 2)
        self.entrar(h.SENHA_ADMIN)
        r = self.c.post("/arquivar", data={"ate": "2999-12-31", "confirmacao": "ARQUIVAR"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao")[0][0], 2)


class IsolamentoTest(unittest.TestCase):
    def setUp(self):
        h.criar_banco(2)
        self.pessoa_a = h.inserir_pessoa("Pessoa Ficticia Alfa", 1)
        self.pessoa_b = h.inserir_pessoa("Pessoa Ficticia Beta", 2)
        h.inserir_movimentacoes(1, h.MES_ATUAL, 2, id_pessoa=self.pessoa_a)
        h.inserir_movimentacoes(2, h.MES_ATUAL, 4, id_pessoa=self.pessoa_b)

    def test_dashboard_mostra_so_a_empresa(self):
        html = h.cliente(1).get("/").get_data(as_text=True)
        self.assertIn("Pessoa Ficticia Alfa", html)
        self.assertNotIn("Pessoa Ficticia Beta", html)

    def test_pessoas_mostra_so_a_empresa(self):
        html = h.cliente(2).get("/pessoas").get_data(as_text=True)
        self.assertIn("Pessoa Ficticia Beta", html)
        self.assertNotIn("Pessoa Ficticia Alfa", html)

    def atualizar(self, c, id_pessoa, tipo):
        token = h.token_csrf(c.get("/pessoas").get_data(as_text=True))
        return c.post("/pessoas/atualizar", data={"id_pessoa": id_pessoa, "tipo_pessoa": tipo, "csrf_token": token})

    def test_nao_altera_pessoa_de_outra_empresa(self):
        self.assertEqual(self.atualizar(h.cliente(1), self.pessoa_b, "visitante").status_code, 302)
        self.assertEqual(h.consultar("SELECT tipo_pessoa FROM pessoa WHERE id_pessoa = ?", (self.pessoa_b,)),
                         [("funcionario",)])

    def test_altera_pessoa_da_propria_empresa(self):
        self.atualizar(h.cliente(1), self.pessoa_a, "visitante")
        self.assertEqual(h.consultar("SELECT tipo_pessoa FROM pessoa WHERE id_pessoa = ?", (self.pessoa_a,)),
                         [("visitante",)])

    def test_tipo_invalido_recusado(self):
        self.assertEqual(self.atualizar(h.cliente(1), self.pessoa_a, "administrador").status_code, 400)

    def test_arquivar_exige_confirmacao(self):
        c = h.cliente(1)
        token = h.token_csrf(c.get("/").get_data(as_text=True))
        c.post("/arquivar", data={"ate": "2999-12-31", "confirmacao": "", "csrf_token": token})
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao WHERE id_empresa = 1")[0][0], 2)


if __name__ == "__main__":
    unittest.main()
