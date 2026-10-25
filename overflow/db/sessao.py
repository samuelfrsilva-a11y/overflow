import sqlite3
import uuid
from datetime import datetime

from overflow import config

def criar_sessao():
    identificador_sessao = str(uuid.uuid4())

    conexao = sqlite3.connect(config.BANCO)
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessao_camera (
            id_sessao INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador TEXT NOT NULL UNIQUE,
            inicio TEXT NOT NULL,
            fim TEXT
        )
    """)

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO sessao_camera (
            identificador,
            inicio
        )
        VALUES (?, ?)
    """, (
        identificador_sessao,
        agora
    ))

    id_sessao = cursor.lastrowid

    conexao.commit()
    conexao.close()

    return id_sessao, identificador_sessao

def finalizar_sessao(id_sessao):
    conexao = sqlite3.connect(config.BANCO)
    cursor = conexao.cursor()

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE sessao_camera
        SET fim = ?
        WHERE id_sessao = ?
    """, (
        agora,
        id_sessao
    ))

    conexao.commit()
    conexao.close()