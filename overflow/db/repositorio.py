"""Acesso ao banco.db do Overflow.

Mantem o esquema existente (tabelas pessoa, reconhecimento, movimentacao) e
apenas ACRESCENTA o necessario para lembrar visitantes entre execucoes:
  - movimentacao.id_visitante, movimentacao.confianca  (colunas novas)
  - tabela visitante e visitante_face                    (tabelas novas)
Faca uma copia do banco.db antes da primeira execucao.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional, Sequence

import numpy as np

from overflow import config

ID_DESCONHECIDO = 1   # mesma convencao do prototipo: pessoa 1 = "Desconhecido"


def _parse_embedding(texto) -> Optional[np.ndarray]:
    try:
        if isinstance(texto, (bytes, bytearray)):
            return np.frombuffer(texto, dtype=np.float32).copy()
        valores = [float(v) for v in str(texto).strip().strip("[]").split(",")]
        return np.asarray(valores, dtype=np.float32)
    except Exception:
        return None


class Repositorio:
    def __init__(self, caminho: Optional[str] = None):
        self.con = sqlite3.connect(caminho if caminho is not None else config.BANCO)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self._garantir_esquema()

    # ----------------------------------------------------------- esquema
    def _garantir_esquema(self) -> None:
        cur = self.con.cursor()
        colunas = {l[1] for l in cur.execute("PRAGMA table_info(movimentacao)")}
        if not colunas:
            raise RuntimeError("Tabela 'movimentacao' nao existe em banco.db")
        if "id_visitante" not in colunas:
            cur.execute("ALTER TABLE movimentacao ADD COLUMN id_visitante INTEGER")
        if "confianca" not in colunas:
            cur.execute("ALTER TABLE movimentacao ADD COLUMN confianca TEXT")
        cur.execute("""CREATE TABLE IF NOT EXISTS visitante (
            id_visitante INTEGER PRIMARY KEY,
            criado_em TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS visitante_face (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_visitante INTEGER NOT NULL,
            embedding BLOB NOT NULL)""")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_vface ON visitante_face(id_visitante)")
        self.con.commit()

    # ------------------------------------------------------------ leitura
    def carregar_cadastrados(self):
        """Lista de (id_pessoa, nome, tipo, codigo, embedding)."""
        cur = self.con.execute("""
            SELECT r.id_pessoa, p.nome, p.tipo_pessoa, p.codigo_pessoa, r.embedding
            FROM reconhecimento r JOIN pessoa p ON p.id_pessoa = r.id_pessoa""")
        saida, invalidos = [], 0
        for id_pessoa, nome, tipo, codigo, emb in cur.fetchall():
            v = _parse_embedding(emb)
            if v is None or v.size == 0:
                invalidos += 1
                continue
            saida.append((id_pessoa, nome, tipo, codigo, v))
        if invalidos:
            print(f"[banco] {invalidos} embeddings invalidos ignorados")
        return saida

    def proximo_id_visitante(self) -> int:
        linha = self.con.execute("SELECT COALESCE(MAX(id_visitante), 0) FROM visitante").fetchone()
        return int(linha[0]) + 1

    def abertas_hoje(self):
        """Movimentacoes de hoje ainda sem saida: (id_mov, id_pessoa, id_visitante)."""
        hoje = datetime.now().strftime("%Y-%m-%d")
        cur = self.con.execute("""
            SELECT id_movimentacao, id_pessoa, id_visitante FROM movimentacao
            WHERE data_saida IS NULL AND data_entrada = ?
            ORDER BY id_movimentacao""", (hoje,))
        return cur.fetchall()

    def faces_visitante(self, id_visitante: int) -> List[np.ndarray]:
        cur = self.con.execute("SELECT embedding FROM visitante_face WHERE id_visitante = ?",
                               (id_visitante,))
        return [_parse_embedding(b) for (b,) in cur.fetchall()]

    # ----------------------------------------------------------- escrita
    def salvar_visitante(self, id_visitante: int, faces: Sequence[np.ndarray]) -> None:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.con.execute("INSERT OR IGNORE INTO visitante (id_visitante, criado_em) VALUES (?, ?)",
                         (id_visitante, agora))
        self.adicionar_faces(id_visitante, faces, commit=False)
        self.con.commit()

    def adicionar_faces(self, id_visitante: int, faces: Sequence[np.ndarray], commit: bool = True) -> None:
        for f in faces:
            self.con.execute("INSERT INTO visitante_face (id_visitante, embedding) VALUES (?, ?)",
                             (id_visitante, np.asarray(f, dtype=np.float32).tobytes()))
        if commit:
            self.con.commit()

    def remover_visitante(self, id_visitante: int) -> None:
        self.con.execute("DELETE FROM visitante_face WHERE id_visitante = ?", (id_visitante,))
        self.con.execute("DELETE FROM visitante WHERE id_visitante = ?", (id_visitante,))
        self.con.commit()

    def abrir(self, id_pessoa: Optional[int], id_visitante: Optional[int], quando: datetime,
              id_sessao, confianca: str, id_local: int = 1) -> int:
        cur = self.con.execute("""
            INSERT INTO movimentacao
              (id_pessoa, id_local, data_entrada, hora_entrada, id_sessao, id_visitante, confianca)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id_pessoa if id_pessoa is not None else ID_DESCONHECIDO, id_local,
             quando.strftime("%Y-%m-%d"), quando.strftime("%H:%M:%S"),
             id_sessao, id_visitante, confianca))
        self.con.commit()
        return cur.lastrowid

    def fechar(self, id_mov: int, quando: datetime, confianca: str = "") -> None:
        linha = self.con.execute(
            "SELECT data_entrada, hora_entrada, confianca FROM movimentacao WHERE id_movimentacao = ?",
            (id_mov,)).fetchone()
        if linha is None:
            return
        data, hora, conf_entrada = linha
        entrada = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M:%S")
        tempo = max(0, int((quando - entrada).total_seconds()))
        conf = f"{conf_entrada or ''}>{confianca}" if confianca else (conf_entrada or "")
        self.con.execute("""
            UPDATE movimentacao SET data_saida = ?, hora_saida = ?, tempo_dentro = ?, confianca = ?
            WHERE id_movimentacao = ?""",
            (quando.strftime("%Y-%m-%d"), quando.strftime("%H:%M:%S"), tempo, conf, id_mov))
        self.con.commit()

    def transferir(self, id_mov: int, id_pessoa: Optional[int], id_visitante: Optional[int]) -> None:
        self.con.execute("""UPDATE movimentacao SET id_pessoa = ?, id_visitante = ?
                            WHERE id_movimentacao = ?""",
                         (id_pessoa if id_pessoa is not None else ID_DESCONHECIDO,
                          id_visitante, id_mov))
        self.con.commit()

    def fechar_conexao(self) -> None:
        try:
            self.con.commit()
        finally:
            self.con.close()
