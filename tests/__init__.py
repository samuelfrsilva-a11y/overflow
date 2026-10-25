"""Testes automatizados do Overflow.

Execucao (na raiz do projeto, sem gerar __pycache__):
    .\\.venv\\Scripts\\python.exe -B -m unittest discover -s tests -t .

Seguranca: este pacote e importado antes de qualquer teste e
  - remove do ambiente todas as variaveis OVERFLOW_* herdadas do terminal;
  - aponta OVERFLOW_BANCO para um banco DESCARTAVEL numa pasta temporaria,
    antes de qualquer import da aplicacao, e confere o resultado;
  - bloqueia sqlite3.connect para QUALQUER banco em arquivo fora dessa pasta
    temporaria (inclusive o banco.db da raiz): o teste falha em vez de abri-lo;
  - apaga a pasta temporaria ao terminar.
Os dados usados nos testes sao ficticios; senhas e chaves sao geradas na hora.
"""
import atexit
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BANCO_REAL = (RAIZ / "banco.db").resolve()

PASTA_TEMP = Path(tempfile.mkdtemp(prefix="overflow_testes_")).resolve()
atexit.register(shutil.rmtree, PASTA_TEMP, ignore_errors=True)
BANCO = PASTA_TEMP / "banco_teste.db"

for _nome in [n for n in os.environ if n.upper().startswith("OVERFLOW_")]:
    del os.environ[_nome]
os.environ["OVERFLOW_BANCO"] = str(BANCO)
os.environ["OVERFLOW_SECRET_KEY"] = secrets.token_hex(32)     # ficticia, so desta execucao
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"                   # vale tambem para os subprocessos
sys.dont_write_bytecode = True


def caminho_do_banco(database):
    """Caminho de arquivo de um argumento de sqlite3.connect (texto, Path ou URI file:)."""
    texto = os.fspath(database) if not isinstance(database, (bytes, bytearray)) else database.decode()
    if texto.startswith("file:"):
        texto = urllib.parse.unquote(urllib.parse.urlsplit(texto).path if texto.startswith("file://")
                                     else texto[5:].split("?", 1)[0])
        if re.match(r"^/[A-Za-z]:", texto):
            texto = texto[1:]
    if texto in ("", ":memory:"):
        return None
    return Path(texto).resolve()


def banco_permitido(caminho):
    """So bancos em memoria ou dentro da pasta temporaria desta execucao."""
    return caminho is None or (caminho != BANCO_REAL and caminho.is_relative_to(PASTA_TEMP))


_connect_original = sqlite3.connect


def _connect_protegido(database, *args, **kwargs):
    if not banco_permitido(caminho_do_banco(database)):
        raise RuntimeError("Teste tentou abrir um banco fora da pasta temporaria; "
                           "os testes so podem usar bancos temporarios.")
    return _connect_original(database, *args, **kwargs)


sqlite3.connect = _connect_protegido

from overflow import config  # noqa: E402

if Path(config.BANCO).resolve() != BANCO.resolve() or not banco_permitido(Path(config.BANCO).resolve()):
    raise RuntimeError("Os testes so podem usar o banco descartavel da pasta temporaria.")
