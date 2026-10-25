import cv2
import sqlite3
import numpy as np
from datetime import datetime
from ultralytics import YOLO

from overflow import config
from overflow.db.empresa import EmpresaIndefinida, resolver_empresa
from overflow.db.sessao import criar_sessao, finalizar_sessao

FONTE = config.CAMERA_FONTE
MODELO_DETECCAO = str(config.MODELO_DETECCAO)

LARGURA_CAMERA = 1280
ALTURA_CAMERA = 720

IMGSZ = 640
CONFIANCA = 0.20
IOU = 0.50
MAX_DET = 50

LINHA_SUPERIOR = 0.425
LINHA_INFERIOR = 0.575
NOME_JANELA = "Overflow - Contagem de Pessoas"


def abrir_camera(indice):
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
        camera = cv2.VideoCapture(indice, backend)
        if camera.isOpened():
            sucesso, frame = camera.read()
            if sucesso and frame is not None:
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, LARGURA_CAMERA)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTURA_CAMERA)
                camera.set(cv2.CAP_PROP_FPS, 30)
                camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return camera
        camera.release()
    return None


def criar_movimentacao():
    agora = datetime.now()
    colunas = ["id_pessoa", "id_local", "data_entrada", "hora_entrada", "id_sessao"]
    valores = [1, 1, agora.strftime("%Y-%m-%d"), agora.strftime("%H:%M:%S"), id_sessao]
    # Sem id_empresa a movimentação não aparece no painel de nenhuma empresa.
    # (None só em banco ainda não migrado, que não tem a coluna.)
    if id_empresa is not None:
        colunas.append("id_empresa")
        valores.append(id_empresa)
    cursor.execute(
        f"INSERT INTO movimentacao ({', '.join(colunas)}) VALUES ({', '.join('?' * len(valores))})",
        valores,
    )
    banco.commit()
    return cursor.lastrowid


def finalizar_movimentacao(id_movimentacao, momento_saida):
    cursor.execute(
        """
        SELECT data_entrada, hora_entrada
        FROM movimentacao
        WHERE id_movimentacao = ?
        """,
        (id_movimentacao,),
    )
    resultado = cursor.fetchone()
    if resultado is None:
        return

    data_entrada, hora_entrada = resultado
    entrada = datetime.strptime(
        f"{data_entrada} {hora_entrada}", "%Y-%m-%d %H:%M:%S"
    )
    tempo_dentro = max(0, int((momento_saida - entrada).total_seconds()))

    cursor.execute(
        """
        UPDATE movimentacao
        SET data_saida = ?, hora_saida = ?, tempo_dentro = ?
        WHERE id_movimentacao = ?
        """,
        (
            momento_saida.strftime("%Y-%m-%d"),
            momento_saida.strftime("%H:%M:%S"),
            tempo_dentro,
            id_movimentacao,
        ),
    )
    banco.commit()


def finalizar_movimentacoes_abertas():
    agora = datetime.now()
    for id_movimentacao in list(movimentacoes_ativas.values()):
        finalizar_movimentacao(id_movimentacao, agora)
    movimentacoes_ativas.clear()


def registrar_cruzamento(track_id, zona_nova):
    global entradas, saidas

    zona_antiga = ultima_zona.get(track_id)
    if zona_antiga is None:
        ultima_zona[track_id] = zona_nova
        return

    if zona_antiga == zona_nova:
        return

    if zona_antiga == "cima" and zona_nova == "baixo":
        if track_id not in movimentacoes_ativas and track_id not in ids_contados:
            movimentacoes_ativas[track_id] = criar_movimentacao()
            entradas += 1
            ids_contados.add(track_id)
        ultima_zona[track_id] = zona_nova
        return

    if zona_antiga == "baixo" and zona_nova == "cima":
        if track_id in movimentacoes_ativas:
            id_movimentacao = movimentacoes_ativas.pop(track_id)
            finalizar_movimentacao(id_movimentacao, datetime.now())
            saidas += 1
            ids_contados.discard(track_id)
        ultima_zona[track_id] = zona_nova
        return

    if zona_nova in ("cima", "baixo"):
        ultima_zona[track_id] = zona_nova


def main():
    global modelo, cap, id_sessao, id_empresa, banco, cursor, entradas, saidas, movimentacoes_ativas, ultima_zona, ultimo_visto, ids_contados

    # Decide a empresa antes de abrir a câmera, para falhar cedo se o banco não estiver pronto.
    conexao_empresa = sqlite3.connect(config.BANCO)
    try:
        id_empresa = resolver_empresa(conexao_empresa)
    except EmpresaIndefinida as erro:
        print(f"Erro: {erro}")
        raise SystemExit(1)
    finally:
        conexao_empresa.close()

    cv2.setUseOptimized(True)
    modelo = YOLO(MODELO_DETECCAO)

    cap = abrir_camera(FONTE)

    if cap is None:
        print(f"Erro: não foi possível abrir a câmera de índice {FONTE}.")
        print("Confira o índice da webcam e defina OVERFLOW_CAMERA_FONTE (ex.: 1 para a segunda câmera).")
        raise SystemExit(1)

    largura_video = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura_video = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_camera = cap.get(cv2.CAP_PROP_FPS)

    print()
    print("========================================")
    print("OVERFLOW - CONTAGEM DE PESSOAS")
    print("========================================")
    print("Modelo:", MODELO_DETECCAO)
    print("Fonte de câmera:", FONTE)
    print("Empresa:", id_empresa if id_empresa is not None else "(banco sem empresas)")
    print("Resolução:", largura_video, "x", altura_video)
    print("FPS informado pela câmera:", round(fps_camera, 2))
    print("YOLO IMG_SIZE:", IMGSZ)
    print("Confiança mínima:", CONFIANCA)
    print("Tracker: ByteTrack")
    print("Processamento: CPU")
    print("Reconhecimento facial: desativado")
    print("========================================")
    print()

    sessao_resultado = criar_sessao()
    id_sessao = sessao_resultado[0] if isinstance(sessao_resultado, tuple) else sessao_resultado

    banco = sqlite3.connect(config.BANCO)
    cursor = banco.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA cache_size=-20000")

    entradas = 0
    saidas = 0
    movimentacoes_ativas = {}
    ultima_zona = {}
    ultimo_visto = {}
    ids_contados = set()

    fps_inicio = cv2.getTickCount()
    fps_frames = 0
    fps_real = 0.0

    cv2.namedWindow(NOME_JANELA, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(NOME_JANELA, 960, 540)

    try:
        while True:
            sucesso, frame = cap.read()
            if not sucesso or frame is None:
                print("Erro ao capturar imagem da webcam.")
                break

            fps_frames += 1
            altura, largura = frame.shape[:2]
            linha_y1 = int(altura * LINHA_SUPERIOR)
            linha_y2 = int(altura * LINHA_INFERIOR)

            resultado = modelo.track(
                frame,
                persist=True,
                classes=[0],
                tracker="bytetrack.yaml",
                imgsz=IMGSZ,
                conf=CONFIANCA,
                iou=IOU,
                max_det=MAX_DET,
                device="cpu",
                verbose=False,
            )

            deteccoes = resultado[0]
            if deteccoes.boxes is not None and deteccoes.boxes.id is not None:
                caixas = deteccoes.boxes.xyxy.cpu().numpy()
                ids = deteccoes.boxes.id.cpu().numpy().astype(int)

                for caixa, track_id in zip(caixas, ids):
                    x1, y1, x2, y2 = map(int, caixa)
                    x1 = max(0, min(x1, largura - 1))
                    y1 = max(0, min(y1, altura - 1))
                    x2 = max(0, min(x2, largura - 1))
                    y2 = max(0, min(y2, altura - 1))

                    largura_caixa = x2 - x1
                    altura_caixa = y2 - y1
                    if largura_caixa <= 0 or altura_caixa <= 0:
                        continue

                    proporcao = altura_caixa / max(largura_caixa, 1)
                    area_relativa = (largura_caixa * altura_caixa) / max(largura * altura, 1)

                    # Filtros leves: preservam pessoas pequenas no fundo do corredor.
                    if altura_caixa < 35 or largura_caixa < 12:
                        continue
                    if proporcao < 0.85 or proporcao > 6.5:
                        continue
                    if area_relativa > 0.45:
                        continue

                    # Ponto próximo aos pés: tende a representar melhor a passagem no corredor.
                    ponto_y = int(y2 - altura_caixa * 0.08)

                    if ponto_y < linha_y1:
                        zona_atual = "cima"
                    elif ponto_y > linha_y2:
                        zona_atual = "baixo"
                    else:
                        zona_atual = "meio"

                    if track_id not in ultima_zona:
                        ultima_zona[track_id] = zona_atual
                    elif zona_atual != "meio":
                        registrar_cruzamento(track_id, zona_atual)

                    ultimo_visto[track_id] = datetime.now().timestamp()

                    cor = (0, 255, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), cor, 2)
                    cv2.putText(
                        frame,
                        f"Pessoa ID {track_id}",
                        (x1, max(22, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        cor,
                        2,
                        cv2.LINE_AA,
                    )

            # Limpa históricos antigos para não acumular IDs indefinidamente.
            agora_ts = datetime.now().timestamp()
            ids_antigos = [i for i, t in ultimo_visto.items() if agora_ts - t > 15]
            for track_id in ids_antigos:
                ultimo_visto.pop(track_id, None)
                ultima_zona.pop(track_id, None)
                ids_contados.discard(track_id)

            dentro = max(0, entradas - saidas)

            cv2.line(frame, (0, linha_y1), (largura, linha_y1), (0, 255, 255), 2)
            cv2.line(frame, (0, linha_y2), (largura, linha_y2), (0, 255, 255), 2)
            cv2.putText(frame, "CIMA", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "MEIO", (10, linha_y1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "BAIXO", (10, linha_y2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            cv2.rectangle(frame, (8, altura - 120), (300, altura - 8), (0, 0, 0), -1)
            cv2.putText(frame, f"Entradas: {entradas}", (18, altura - 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Saidas: {saidas}", (18, altura - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Dentro: {dentro}", (18, altura - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)

            agora_tick = cv2.getTickCount()
            tempo = (agora_tick - fps_inicio) / cv2.getTickFrequency()
            if tempo >= 1.0:
                fps_real = fps_frames / tempo
                fps_frames = 0
                fps_inicio = agora_tick

            cv2.putText(frame, f"FPS: {fps_real:.1f}", (largura - 150, altura - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow(NOME_JANELA, frame)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord("q"):
                break

    finally:
        try:
            finalizar_movimentacoes_abertas()
        finally:
            cap.release()
            cv2.destroyAllWindows()
            banco.close()
            finalizar_sessao(id_sessao)

        print()
        print("========================================")
        print("SESSÃO FINALIZADA")
        print("========================================")
        print("Entradas:", entradas)
        print("Saídas:", saidas)
        print("Pessoas dentro:", entradas - saidas)
        print("========================================")


if __name__ == "__main__":
    main()
