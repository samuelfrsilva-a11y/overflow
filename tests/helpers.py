"""Utilitarios comuns: banco ficticio, subprocessos isolados, login no painel e simulacoes."""
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from tests import BANCO, BANCO_REAL, PASTA_TEMP, RAIZ

EMAIL_ADMIN = "admin@teste.com"                     # criado por scripts/migrar_banco.py
SENHA_ADMIN = "senha-ficticia-" + secrets.token_hex(6)
SENHA_OUTRAS = "senha-ficticia-" + secrets.token_hex(6)
HOJE = date.today()
MES_ATUAL = HOJE.strftime("%Y-%m")
MES_ANTERIOR = (HOJE.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

# Impede o import de bibliotecas de visao: prova que o painel roda so com requirements-web.txt.
BLOQUEIO_VISAO = """
import sys
class _BloqueioVisao:
    def find_spec(self, nome, path=None, target=None):
        if nome.split('.')[0] in ('cv2', 'ultralytics', 'torch', 'torchvision', 'lap'):
            raise ImportError('bloqueado no teste: ' + nome)
sys.meta_path.insert(0, _BloqueioVisao())
"""

# cv2 simulado para scripts/cadastrar_pessoa_rosto.py (nao ha foto ficticia com rosto real).
# argv: raiz do projeto, quantidade de rostos detectados.
CV2_FALSO = r'''
import sys, types, numpy as np
cv2 = types.ModuleType("cv2")
class _Det:
    def setInputSize(self, s): pass
    def detect(self, frame): return 1, np.zeros((int(sys.argv[2]), 15), dtype=np.float32)
class _Rec:
    def alignCrop(self, frame, rosto): return frame
    def feature(self, img): return np.ones((1, 128), dtype=np.float32)
cv2.FaceDetectorYN = types.SimpleNamespace(create=lambda *a: _Det())
cv2.FaceRecognizerSF = types.SimpleNamespace(create=lambda *a: _Rec())
cv2.imread = lambda caminho: np.zeros((100, 100, 3), dtype=np.uint8)
sys.modules["cv2"] = cv2
sys.path.insert(0, sys.argv[1])
import runpy
runpy.run_path(sys.argv[1] + "/scripts/cadastrar_pessoa_rosto.py", run_name="__main__")
'''


# ------------------------------------------------------------------ subprocessos
def env_teste(banco=BANCO, **extra):
    """Ambiente limpo para subprocessos: sem OVERFLOW_* herdadas e com um banco temporario."""
    banco = Path(banco)
    if banco.resolve().parent != PASTA_TEMP.resolve() or banco.resolve() == BANCO_REAL:
        raise RuntimeError("subprocesso de teste so pode usar banco temporario")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("OVERFLOW_")}
    # Saida dos subprocessos sempre em UTF-8, independente da configuracao do terminal.
    env.update(OVERFLOW_BANCO=str(banco), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", **extra)
    return env


def python(args, entrada=None, banco=BANCO, **extra):
    """Roda `python -B <args>` na raiz do projeto, com ambiente de teste."""
    return subprocess.run([sys.executable, "-B", *args], cwd=RAIZ, env=env_teste(banco, **extra),
                          input=entrada, capture_output=True, encoding="utf-8", timeout=180)


def rodar_script(nome, *args, banco=BANCO, checar=True, **extra):
    r = subprocess.run([sys.executable, "-B", str(RAIZ / "scripts" / nome), *args], cwd=PASTA_TEMP,
                       env=env_teste(banco, **extra), capture_output=True, encoding="utf-8", timeout=180)
    if checar and r.returncode != 0:
        raise AssertionError(f"scripts/{nome} falhou: {r.stderr[-1500:]}")
    return r


def cadastrar_com_cv2_falso(n_rostos=1, **extra):
    return python(["-c", CV2_FALSO, str(RAIZ), str(n_rostos)],
                  entrada="Pessoa Ficticia\nfuncionario\nfoto_ficticia.jpg\n", **extra)


def resultado_sonda(r):
    """Le a linha RESULTADO=<json> impressa por uma sonda executada em subprocesso."""
    m = re.search(r"^RESULTADO=(.*)$", r.stdout, re.M)
    if not m:
        raise AssertionError(f"sonda falhou: {r.stderr[-2000:]}")
    return json.loads(m.group(1))


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ banco ficticio
def apagar_banco(banco=BANCO):
    for sufixo in ("", "-wal", "-shm", "-journal"):
        Path(f"{banco}{sufixo}").unlink(missing_ok=True)


def criar_banco(n_empresas=1, banco=BANCO):
    """Banco novo criado pelos proprios scripts do projeto, com o esquema completo do painel.
    Empresa 1: admin@teste.com. Empresas 2..n: usuarioN@exemplo.invalid (senha SENHA_OUTRAS)."""
    apagar_banco(banco)
    rodar_script("estrutura_banco.py", banco=banco)
    rodar_script("indice_banco.py", banco=banco)
    rodar_script("migrar_banco.py", banco=banco, OVERFLOW_ADMIN_PASSWORD=SENHA_ADMIN)
    from overflow.db import resumo
    from overflow.db.repositorio import Repositorio
    Repositorio(str(banco)).fechar_conexao()
    con = sqlite3.connect(banco)
    try:
        resumo.garantir_tabelas(con)
        for i in range(2, n_empresas + 1):
            id_empresa = con.execute("INSERT INTO empresa (nome) VALUES (?)", (f"Empresa Ficticia {i}",)).lastrowid
            con.execute("INSERT INTO usuario (id_empresa, email, senha) VALUES (?, ?, ?)",
                        (id_empresa, email_empresa(id_empresa), generate_password_hash(SENHA_OUTRAS)))
        con.commit()
    finally:
        con.close()


def email_empresa(id_empresa):
    return EMAIL_ADMIN if id_empresa == 1 else f"usuario{id_empresa}@exemplo.invalid"


def inserir_movimentacoes(id_empresa, mes, n, id_pessoa=1, banco=BANCO):
    con = sqlite3.connect(banco)
    try:
        for i in range(n):
            dia = f"{mes}-{10 + i:02d}"
            con.execute("""INSERT INTO movimentacao (id_pessoa, id_local, data_entrada, hora_entrada, data_saida,
                           hora_saida, tempo_dentro, id_empresa) VALUES (?, 1, ?, '10:00:00', ?, '10:05:00', 300, ?)""",
                        (id_pessoa, dia, dia, id_empresa))
        con.commit()
    finally:
        con.close()


def inserir_pessoa(nome, id_empresa, tipo="funcionario", banco=BANCO):
    con = sqlite3.connect(banco)
    try:
        id_pessoa = con.execute("INSERT INTO pessoa (nome, codigo_pessoa, tipo_pessoa, id_empresa) VALUES (?, ?, ?, ?)",
                                (nome, "PESSOA-" + secrets.token_hex(4).upper(), tipo, id_empresa)).lastrowid
        con.commit()
        return id_pessoa
    finally:
        con.close()


def consultar(sql, params=(), banco=BANCO):
    con = sqlite3.connect(banco)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


# ------------------------------------------------------------------ painel
def token_csrf(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def cliente(id_empresa=1, entrar=True):
    """Cliente de teste do painel (em processo), opcionalmente ja logado na empresa indicada."""
    from overflow.web import dashboard
    dashboard.app.config["TESTING"] = True
    dashboard._falhas_login.clear()
    dashboard._ultima_virada = 0.0
    c = dashboard.app.test_client()
    if entrar:
        senha = SENHA_ADMIN if id_empresa == 1 else SENHA_OUTRAS
        token = token_csrf(c.get("/login").get_data(as_text=True))
        r = c.post("/login", data={"email": email_empresa(id_empresa), "senha": senha, "csrf_token": token})
        if r.status_code != 302:
            raise AssertionError("login ficticio falhou")
    return c
