import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overflow import config

conexao = sqlite3.connect(config.BANCO)
cursor = conexao.cursor()

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_movimentacao_data_entrada
ON movimentacao(data_entrada)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_movimentacao_hora_entrada
ON movimentacao(hora_entrada)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_movimentacao_id_pessoa
ON movimentacao(id_pessoa)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_movimentacao_id_local
ON movimentacao(id_local)
""")

conexao.commit()
conexao.close()

print("Índices do banco criados com sucesso!")