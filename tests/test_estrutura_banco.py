"""Etapa 3: scripts/estrutura_banco.py cria o esquema real e e inocuo em bancos ja completos."""
import hashlib
import sqlite3
import unittest

from tests import BANCO
from tests import helpers as h

# Esquema do banco em uso (nome, tipo, NOT NULL) das tabelas tratadas pelo script, sem id_empresa
# (acrescentada por scripts/migrar_banco.py).
ESPERADO = {
    "pessoa": {("id_pessoa", "INTEGER", 0), ("tipo_pessoa", "TEXT", 1), ("identificador", "TEXT", 0),
               ("codigo_pessoa", "TEXT", 0), ("nome", "TEXT", 0)},
    "reconhecimento": {("id_reconhecimento", "INTEGER", 0), ("id_pessoa", "INTEGER", 1),
                       ("imagem_referencia", "TEXT", 0), ("criado_em", "TEXT", 1), ("embedding", "TEXT", 0)},
    "identificacao": {("id_identificacao", "INTEGER", 0), ("id_pessoa", "INTEGER", 1),
                      ("identificador", "TEXT", 1), ("data_cadastro", "TEXT", 1)},
}

# Esquema criado pela versao anterior do script, com dados ficticios.
ESQUEMA_ANTIGO = """
CREATE TABLE pessoa (id_pessoa INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, codigo_pessoa TEXT,
    tipo_pessoa TEXT NOT NULL DEFAULT 'desconhecido');
CREATE TABLE reconhecimento (id_reconhecimento INTEGER PRIMARY KEY AUTOINCREMENT, id_pessoa INTEGER NOT NULL,
    embedding TEXT NOT NULL);
CREATE TABLE local (id_local INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL);
CREATE TABLE movimentacao (id_movimentacao INTEGER PRIMARY KEY AUTOINCREMENT, id_pessoa INTEGER NOT NULL,
    id_local INTEGER NOT NULL, data_entrada TEXT NOT NULL, hora_entrada TEXT NOT NULL, data_saida TEXT,
    hora_saida TEXT, tempo_dentro INTEGER, id_sessao INTEGER);
INSERT INTO pessoa (nome, codigo_pessoa, tipo_pessoa) VALUES ('Desconhecido', 'DESC-001', 'desconhecido');
INSERT INTO pessoa (nome, codigo_pessoa, tipo_pessoa) VALUES ('Pessoa Ficticia Antiga', 'P-1', 'funcionario');
INSERT INTO reconhecimento (id_pessoa, embedding) VALUES (2, '[0.1, 0.2]');
INSERT INTO local (nome) VALUES ('Local Ficticio');
INSERT INTO movimentacao (id_pessoa, id_local, data_entrada, hora_entrada) VALUES (2, 1, '2020-01-01', '08:00:00');
"""


def colunas(con, tabela):
    return {(r[1], r[2], r[3]) for r in con.execute(f"PRAGMA table_info({tabela})") if r[1] != "id_empresa"}


def retrato(banco=BANCO):
    """Esquema completo, hash do conteudo de cada tabela e integrity_check."""
    con = sqlite3.connect(banco)
    try:
        esquema = sorted(con.execute("SELECT type, name, tbl_name, sql FROM sqlite_master").fetchall(),
                         key=lambda r: tuple(str(x) for x in r))
        dados = {}
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            soma = hashlib.sha256()
            for linha in con.execute(f'SELECT * FROM "{t}" ORDER BY rowid'):
                soma.update(repr(linha).encode())
            dados[t] = soma.hexdigest()
        return esquema, dados, con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()


class BancoNovoTest(unittest.TestCase):
    def setUp(self):
        h.apagar_banco()

    def test_esquema_igual_ao_do_banco_em_uso(self):
        h.rodar_script("estrutura_banco.py")
        con = sqlite3.connect(BANCO)
        try:
            for tabela, esperado in ESPERADO.items():
                self.assertEqual(colunas(con, tabela), esperado, tabela)
            self.assertTrue(con.execute("SELECT 1 FROM pragma_index_list('identificacao') WHERE \"unique\" = 1")
                            .fetchone(), "identificador deve ser UNIQUE")
            self.assertEqual(con.execute("SELECT nome FROM pessoa WHERE id_pessoa = 1").fetchone(), ("Desconhecido",))
            self.assertEqual(con.execute("SELECT id_local FROM local").fetchall(), [(1,)])
        finally:
            con.close()

    def test_idempotente(self):
        h.rodar_script("estrutura_banco.py")
        antes = retrato()
        h.rodar_script("estrutura_banco.py")
        self.assertEqual(retrato(), antes)


class BancoAntigoTest(unittest.TestCase):
    def test_atualiza_sem_perder_dados(self):
        h.apagar_banco()
        con = sqlite3.connect(BANCO)
        con.executescript(ESQUEMA_ANTIGO)
        con.close()
        _, dados_antes, _ = retrato()
        h.rodar_script("estrutura_banco.py")
        con = sqlite3.connect(BANCO)
        try:
            nomes = lambda t: {c[0] for c in colunas(con, t)}
            self.assertIn("identificador", nomes("pessoa"))
            self.assertTrue({"imagem_referencia", "criado_em"} <= nomes("reconhecimento"))
            self.assertEqual(nomes("identificacao"), {c[0] for c in ESPERADO["identificacao"]})
            self.assertEqual(con.execute("SELECT nome, codigo_pessoa, tipo_pessoa FROM pessoa ORDER BY id_pessoa")
                             .fetchall(), [("Desconhecido", "DESC-001", "desconhecido"),
                                           ("Pessoa Ficticia Antiga", "P-1", "funcionario")])
            self.assertEqual(con.execute("SELECT id_pessoa, embedding, criado_em FROM reconhecimento").fetchall(),
                             [(2, "[0.1, 0.2]", None)])
        finally:
            con.close()
        _, dados_depois, integridade = retrato()
        self.assertEqual(integridade, "ok")
        for tabela in ("local", "movimentacao"):
            self.assertEqual(dados_depois[tabela], dados_antes[tabela], tabela)


class BancoCompletoTest(unittest.TestCase):
    """Banco ficticio no estado do banco em uso (migrado, com painel e dados): o script nao muda nada."""

    def test_nada_muda(self):
        h.criar_banco(2)
        h.inserir_pessoa("Pessoa Ficticia Completa", 1)
        h.inserir_movimentacoes(1, h.MES_ATUAL, 3)
        h.cliente(1).get("/")                 # tabelas criadas pelo painel e virada de mes
        con = sqlite3.connect(BANCO)
        try:
            con.execute("INSERT INTO identificacao (id_pessoa, identificador, data_cadastro) "
                        "VALUES (2, 'PESSOA-FICT', '2026-01-01 00:00:00')")
            con.execute("INSERT INTO reconhecimento (id_pessoa, imagem_referencia, criado_em, embedding) "
                        "VALUES (2, NULL, '2026-01-01 00:00:00', '[0.5]')")
            con.commit()
        finally:
            con.close()
        antes = retrato()
        h.rodar_script("estrutura_banco.py")
        depois = retrato()
        self.assertEqual(depois[0], antes[0], "esquema mudou")
        self.assertEqual(depois[1], antes[1], "dados mudaram")
        self.assertEqual(depois[2], "ok")


if __name__ == "__main__":
    unittest.main()
