"""Integracao das quatro etapas e protecoes da propria suite de testes."""
import ast
import re
import sqlite3
import unittest
from pathlib import Path

from tests import BANCO, BANCO_REAL, PASTA_TEMP, RAIZ, banco_permitido, caminho_do_banco
from tests import helpers as h

try:
    from overflow.visao import camera
except ImportError as erro:
    camera, ERRO_CAMERA = None, erro
else:
    ERRO_CAMERA = None


HASH_WERKZEUG = r"(?:scrypt:\d+:\d+:\d+|pbkdf2:sha\d+(?::\d+)?)\$[A-Za-z0-9]+\$[0-9a-f]{32,}"


@unittest.skipIf(camera is None, f"camera indisponivel: {ERRO_CAMERA}")
class FluxoCompletoTest(unittest.TestCase):
    """Banco novo so com os scripts do projeto -> cadastro -> camera -> painel e resumo da empresa."""

    def test_fluxo(self):
        h.criar_banco(2)
        r = h.cadastrar_com_cv2_falso(OVERFLOW_ID_EMPRESA="2")
        self.assertEqual(r.returncode, 0, r.stderr)

        camera.banco = sqlite3.connect(BANCO)
        try:
            camera.cursor = camera.banco.cursor()
            camera.id_sessao, camera.id_empresa = 1, 2
            camera.entradas = camera.saidas = 0
            camera.movimentacoes_ativas, camera.ultima_zona, camera.ids_contados = {}, {}, set()
            for tid in (1, 2):
                camera.registrar_cruzamento(tid, "cima")
                camera.registrar_cruzamento(tid, "baixo")
            camera.registrar_cruzamento(1, "cima")
        finally:
            camera.banco.close()
        self.assertEqual((camera.entradas, camera.saidas), (2, 1))

        b, a = h.cliente(2), h.cliente(1)
        self.assertIn("Pessoa Ficticia", b.get("/pessoas").get_data(as_text=True))
        self.assertNotIn("Pessoa Ficticia", a.get("/pessoas").get_data(as_text=True))
        self.assertEqual(h.consultar("SELECT id_empresa, COUNT(*) FROM movimentacao GROUP BY id_empresa"), [(2, 2)])
        html = b.get(f"/resumo/{h.MES_ATUAL}").get_data(as_text=True)
        self.assertIn("<h3>Entradas</h3><p>2</p>", html)
        self.assertNotIn("<h3>Entradas</h3><p>2</p>", a.get(f"/resumo/{h.MES_ATUAL}").get_data(as_text=True))


class PontosDeEntradaTest(unittest.TestCase):
    def test_modulos_importaveis(self):
        r = h.python(["-c", "import wsgi; from overflow.visao import camera, contador; "
                      "from overflow.web import dashboard; from overflow.db import empresa, reconhecimento, "
                      "repositorio, resumo, sessao; print(callable(camera.main), callable(dashboard.main))"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["True", "True"])

    def test_scripts_existem(self):
        for nome in ("estrutura_banco.py", "indice_banco.py", "migrar_banco.py", "consultar.py",
                     "redefinir_senha.py", "cadastrar_pessoa_rosto.py"):
            self.assertTrue((RAIZ / "scripts" / nome).is_file(), nome)


class SintaxeTest(unittest.TestCase):
    def test_todo_o_codigo_do_projeto(self):
        ignorar = {".venv", "_backup", "__pycache__", ".git"}
        arquivos = [p for p in RAIZ.rglob("*.py") if not ignorar & set(p.relative_to(RAIZ).parts)]
        self.assertGreater(len(arquivos), 25)
        for p in arquivos:
            ast.parse(p.read_text(encoding="utf-8"), str(p))


class ProtecaoDaSuiteTest(unittest.TestCase):
    def test_banco_configurado_e_temporario(self):
        from overflow import config
        self.assertEqual(Path(config.BANCO).resolve(), BANCO.resolve())
        self.assertEqual(BANCO.resolve().parent, PASTA_TEMP.resolve())
        self.assertNotEqual(BANCO.resolve(), BANCO_REAL)

    def test_trava_recusa_o_banco_real(self):
        # A trava recusa antes de abrir: nenhuma das formas chega a tocar o arquivo.
        for alvo in (BANCO_REAL, str(BANCO_REAL), f"{BANCO_REAL.as_uri()}?mode=ro",
                     f"file:{BANCO_REAL}?mode=ro&immutable=1"):
            self.assertEqual(caminho_do_banco(alvo), BANCO_REAL, alvo)
            with self.assertRaises(RuntimeError):
                sqlite3.connect(alvo, uri=str(alvo).startswith("file:"))

    def test_trava_recusa_qualquer_banco_fora_da_pasta_temporaria(self):
        fora = PASTA_TEMP.parent / "overflow_fora_da_pasta_de_teste" / "banco.db"
        self.assertFalse(banco_permitido(fora.resolve()))
        with self.assertRaises(RuntimeError):
            sqlite3.connect(fora)
        self.assertFalse(fora.parent.exists())
        self.assertTrue(banco_permitido(None))                  # :memory:
        self.assertTrue(banco_permitido((PASTA_TEMP / "x.db").resolve()))

    def test_subprocessos_exigem_banco_temporario(self):
        with self.assertRaises(RuntimeError):
            h.env_teste(banco=BANCO_REAL)

    def test_pasta_tests_so_tem_codigo(self):
        pasta = RAIZ / "tests"
        proibidos = [p.name for p in pasta.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix.lower() != ".py"]
        self.assertEqual(proibidos, [])
        for p in pasta.glob("*.py"):
            texto = p.read_text(encoding="utf-8")
            # Nenhuma senha/chave literal: os testes geram as suas na hora.
            self.assertIsNone(re.search(r"(?im)(senha|password|secret_key)\w*\s*=\s*['\"][^'\"]{6,}['\"]\s*$", texto),
                              p.name)
            # Hash no formato do werkzeug (scrypt:N:r:p$sal$hex ou pbkdf2:sha256:N$sal$hex).
            self.assertIsNone(re.search(HASH_WERKZEUG, texto), p.name)


if __name__ == "__main__":
    unittest.main()
