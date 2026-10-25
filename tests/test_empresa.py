"""Etapa 1: movimentacoes da camera e pessoas cadastradas associadas a empresa correta."""
import hashlib
import sqlite3
import unittest

from tests import BANCO
from tests import helpers as h
from overflow.db.empresa import EmpresaIndefinida, resolver_empresa

try:
    from overflow.visao import camera
except ImportError as erro:          # instalacao so do painel (requirements-web.txt)
    camera, ERRO_CAMERA = None, erro
else:
    ERRO_CAMERA = None


def sha_banco():
    return hashlib.sha256(BANCO.read_bytes()).hexdigest()


class ResolverEmpresaTest(unittest.TestCase):
    def test_unica_empresa_e_usada(self):
        h.criar_banco(1)
        con = sqlite3.connect(BANCO)
        try:
            self.assertEqual(resolver_empresa(con), 1)
        finally:
            con.close()

    def test_varias_empresas_recusa_sem_escolher(self):
        h.criar_banco(2)
        con = sqlite3.connect(BANCO)
        try:
            with self.assertRaisesRegex(EmpresaIndefinida, "OVERFLOW_ID_EMPRESA"):
                resolver_empresa(con)
        finally:
            con.close()

    def test_empresa_configurada(self):
        h.criar_banco(2)
        con = sqlite3.connect(BANCO)
        try:
            self.assertEqual(resolver_empresa(con, 2), 2)
            with self.assertRaises(EmpresaIndefinida):
                resolver_empresa(con, 99)
        finally:
            con.close()

    def test_tabela_empresa_vazia(self):
        con = sqlite3.connect(":memory:")
        try:
            con.execute("CREATE TABLE empresa (id_empresa INTEGER PRIMARY KEY, nome TEXT)")
            with self.assertRaises(EmpresaIndefinida):
                resolver_empresa(con)
        finally:
            con.close()

    def test_banco_sem_tabela_empresa(self):
        con = sqlite3.connect(":memory:")
        try:
            self.assertIsNone(resolver_empresa(con))
            with self.assertRaises(EmpresaIndefinida):
                resolver_empresa(con, 1)
        finally:
            con.close()


@unittest.skipIf(camera is None, f"camera indisponivel: {ERRO_CAMERA}")
class CameraCruzamentoTest(unittest.TestCase):
    """registrar_cruzamento sem webcam nem YOLO, gravando no banco temporario."""

    def setUp(self):
        h.criar_banco(1)
        camera.banco = sqlite3.connect(BANCO)
        camera.cursor = camera.banco.cursor()
        camera.id_sessao, camera.id_empresa = 1, 1
        camera.entradas = camera.saidas = 0
        camera.movimentacoes_ativas, camera.ultima_zona, camera.ids_contados = {}, {}, set()

    def tearDown(self):
        camera.banco.close()

    def movs(self):
        return camera.cursor.execute(
            "SELECT id_empresa, id_pessoa, id_local, id_sessao, data_saida, hora_entrada, tempo_dentro "
            "FROM movimentacao ORDER BY id_movimentacao").fetchall()

    def test_entrada_e_saida_com_empresa(self):
        camera.registrar_cruzamento(7, "cima")
        camera.registrar_cruzamento(7, "baixo")
        self.assertEqual((camera.entradas, camera.saidas), (1, 0))
        linhas = self.movs()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0][:5], (1, 1, 1, 1, None))
        self.assertRegex(linhas[0][5], r"^\d\d:\d\d:\d\d$")
        camera.registrar_cruzamento(7, "cima")
        self.assertEqual((camera.entradas, camera.saidas), (1, 1))
        self.assertIsNotNone(self.movs()[0][4])
        self.assertGreaterEqual(self.movs()[0][6], 0)

    def test_contagem_preservada(self):
        camera.registrar_cruzamento(3, "cima")
        camera.registrar_cruzamento(3, "baixo")
        camera.registrar_cruzamento(3, "baixo")      # repetido: nao conta de novo
        camera.registrar_cruzamento(5, "baixo")
        camera.registrar_cruzamento(5, "cima")       # subiu sem ter entrado: nao conta
        self.assertEqual((camera.entradas, camera.saidas), (1, 0))
        self.assertEqual(len(self.movs()), 1)

    def test_finalizar_abertas(self):
        camera.registrar_cruzamento(9, "cima")
        camera.registrar_cruzamento(9, "baixo")
        camera.finalizar_movimentacoes_abertas()
        self.assertIsNotNone(self.movs()[0][4])
        self.assertEqual(camera.movimentacoes_ativas, {})

    def test_banco_nao_migrado_grava_sem_coluna(self):
        camera.banco.close()
        con = sqlite3.connect(":memory:")
        con.execute("""CREATE TABLE movimentacao (id_movimentacao INTEGER PRIMARY KEY, id_pessoa INTEGER,
            id_local INTEGER, data_entrada TEXT, hora_entrada TEXT, data_saida TEXT, hora_saida TEXT,
            tempo_dentro INTEGER, id_sessao INTEGER)""")
        camera.banco, camera.cursor, camera.id_empresa = con, con.cursor(), None
        camera.registrar_cruzamento(1, "cima")
        camera.registrar_cruzamento(1, "baixo")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM movimentacao").fetchone()[0], 1)

    def test_movimentacao_aparece_no_painel(self):
        camera.registrar_cruzamento(8, "cima")
        camera.registrar_cruzamento(8, "baixo")
        self.assertEqual(h.cliente(1).get("/").status_code, 200)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao WHERE id_empresa = 1")[0][0], 1)


class CameraInicioTest(unittest.TestCase):
    def test_varias_empresas_para_antes_de_gravar(self):
        h.criar_banco(2)
        antes = sha_banco()
        r = h.python(["-m", "overflow.visao.camera"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("mais de uma empresa", r.stdout)
        self.assertNotIn("OVERFLOW - CONTAGEM", r.stdout)    # nao chegou a abrir a camera
        self.assertEqual(sha_banco(), antes)                  # nem a sessao foi criada


class CadastroTest(unittest.TestCase):
    def test_unica_empresa(self):
        h.criar_banco(1)
        r = h.cadastrar_com_cv2_falso()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cadastrada com sucesso", r.stdout)
        self.assertEqual(h.consultar("SELECT id_empresa FROM pessoa WHERE nome = 'Pessoa Ficticia'"), [(1,)])
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM reconhecimento")[0][0], 1)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM identificacao")[0][0], 1)

    def test_varias_empresas_recusa_sem_gravar(self):
        h.criar_banco(2)
        antes = sha_banco()
        r = h.cadastrar_com_cv2_falso()
        self.assertIn("mais de uma empresa", r.stdout)
        self.assertNotIn("cadastrada com sucesso", r.stdout)
        self.assertEqual(sha_banco(), antes)

    def test_empresa_configurada(self):
        h.criar_banco(2)
        r = h.cadastrar_com_cv2_falso(OVERFLOW_ID_EMPRESA="2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(h.consultar("SELECT id_empresa FROM pessoa WHERE nome = 'Pessoa Ficticia'"), [(2,)])

    def test_foto_com_dois_rostos_recusada(self):
        h.criar_banco(1)
        r = h.cadastrar_com_cv2_falso(n_rostos=2)
        self.assertIn("apenas uma pessoa", r.stdout)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM pessoa WHERE nome = 'Pessoa Ficticia'")[0][0], 0)

    def test_pessoa_aparece_so_na_propria_empresa(self):
        h.criar_banco(2)
        self.assertEqual(h.cadastrar_com_cv2_falso(OVERFLOW_ID_EMPRESA="2").returncode, 0)
        self.assertIn("Pessoa Ficticia", h.cliente(2).get("/pessoas").get_data(as_text=True))
        self.assertNotIn("Pessoa Ficticia", h.cliente(1).get("/pessoas").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
