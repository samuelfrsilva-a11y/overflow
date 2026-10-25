"""Cadastra uma pessoa a partir de uma foto com um único rosto (embedding SFace).

Uso, a partir da raiz do projeto:
    python scripts/cadastrar_pessoa_rosto.py
Requer os modelos ONNX em modelos/ (veja README). A foto NÃO é copiada para o banco;
apenas o embedding (dado biométrico: trate o banco como dado pessoal sensível).
"""
import cv2
import sqlite3
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overflow import config
from overflow.db.empresa import EmpresaIndefinida, resolver_empresa

nome = input("Nome da pessoa: ").strip()
tipo = input("Tipo (funcionario/visitante): ").strip().lower()
imagem = input("Nome da foto: ").strip()

if not nome:
    print("Nome inválido.")
    exit()

if tipo not in ["funcionario", "visitante"]:
    print("Tipo inválido.")
    exit()

modelo_detector = str(config.MODELO_FACE_DETECTOR)
modelo_reconhecimento = str(config.MODELO_FACE_RECONHECIMENTO)

detector = cv2.FaceDetectorYN.create(
    modelo_detector,
    "",
    (320, 320),
    0.8,
    0.3,
    5000
)

reconhecedor = cv2.FaceRecognizerSF.create(
    modelo_reconhecimento,
    ""
)

frame = cv2.imread(imagem)

if frame is None:
    print("Não foi possível abrir a foto.")
    exit()

altura, largura = frame.shape[:2]

detector.setInputSize((largura, altura))

_, rostos = detector.detect(frame)

if rostos is None or len(rostos) == 0:
    print("Nenhum rosto foi encontrado.")
    exit()

if len(rostos) > 1:
    print("A foto deve conter apenas uma pessoa.")
    exit()

rosto = rostos[0]

rosto_alinhado = reconhecedor.alignCrop(
    frame,
    rosto
)

embedding = reconhecedor.feature(
    rosto_alinhado
)

embedding_texto = json.dumps(
    embedding.flatten().tolist()
)

codigo_pessoa = "PESSOA-" + uuid.uuid4().hex[:8].upper()

agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

conexao = sqlite3.connect(config.BANCO)
cursor = conexao.cursor()

# Sem id_empresa a pessoa não aparece na página Pessoas de nenhuma empresa.
try:
    id_empresa = resolver_empresa(conexao)
except EmpresaIndefinida as erro:
    conexao.close()
    print(f"Erro: {erro}")
    exit()

if id_empresa is None:
    cursor.execute("""
        INSERT INTO pessoa (
            nome,
            codigo_pessoa,
            tipo_pessoa
        )
        VALUES (?, ?, ?)
    """, (
        nome,
        codigo_pessoa,
        tipo
    ))
else:
    cursor.execute("""
        INSERT INTO pessoa (
            nome,
            codigo_pessoa,
            tipo_pessoa,
            id_empresa
        )
        VALUES (?, ?, ?, ?)
    """, (
        nome,
        codigo_pessoa,
        tipo,
        id_empresa
    ))

id_pessoa = cursor.lastrowid

cursor.execute("""
    INSERT INTO identificacao (
        id_pessoa,
        identificador,
        data_cadastro
    )
    VALUES (?, ?, ?)
""", (
    id_pessoa,
    codigo_pessoa,
    agora
))

cursor.execute("""
    INSERT INTO reconhecimento (
        id_pessoa,
        embedding,
        criado_em
    )
    VALUES (?, ?, ?)
""", (
    id_pessoa,
    embedding_texto,
    agora
))

conexao.commit()
conexao.close()

print()
print("Pessoa cadastrada com sucesso!")
print(f"ID: {id_pessoa}")
print(f"Código: {codigo_pessoa}")
print(f"Nome: {nome}")
print(f"Tipo: {tipo}")