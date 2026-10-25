import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overflow import config

conexao = sqlite3.connect(config.BANCO)
cursor = conexao.cursor()

cursor.execute("""
    SELECT
        m.id_movimentacao,
        p.id_pessoa,
        p.nome,
        p.codigo_pessoa,
        p.tipo_pessoa,
        l.nome,
        m.data_entrada,
        m.hora_entrada,
        m.data_saida,
        m.hora_saida,
        m.tempo_dentro,
        m.id_sessao
    FROM movimentacao m
    JOIN pessoa p
        ON m.id_pessoa = p.id_pessoa
    JOIN local l
        ON m.id_local = l.id_local
    ORDER BY m.id_movimentacao DESC
""")

movimentacoes = cursor.fetchall()

conexao.close()

if not movimentacoes:
    print("Nenhuma movimentação encontrada.")
    exit()

print()
print("MOVIMENTAÇÕES")
print("=" * 80)

for movimento in movimentacoes:

    id_movimentacao = movimento[0]
    id_pessoa = movimento[1]
    nome = movimento[2]
    codigo = movimento[3]
    tipo = movimento[4]
    local = movimento[5]
    data_entrada = movimento[6]
    hora_entrada = movimento[7]
    data_saida = movimento[8]
    hora_saida = movimento[9]
    tempo = movimento[10]
    id_sessao = movimento[11]

    if nome is None:
        nome = "Desconhecido"

    if codigo is None:
        codigo = "Sem código"

    if tipo == "funcionario":
        tipo_exibicao = "Funcionário"
    elif tipo == "visitante":
        tipo_exibicao = "Visitante"
    else:
        tipo_exibicao = "Desconhecido"

    if tempo is not None:
        minutos = tempo // 60
        segundos = tempo % 60
        tempo_exibicao = f"{minutos}min {segundos}s"
    else:
        tempo_exibicao = "Em andamento"

    print(f"Movimentação: {id_movimentacao}")
    print(f"Pessoa: {nome}")
    print(f"ID pessoa: {id_pessoa}")
    print(f"Código: {codigo}")
    print(f"Tipo: {tipo_exibicao}")
    print(f"Local: {local}")
    print(f"Entrada: {data_entrada} {hora_entrada}")

    if data_saida:
        print(f"Saída: {data_saida} {hora_saida}")
    else:
        print("Saída: Ainda dentro do local")

    print(f"Tempo dentro: {tempo_exibicao}")
    print(f"Sessão: {id_sessao}")
    print("-" * 80)