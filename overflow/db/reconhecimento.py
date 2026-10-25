import sqlite3
from datetime import datetime

from overflow import config

def cadastrar_reconhecimento(id_pessoa, embedding):
    conexao = sqlite3.connect(config.BANCO)
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO reconhecimento (
            id_pessoa,
            embedding,
            criado_em
        )
        VALUES (?, ?, ?)
    """, (
        id_pessoa,
        embedding,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conexao.commit()
    conexao.close()

    print("Reconhecimento cadastrado com sucesso!")

def buscar_reconhecimento(id_pessoa):
    conexao = sqlite3.connect(config.BANCO)
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT embedding
        FROM reconhecimento
        WHERE id_pessoa = ?
    """, (id_pessoa,))

    resultado = cursor.fetchone()

    conexao.close()

    return resultado[0] if resultado else None