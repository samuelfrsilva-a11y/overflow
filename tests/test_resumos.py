"""Etapa 2: resumos mensais isolados por empresa, com os resumos antigos preservados."""
import json
import re
import sqlite3
import unittest

from werkzeug.security import generate_password_hash

from tests import BANCO
from tests import helpers as h
from overflow.db import resumo


def entradas_na_pagina(html):
    return int(re.search(r"<h3>Entradas</h3><p>(\d+)</p>", html).group(1))


def linhas_da_lista(html):
    """[(mes, entradas)] da tabela de /resumos."""
    return [(m, int(n)) for m, n in re.findall(r"<td>(\d{4}-\d{2})</td>\s*<td>(\d+)</td>", html)]


def resumo_legado(mes, entradas):
    """Resumo completo gerado pela propria funcao, como os gravados antes da separacao por empresa."""
    mem = sqlite3.connect(":memory:")
    try:
        mem.execute("""CREATE TABLE movimentacao (id_pessoa INTEGER, data_entrada TEXT, hora_entrada TEXT,
                       data_saida TEXT, tempo_dentro INTEGER)""")
        mem.executemany("INSERT INTO movimentacao VALUES (1, ?, '10:00:00', NULL, NULL)",
                        [(f"{mes}-{1 + i % 28:02d}",) for i in range(entradas)])
        return resumo.gerar_resumo(mem, mes)
    finally:
        mem.close()


class ResumoPorEmpresaTest(unittest.TestCase):
    """Empresa 1: 3 entradas no mes anterior e 2 no atual. Empresa 2: 5 e 4."""

    def setUp(self):
        h.criar_banco(2)
        h.inserir_movimentacoes(1, h.MES_ANTERIOR, 3)
        h.inserir_movimentacoes(1, h.MES_ATUAL, 2)
        h.inserir_movimentacoes(2, h.MES_ANTERIOR, 5)
        h.inserir_movimentacoes(2, h.MES_ATUAL, 4)

    def test_mes_anterior_separado(self):
        a, b = h.cliente(1), h.cliente(2)
        self.assertEqual(linhas_da_lista(a.get("/resumos").get_data(as_text=True)), [(h.MES_ANTERIOR, 3)])
        self.assertEqual(entradas_na_pagina(a.get(f"/resumo/{h.MES_ANTERIOR}").get_data(as_text=True)), 3)
        self.assertEqual(linhas_da_lista(b.get("/resumos").get_data(as_text=True)), [(h.MES_ANTERIOR, 5)])
        self.assertEqual(entradas_na_pagina(b.get(f"/resumo/{h.MES_ANTERIOR}").get_data(as_text=True)), 5)

    def test_mes_atual_parcial_separado(self):
        self.assertEqual(entradas_na_pagina(h.cliente(1).get(f"/resumo/{h.MES_ATUAL}").get_data(as_text=True)), 2)
        self.assertEqual(entradas_na_pagina(h.cliente(2).get(f"/resumo/{h.MES_ATUAL}").get_data(as_text=True)), 4)

    def test_arquivamento_preservado(self):
        h.cliente(1).get("/")                         # abrir o painel dispara a virada de mes
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao WHERE substr(data_entrada,1,7) = ?",
                                     (h.MES_ANTERIOR,))[0][0], 0)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao_arquivo WHERE substr(data_entrada,1,7) = ?",
                                     (h.MES_ANTERIOR,))[0][0], 8)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao")[0][0], 6)

    def test_arquivar_manual_so_da_propria_empresa(self):
        c = h.cliente(1)
        token = h.token_csrf(c.get("/").get_data(as_text=True))
        c.post("/arquivar", data={"ate": "2999-12-31", "confirmacao": "ARQUIVAR", "csrf_token": token})
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao WHERE id_empresa = 1")[0][0], 0)
        self.assertEqual(h.consultar("SELECT COUNT(*) FROM movimentacao WHERE id_empresa = 2")[0][0], 4)

    def test_virada_idempotente(self):
        con = sqlite3.connect(BANCO)
        try:
            resumo.virar_mes(con)
            resumo.virar_mes(con)
            resumo.garantir_tabelas(con)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM resumo_mensal_empresa").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM resumo_mensal").fetchone()[0], 0)
        finally:
            con.close()

    def test_mes_sem_dados_e_mes_invalido(self):
        a = h.cliente(1)
        self.assertEqual(a.get("/resumo/2001-01").status_code, 200)
        self.assertEqual(a.get("/resumo/2001-13").status_code, 404)

    def test_resumo_de_outra_empresa_invisivel(self):
        con = sqlite3.connect(BANCO)
        try:
            con.execute("INSERT INTO resumo_mensal_empresa VALUES (2, '2020-05', '2020-06-01 00:00:00', ?)",
                        (json.dumps(resumo_legado("2020-05", 99)),))
            con.commit()
        finally:
            con.close()
        a = h.cliente(1)
        self.assertNotIn("2020-05", a.get("/resumos").get_data(as_text=True))
        self.assertNotIn("<h3>Entradas</h3><p>99</p>", a.get("/resumo/2020-05").get_data(as_text=True))


class ResumoLegadoTest(unittest.TestCase):
    """Situacao do banco real: resumo antigo sem empresa e registros arquivados sem id_empresa."""

    def setUp(self):
        h.criar_banco(1)
        con = sqlite3.connect(BANCO)
        try:
            con.execute("INSERT INTO resumo_mensal VALUES ('2020-09', '2020-10-01 00:00:00', ?)",
                        (json.dumps(resumo_legado("2020-09", 190), ensure_ascii=False),))
            con.execute("""INSERT INTO movimentacao_arquivo (id_movimentacao, id_pessoa, id_local, data_entrada,
                           hora_entrada, arquivado_em, motivo) VALUES (1, 1, 1, '2020-09-15', '10:00:00',
                           '2020-10-01 00:00:00', 'virada de mes (2020-09)')""")
            con.commit()
        finally:
            con.close()
        h.inserir_movimentacoes(1, h.MES_ATUAL, 2)

    def test_resumo_antigo_continua_visivel(self):
        a = h.cliente(1)
        self.assertIn(("2020-09", 190), linhas_da_lista(a.get("/resumos").get_data(as_text=True)))
        self.assertEqual(entradas_na_pagina(a.get("/resumo/2020-09").get_data(as_text=True)), 190)

    def test_tabela_antiga_e_arquivo_intactos(self):
        antes = h.consultar("SELECT * FROM resumo_mensal"), h.consultar("SELECT * FROM movimentacao_arquivo")
        h.cliente(1).get("/resumos")
        self.assertEqual((h.consultar("SELECT * FROM resumo_mensal"), h.consultar("SELECT * FROM movimentacao_arquivo")),
                         antes)

    def test_empresa_criada_depois_nao_ve_resumo_antigo(self):
        h.cliente(1).get("/resumos")                  # copia o resumo antigo para a empresa 1
        con = sqlite3.connect(BANCO)
        try:
            con.execute("INSERT INTO empresa (id_empresa, nome) VALUES (2, 'Empresa Ficticia 2')")
            con.execute("INSERT INTO usuario (id_empresa, email, senha) VALUES (2, ?, ?)",
                        (h.email_empresa(2), generate_password_hash(h.SENHA_OUTRAS)))
            con.commit()
        finally:
            con.close()
        self.assertIn(("2020-09", 190), linhas_da_lista(h.cliente(1).get("/resumos").get_data(as_text=True)))
        self.assertEqual(linhas_da_lista(h.cliente(2).get("/resumos").get_data(as_text=True)), [])


class BancoNaoMigradoTest(unittest.TestCase):
    """Sem empresa nem id_empresa, vale o comportamento antigo (tabela resumo_mensal)."""

    def test_comportamento_antigo(self):
        con = sqlite3.connect(":memory:")
        try:
            con.execute("""CREATE TABLE movimentacao (id_movimentacao INTEGER PRIMARY KEY, id_pessoa INTEGER,
                id_local INTEGER, data_entrada TEXT, hora_entrada TEXT, data_saida TEXT, hora_saida TEXT,
                tempo_dentro INTEGER, id_sessao INTEGER)""")
            con.execute("INSERT INTO movimentacao (id_pessoa, id_local, data_entrada, hora_entrada) "
                        "VALUES (1, 1, '2020-01-05', '09:00:00')")
            con.commit()
            self.assertEqual(resumo.virar_mes(con, h.HOJE), ["2020-01"])
            self.assertEqual(resumo.carregar_resumo(con, "2020-01")["entradas"], 1)
            self.assertEqual([r["mes"] for r in resumo.listar_resumos(con)], ["2020-01"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM movimentacao_arquivo").fetchone()[0], 1)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
