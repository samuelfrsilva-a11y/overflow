"""Resumo mensal, arquivamento e virada de mes do Overflow.

- gerar_resumo: calcula melhores horarios, dias e semanas de um mes.
- arquivar: MOVE registros de `movimentacao` para `movimentacao_arquivo`
  (o painel "reinicia", mas nada e perdido).
- virar_mes: para cada mes anterior ao atual, salva o resumo e arquiva os registros.

Isolamento entre empresas: os resumos ficam em `resumo_mensal_empresa`
(chave id_empresa + mes). A tabela antiga `resumo_mensal` (sem empresa) nao e
alterada; enquanto o banco tiver uma unica empresa, seus resumos sao copiados
para ela. Sem id_empresa (banco nao migrado) vale o comportamento antigo.
"""
from __future__ import annotations

import calendar
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence

NOMES_DIA_SEMANA = ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira",
                    "Quinta-feira", "Sexta-feira", "Sábado"]


def _colunas(con: sqlite3.Connection, tabela: str):
    return [(l[1], l[2] or "") for l in con.execute(f"PRAGMA table_info({tabela})")]


def garantir_tabelas(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS resumo_mensal (
        mes TEXT PRIMARY KEY, criado_em TEXT NOT NULL, dados TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS resumo_mensal_empresa (
        id_empresa INTEGER NOT NULL, mes TEXT NOT NULL, criado_em TEXT NOT NULL, dados TEXT NOT NULL,
        PRIMARY KEY (id_empresa, mes))""")
    if _tabela_existe(con, "empresa"):
        empresas = [i for (i,) in con.execute("SELECT id_empresa FROM empresa")]
        if len(empresas) == 1:
            # Resumos antigos (gerados antes da separacao) pertencem a unica empresa existente.
            con.execute("""INSERT OR IGNORE INTO resumo_mensal_empresa (id_empresa, mes, criado_em, dados)
                           SELECT ?, mes, criado_em, dados FROM resumo_mensal""", (empresas[0],))
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movimentacao_arquivo'").fetchone()
    if not existe:
        con.execute("CREATE TABLE movimentacao_arquivo AS SELECT * FROM movimentacao WHERE 0")
        con.execute("ALTER TABLE movimentacao_arquivo ADD COLUMN arquivado_em TEXT")
        con.execute("ALTER TABLE movimentacao_arquivo ADD COLUMN motivo TEXT")
    tem = {c for c, _ in _colunas(con, "movimentacao_arquivo")}
    for nome, tipo in _colunas(con, "movimentacao"):
        if nome not in tem:
            con.execute(f'ALTER TABLE movimentacao_arquivo ADD COLUMN "{nome}" {tipo}')
    con.commit()


def _tabela_existe(con: sqlite3.Connection, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def _por_empresa(con: sqlite3.Connection) -> bool:
    return "id_empresa" in {c for c, _ in _colunas(con, "movimentacao")}


def _top(contador: Counter, n: int = 3) -> List[Dict]:
    itens = sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [{"chave": k, "total": v} for k, v in itens]


def gerar_resumo(con: sqlite3.Connection, mes: str, id_empresa: Optional[int] = None) -> Optional[Dict]:
    """mes no formato 'AAAA-MM'. Com id_empresa, considera so os registros dela.
    Retorna None se nao houver registros."""
    tem_vis = "id_visitante" in {c for c, _ in _colunas(con, "movimentacao")}
    col_vis = "id_visitante" if tem_vis else "NULL"
    filtro, params = "", [mes]
    if id_empresa is not None:
        filtro = " AND id_empresa = ?"
        params.append(id_empresa)
    linhas = con.execute(f"""
        SELECT data_entrada, hora_entrada, data_saida, tempo_dentro, id_pessoa, {col_vis}
        FROM movimentacao WHERE substr(data_entrada, 1, 7) = ?{filtro}""", params).fetchall()
    if not linhas:
        return None

    ano, num_mes = int(mes[:4]), int(mes[5:7])
    ultimo_dia = calendar.monthrange(ano, num_mes)[1]

    por_dia, por_hora, por_semana, por_dow = Counter(), Counter(), Counter(), Counter()
    tempos, pessoas = [], set()
    saidas = 0
    for data_e, hora_e, data_s, tempo, id_pessoa, id_vis in linhas:
        por_dia[data_e] += 1
        por_hora[(hora_e or "00")[:2]] += 1
        dia = int(data_e[8:10])
        por_semana[(dia - 1) // 7 + 1] += 1
        por_dow[date(ano, num_mes, dia).weekday()] += 1
        if data_s:
            saidas += 1
        if tempo is not None:
            tempos.append(tempo)
        pessoas.add(("v", id_vis) if id_vis else ("p", id_pessoa))

    semanas = []
    for s in range(1, (ultimo_dia - 1) // 7 + 2):
        semanas.append({"semana": s, "inicio": 7 * (s - 1) + 1, "fim": min(7 * s, ultimo_dia),
                        "total": por_semana.get(s, 0)})
    melhor_semana = max(semanas, key=lambda x: x["total"])

    # weekday(): segunda=0 ... domingo=6 -> reordena para domingo=0
    dow = [por_dow.get((i - 1) % 7, 0) for i in range(7)]
    melhor_dow = max(range(7), key=lambda i: dow[i])

    return {
        "mes": mes,
        "entradas": len(linhas),
        "saidas": saidas,
        "sem_saida": len(linhas) - saidas,
        "tempo_medio": int(sum(tempos) / len(tempos)) if tempos else 0,
        "pessoas_diferentes": len(pessoas),
        "dias": [{"data": d, "total": t} for d, t in sorted(por_dia.items())],
        "melhores_dias": [{"data": x["chave"], "total": x["total"]} for x in _top(por_dia)],
        "horas": [{"hora": h, "total": t} for h, t in sorted(por_hora.items())],
        "melhores_horas": [{"hora": x["chave"], "total": x["total"]} for x in _top(por_hora)],
        "semanas": semanas,
        "melhor_semana": melhor_semana,
        "dias_semana": [{"nome": NOMES_DIA_SEMANA[i], "total": dow[i]} for i in range(7)],
        "melhor_dia_semana": {"nome": NOMES_DIA_SEMANA[melhor_dow], "total": dow[melhor_dow]},
    }


def arquivar(con: sqlite3.Connection, condicao: str, params: Sequence, motivo: str) -> int:
    """Move de `movimentacao` para `movimentacao_arquivo` as linhas que satisfazem a condicao."""
    garantir_tabelas(con)
    cols = ", ".join(f'"{c}"' for c, _ in _colunas(con, "movimentacao"))
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        con.execute(f"""INSERT INTO movimentacao_arquivo ({cols}, arquivado_em, motivo)
                        SELECT {cols}, ?, ? FROM movimentacao WHERE {condicao}""",
                    (agora, motivo, *params))
        n = con.execute(f"DELETE FROM movimentacao WHERE {condicao}", tuple(params)).rowcount
        con.commit()
    except Exception:
        con.rollback()
        raise
    return n


def virar_mes(con: sqlite3.Connection, hoje: Optional[date] = None) -> List[str]:
    """Salva o resumo e arquiva todos os meses anteriores ao atual. Retorna os meses tratados."""
    garantir_tabelas(con)
    mes_atual = (hoje or date.today()).strftime("%Y-%m")
    meses = [m for (m,) in con.execute(
        """SELECT DISTINCT substr(data_entrada, 1, 7) FROM movimentacao
           WHERE substr(data_entrada, 1, 7) < ? ORDER BY 1""", (mes_atual,)) if m]
    por_empresa = _por_empresa(con)
    for mes in meses:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if por_empresa:
            empresas = [i for (i,) in con.execute(
                """SELECT DISTINCT id_empresa FROM movimentacao
                   WHERE substr(data_entrada, 1, 7) = ? AND id_empresa IS NOT NULL""", (mes,))]
            for id_empresa in empresas:
                resumo = gerar_resumo(con, mes, id_empresa)
                if resumo:
                    con.execute("""INSERT OR IGNORE INTO resumo_mensal_empresa
                                   (id_empresa, mes, criado_em, dados) VALUES (?, ?, ?, ?)""",
                                (id_empresa, mes, agora, json.dumps(resumo, ensure_ascii=False)))
        else:
            resumo = gerar_resumo(con, mes)
            if resumo:
                con.execute("INSERT OR IGNORE INTO resumo_mensal (mes, criado_em, dados) VALUES (?, ?, ?)",
                            (mes, agora, json.dumps(resumo, ensure_ascii=False)))
        arquivar(con, "substr(data_entrada, 1, 7) = ?", (mes,), f"virada de mes ({mes})")
    # registros sem data valida (lixo) tambem saem do painel
    arquivar(con, "data_entrada IS NULL OR substr(data_entrada, 1, 7) < '2000'", (), "data invalida")
    return meses


def carregar_resumo(con: sqlite3.Connection, mes: str, id_empresa: Optional[int] = None) -> Optional[Dict]:
    garantir_tabelas(con)
    if id_empresa is None:
        linha = con.execute("SELECT dados FROM resumo_mensal WHERE mes = ?", (mes,)).fetchone()
    else:
        linha = con.execute("SELECT dados FROM resumo_mensal_empresa WHERE id_empresa = ? AND mes = ?",
                            (id_empresa, mes)).fetchone()
    return json.loads(linha[0]) if linha else None


def listar_resumos(con: sqlite3.Connection, id_empresa: Optional[int] = None) -> List[Dict]:
    garantir_tabelas(con)
    if id_empresa is None:
        cur = con.execute("SELECT dados FROM resumo_mensal ORDER BY mes DESC")
    else:
        cur = con.execute("SELECT dados FROM resumo_mensal_empresa WHERE id_empresa = ? ORDER BY mes DESC",
                          (id_empresa,))
    return [json.loads(d) for (d,) in cur]
