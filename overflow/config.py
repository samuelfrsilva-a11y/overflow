"""Caminhos e parametros centrais do Overflow.

Todos os caminhos sao absolutos, calculados a partir da raiz do projeto,
entao funcionam independentemente da pasta de onde o script e executado.

O que muda entre maquinas (ambiente, banco, modelos, camera, painel) vem de
variaveis de ambiente; veja .env.example. Nenhum segredo fica no codigo.
Valores invalidos interrompem a execucao com uma mensagem clara.
"""
import os
from pathlib import Path

# Raiz do projeto (pasta que contem este pacote)
BASE_DIR = Path(__file__).resolve().parent.parent


def _env(nome, padrao=None):
    valor = os.environ.get(nome, "").strip()
    return valor if valor else padrao


def _env_int(nome, padrao=None, minimo=None, maximo=None):
    valor = _env(nome)
    if valor is None:
        return padrao
    try:
        numero = int(valor)
    except ValueError:
        raise SystemExit(f"Configuracao invalida: {nome} precisa ser um numero inteiro.")
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        faixa = f"entre {minimo} e {maximo}" if maximo is not None else f"maior ou igual a {minimo}"
        raise SystemExit(f"Configuracao invalida: {nome} precisa ser {faixa}.")
    return numero


# Ambiente: "desenvolvimento" (padrao) ou "producao". Qualquer outro valor interrompe,
# para que um erro de digitacao nao deixe a producao rodando sem as protecoes.
AMBIENTE = _env("OVERFLOW_AMBIENTE", "desenvolvimento").lower()
if AMBIENTE not in ("desenvolvimento", "producao"):
    raise SystemExit("Configuracao invalida: OVERFLOW_AMBIENTE deve ser 'desenvolvimento' ou 'producao'.")
PRODUCAO = AMBIENTE == "producao"

# Banco de dados
# OVERFLOW_BANCO permite apontar para outro arquivo (ex.: uma copia para testes).
BANCO = Path(_env("OVERFLOW_BANCO") or BASE_DIR / "banco.db")

# Empresa dona das movimentacoes gravadas pela camera e das pessoas cadastradas.
# Opcional quando o banco tem uma unica empresa (ela e usada automaticamente);
# obrigatoria quando ha mais de uma (veja overflow/db/empresa.py).
ID_EMPRESA = _env_int("OVERFLOW_ID_EMPRESA", minimo=1)

# Modelos, nao versionados (veja README). OVERFLOW_MODELOS_DIR: pasta dos ONNX de rosto;
# OVERFLOW_MODELO_DETECCAO: pesos do YOLO.
MODELOS_DIR = Path(_env("OVERFLOW_MODELOS_DIR") or BASE_DIR / "modelos")
MODELO_DETECCAO = Path(_env("OVERFLOW_MODELO_DETECCAO") or BASE_DIR / "yolo26n.pt")
MODELO_FACE_DETECTOR = MODELOS_DIR / "face_detection_yunet_2023mar.onnx"
MODELO_FACE_RECONHECIMENTO = MODELOS_DIR / "face_recognition_sface_2021dec.onnx"

# Camera: indice da webcam (0 = primeira)
CAMERA_FONTE = _env_int("OVERFLOW_CAMERA_FONTE", 0, minimo=0)

# Rastreador
# TRACKER e o que o camera.py usa hoje (configuracao padrao do Ultralytics).
# TRACKER_CUSTOM existe no projeto, mas ainda nao e usado.
TRACKER = "bytetrack.yaml"
TRACKER_CUSTOM = BASE_DIR / "bytetrack_custom.yaml"

# Interface web
TEMPLATES_DIR = BASE_DIR / "templates"
WEB_HOST = _env("OVERFLOW_HOST", "127.0.0.1")
WEB_PORTA = _env_int("OVERFLOW_PORTA", 5000, minimo=1, maximo=65535)

# Quantos proxies reversos confiaveis (HTTPS, tunel) ficam na frente do painel.
# 0 (padrao): os cabecalhos X-Forwarded-* enviados pelo cliente sao ignorados.
PROXIES_CONFIAVEIS = _env_int("OVERFLOW_PROXIES_CONFIAVEIS", 0, minimo=0, maximo=5)

# Dataset de uniforme (imagens brutas, nao versionadas)
UNIFORME_DIR = BASE_DIR / "uniforme"
