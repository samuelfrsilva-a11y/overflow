"""Ponto de entrada WSGI do painel (para servidores como waitress ou gunicorn).

Exemplos (servidores nao incluidos nos requirements):
    waitress-serve --host 127.0.0.1 --port 8000 wsgi:app
    gunicorn --workers 1 --bind 127.0.0.1:8000 wsgi:app
Use 1 processo: o limite de tentativas de login fica na memoria do processo.
Ao carregar, ajusta o esquema do banco (idempotente; so acrescenta tabelas/colunas).
"""
from overflow.web.dashboard import app, preparar_banco

preparar_banco()
