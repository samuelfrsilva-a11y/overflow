"""Empresa (cliente) dona dos registros gravados pela camera e pelo cadastro.

O painel so mostra linhas com o id_empresa do usuario logado; registros gravados
sem empresa ficariam invisiveis. Por isso a camera e o cadastro resolvem a
empresa antes de gravar.
"""
import sqlite3

from overflow import config


class EmpresaIndefinida(Exception):
    """Nao foi possivel decidir a qual empresa os registros pertencem."""


def _tabela_existe(con, nome):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def resolver_empresa(con: sqlite3.Connection, id_configurado=None):
    """Retorna o id_empresa a usar, ou None se o banco ainda nao foi migrado (sem tabela empresa).

    Ordem: OVERFLOW_ID_EMPRESA (conferido no banco) > unica empresa existente.
    Com varias empresas e nenhuma configurada, recusa em vez de adivinhar.
    """
    if id_configurado is None:
        id_configurado = config.ID_EMPRESA
    if not _tabela_existe(con, "empresa"):
        if id_configurado is not None:
            raise EmpresaIndefinida("OVERFLOW_ID_EMPRESA foi definida, mas o banco nao tem a tabela empresa; "
                                    "execute scripts/migrar_banco.py antes.")
        return None
    if id_configurado is not None:
        if con.execute("SELECT 1 FROM empresa WHERE id_empresa = ?", (id_configurado,)).fetchone() is None:
            raise EmpresaIndefinida(f"OVERFLOW_ID_EMPRESA={id_configurado} nao existe na tabela empresa.")
        return id_configurado
    ids = [i for (i,) in con.execute("SELECT id_empresa FROM empresa ORDER BY id_empresa")]
    if len(ids) == 1:
        return ids[0]
    if not ids:
        raise EmpresaIndefinida("a tabela empresa esta vazia; execute scripts/migrar_banco.py antes.")
    raise EmpresaIndefinida("o banco tem mais de uma empresa; defina OVERFLOW_ID_EMPRESA.")
