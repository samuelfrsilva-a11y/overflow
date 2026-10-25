import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overflow import config

conexao = sqlite3.connect(config.BANCO)
cursor = conexao.cursor()

# ---------- Tabela de pessoas ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS pessoa (
    id_pessoa INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    codigo_pessoa TEXT,
    tipo_pessoa TEXT NOT NULL DEFAULT 'desconhecido',
    identificador TEXT
)
""")

# Garante colunas caso a tabela já existisse antiga
for coluna, definicao in [
    ("nome", "TEXT"),
    ("codigo_pessoa", "TEXT"),
    ("tipo_pessoa", "TEXT NOT NULL DEFAULT 'desconhecido'"),
    ("identificador", "TEXT")
]:
    try:
        cursor.execute(f"ALTER TABLE pessoa ADD COLUMN {coluna} {definicao}")
    except sqlite3.OperationalError:
        pass  # já existe

# ---------- Tabela de reconhecimento (embeddings) ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS reconhecimento (
    id_reconhecimento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_pessoa INTEGER NOT NULL,
    imagem_referencia TEXT,
    criado_em TEXT NOT NULL,
    embedding TEXT,
    FOREIGN KEY (id_pessoa) REFERENCES pessoa(id_pessoa)
)
""")

# Colunas usadas pelo cadastro de rostos (scripts/cadastrar_pessoa_rosto.py) em bancos antigos.
# criado_em entra sem NOT NULL: o SQLite não permite acrescentar NOT NULL sem valor padrão.
for coluna, definicao in [
    ("imagem_referencia", "TEXT"),
    ("criado_em", "TEXT"),
]:
    try:
        cursor.execute(f"ALTER TABLE reconhecimento ADD COLUMN {coluna} {definicao}")
    except sqlite3.OperationalError:
        pass  # já existe

# ---------- Tabela de identificação (código de cada pessoa cadastrada) ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS identificacao (
    id_identificacao INTEGER PRIMARY KEY AUTOINCREMENT,
    id_pessoa INTEGER NOT NULL,
    identificador TEXT NOT NULL UNIQUE,
    data_cadastro TEXT NOT NULL,
    FOREIGN KEY (id_pessoa) REFERENCES pessoa(id_pessoa)
)
""")

# ---------- Tabela de locais ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS local (
    id_local INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL
)
""")

# ---------- Tabela de movimentações ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS movimentacao (
    id_movimentacao INTEGER PRIMARY KEY AUTOINCREMENT,
    id_pessoa INTEGER NOT NULL,
    id_local INTEGER NOT NULL,
    data_entrada TEXT NOT NULL,
    hora_entrada TEXT NOT NULL,
    data_saida TEXT,
    hora_saida TEXT,
    tempo_dentro INTEGER,
    id_sessao INTEGER,
    FOREIGN KEY (id_pessoa) REFERENCES pessoa(id_pessoa),
    FOREIGN KEY (id_local) REFERENCES local(id_local)
)
""")

# Garante a coluna id_sessao caso a tabela já existisse
try:
    cursor.execute("ALTER TABLE movimentacao ADD COLUMN id_sessao INTEGER")
except sqlite3.OperationalError:
    pass

# ---------- Local padrão ----------
cursor.execute("""
INSERT OR IGNORE INTO local (id_local, nome)
VALUES (1, 'Rua Principal')
""")

# ---------- Pessoa "Desconhecido" padrão (id = 1) ----------
# Usamos ela quando o rosto não é reconhecido
cursor.execute("""
INSERT OR IGNORE INTO pessoa (id_pessoa, nome, codigo_pessoa, tipo_pessoa)
VALUES (1, 'Desconhecido', 'DESC-001', 'desconhecido')
""")

conexao.commit()
conexao.close()

print("Estrutura do banco criada/atualizada com sucesso!")