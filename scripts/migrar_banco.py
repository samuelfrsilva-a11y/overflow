import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.security import generate_password_hash

from overflow import config

SENHA_ADMIN_MINIMA = 8
TABELAS_BASE = ("movimentacao", "pessoa", "local")


def _senha_admin():
    senha = os.environ.get("OVERFLOW_ADMIN_PASSWORD", "")
    return senha if senha.strip() else None


def _tabela_existe(cursor, nome):
    return cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def _precisa_criar_empresa(cursor):
    return not _tabela_existe(cursor, "empresa") or cursor.execute("SELECT COUNT(*) FROM empresa").fetchone()[0] == 0


def _executar(con):
    cursor = con.cursor()

    # Pré-validações (somente leitura): nada é alterado antes de todas passarem.
    faltando = [t for t in TABELAS_BASE if not _tabela_existe(cursor, t)]
    if faltando:
        print(f"Migração interrompida: tabelas base ausentes ({', '.join(faltando)}); "
              "execute scripts/estrutura_banco.py antes.", file=sys.stderr)
        print("Nenhuma alteração foi feita no banco.", file=sys.stderr)
        return False

    # 0. A empresa e o administrador inicial só são criados com uma senha fornecida explicitamente.
    #    Sem ela, nada é alterado (empresa, administrador e associação de registros andam juntos).
    criar_empresa = _precisa_criar_empresa(cursor)
    senha_admin = _senha_admin() if criar_empresa else None
    if criar_empresa and (senha_admin is None or len(senha_admin) < SENHA_ADMIN_MINIMA):
        motivo = ("OVERFLOW_ADMIN_PASSWORD não está configurada" if senha_admin is None
                  else f"OVERFLOW_ADMIN_PASSWORD tem menos de {SENHA_ADMIN_MINIMA} caracteres")
        print(f"Migração interrompida: é preciso criar o administrador inicial, mas {motivo}.", file=sys.stderr)
        print("Nenhuma alteração foi feita no banco.", file=sys.stderr)
        return False

    # 1. Criar tabela de Empresas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresa (
            id_empresa INTEGER PRIMARY KEY AUTOINCREMENT,
            nome VARCHAR(100) NOT NULL
        )
    """)

    # 2. Criar tabela de Utilizadores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuario (
            id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            id_empresa INTEGER NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            senha VARCHAR(255) NOT NULL,
            FOREIGN KEY (id_empresa) REFERENCES empresa (id_empresa)
        )
    """)

    # 3. Adicionar id_empresa às tabelas existentes (caso ainda não existam)
    tabelas = ["movimentacao", "pessoa", "local"]
    for tabela in tabelas:
        cursor.execute(f"PRAGMA table_info({tabela})")
        colunas = [coluna[1] for coluna in cursor.fetchall()]
        if "id_empresa" not in colunas:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN id_empresa INTEGER REFERENCES empresa(id_empresa)")

    # 4. Criar uma empresa de teste e um utilizador inicial
    if criar_empresa:
        cursor.execute("INSERT INTO empresa (nome) VALUES ('Empresa Teste')")
        id_empresa = cursor.lastrowid

        # Administrador inicial: senha vinda de OVERFLOW_ADMIN_PASSWORD, gravada somente como hash
        cursor.execute("""
            INSERT INTO usuario (id_empresa, email, senha)
            VALUES (?, 'admin@teste.com', ?)
        """, (id_empresa, generate_password_hash(senha_admin)))

        # Associar registos antigos à empresa de teste
        for tabela in tabelas:
            cursor.execute(f"UPDATE {tabela} SET id_empresa = ? WHERE id_empresa IS NULL", (id_empresa,))

    con.commit()
    print("Migração concluída com sucesso!")
    return True


def migrar():
    caminho = Path(config.BANCO)
    if not caminho.is_file():
        print(f"Migração interrompida: banco de dados não encontrado em {caminho}.", file=sys.stderr)
        print("Nenhum arquivo foi criado.", file=sys.stderr)
        return False
    # mode=rw: abre somente um banco que já existe; nunca cria um arquivo novo.
    con = sqlite3.connect(f"{caminho.resolve().as_uri()}?mode=rw", uri=True)
    try:
        return _executar(con)
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(0 if migrar() else 1)