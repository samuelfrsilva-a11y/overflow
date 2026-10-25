"""Logica de contagem e reidentificacao do Overflow.

Este modulo NAO depende de OpenCV nem do banco de dados: recebe caixas ja
rastreadas pelo YOLO/ByteTrack e devolve eventos (entrada, saida, ...).

Ideias principais
-----------------
1. CONTAGEM e independente de identidade. Toda travessia da linha, em qualquer
   sentido, conta. Usa histerese (faixa morta) em vez da sequencia
   cima -> meio -> baixo, entao travessias rapidas nao sao perdidas.
2. FUSAO de rastros: se o ByteTrack perde alguem e cria um ID novo logo em
   seguida, o rastro antigo (com seu lado e sua identidade) e herdado.
3. IDENTIDADES (galeria): cada pessoa tem uma Identidade que sobrevive aos IDs
   do rastreador. Rosto (SFace) e a evidencia principal; cor da roupa e apenas
   apoio na saida. Quem volta depois de 15 min e reconhecido e a saida e
   fechada na identidade de quem entrou.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class Config:
    # Geometria da linha (fracao do frame)
    eixo: str = "y"                       # "y": linha horizontal; "x": vertical
    linha: float = 0.5
    margem: float = 0.05                  # histerese: faixa morta de cada lado
    entrada_sentido_positivo: bool = True  # True: entrar = y/x crescente

    # Filtro de caixas (pequeno, so para descartar lixo)
    min_largura: int = 30
    min_altura: int = 60
    min_obs: int = 3                      # observacoes antes de poder contar

    # Fusao de rastros perdidos
    fusao_tempo: float = 2.5              # s
    fusao_dist: float = 1.2               # em alturas de caixa
    ttl_rastro: float = 30.0              # s ate esquecer um rastro

    # Reconhecimento (cosseno do SFace)
    limite_face_cadastrado: float = 0.363
    limite_face_visitante: float = 0.40
    limite_face_ja_dentro: float = 0.55   # exigido para "reentrada" de quem consta dentro
    limite_cor: float = 0.85
    margem_cor: float = 0.05

    # Amostragem de aparencia
    max_amostras_face: int = 8
    max_amostras_cor: int = 6
    intervalo_amostra: float = 0.25       # s entre amostras de um mesmo rastro
    janela_amostra: float = 0.35          # fracao do frame ao redor da linha
    janela_refino: float = 4.0            # s apos cruzar em que ainda se amostra


@dataclass(eq=False)
class Identidade:
    uid: int                              # >0 visitante; <0 cadastrado (-id_pessoa)
    nome: str
    tipo: str = "visitante"
    id_pessoa: Optional[int] = None
    codigo: Optional[str] = None
    faces: List[np.ndarray] = field(default_factory=list)
    cores: List[np.ndarray] = field(default_factory=list)
    dentro: bool = False
    seq_entrada: int = 0
    fechada_estimada: bool = False       # saida atribuida por estimativa
    fechada_quando: Optional[datetime] = None


@dataclass(eq=False)
class Rastro:
    rid: int
    tid: int
    visto_t: float
    centro: Tuple[float, float]
    alt: float
    caixa: Tuple[float, float, float, float] = (0, 0, 0, 0)
    vel: Tuple[float, float] = (0.0, 0.0)
    n_obs: int = 0
    lado_ref: Optional[int] = None
    origem: int = 0
    ident: Optional[Identidade] = None
    palpite: Optional[Identidade] = None   # so para exibir o nome antes de cruzar
    faces: List[np.ndarray] = field(default_factory=list)
    cores: List[np.ndarray] = field(default_factory=list)
    ult_amostra: float = -1e9
    cruzou_t: Optional[float] = None


@dataclass
class Evento:
    tipo: str            # entrada|saida: abrir|fechar|novo_visitante|mesclar|faces|aviso
    t: float
    ident: Optional[Identidade] = None
    alvo: Optional[Identidade] = None      # destino em "mesclar"
    confianca: str = ""
    dados: object = None
    quando: datetime = field(default_factory=datetime.now)


def _unit(v: np.ndarray) -> Optional[np.ndarray]:
    v = np.asarray(v, dtype=np.float32).ravel()
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else None


def _sim_cor(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.minimum(a, b).sum() / max(float(a.sum()), 1e-9))


class Contador:
    def __init__(self, cfg: Optional[Config] = None, uid_inicial: int = 1):
        self.cfg = cfg or Config()
        self.identidades: List[Identidade] = []
        self._uid = itertools.count(uid_inicial)
        self._rid = itertools.count(1)
        self._seq = itertools.count(1)
        self._rastros: Dict[int, Rastro] = {}
        self._por_tid: Dict[int, Rastro] = {}
        self.entradas = 0
        self.saidas = 0
        self.saidas_sem_associacao = 0
        self.dentro_inicial = 0

    # ------------------------------------------------------------------ API
    @property
    def dentro(self) -> int:
        return max(0, self.dentro_inicial + self.entradas - self.saidas)

    def registrar_cadastrado(self, id_pessoa: int, nome: str, tipo: str,
                             codigo: Optional[str], embeddings: Sequence[np.ndarray]) -> Identidade:
        ident = next((i for i in self.identidades if i.id_pessoa == id_pessoa), None)
        if ident is None:
            ident = Identidade(uid=-int(id_pessoa), nome=nome or f"Pessoa {id_pessoa}",
                               tipo=tipo or "cadastrado", id_pessoa=id_pessoa, codigo=codigo)
            self.identidades.append(ident)
        for e in embeddings:
            u = _unit(e)
            if u is not None:
                ident.faces.append(u)
        return ident

    def registrar_visitante(self, uid: int, embeddings: Sequence[np.ndarray],
                            dentro: bool = False) -> Identidade:
        ident = Identidade(uid=uid, nome=f"Visitante {uid:04d}")
        for e in embeddings:
            u = _unit(e)
            if u is not None:
                ident.faces.append(u)
        ident.dentro = dentro
        if dentro:
            ident.seq_entrada = next(self._seq)
        self.identidades.append(ident)
        return ident

    def marcar_dentro(self, ident: Identidade) -> None:
        if not ident.dentro:
            ident.dentro = True
            ident.seq_entrada = next(self._seq)

    def atualizar(self, t: float, deteccoes: Sequence[Tuple[int, Sequence[float]]],
                  largura: int, altura: int) -> Tuple[List[Rastro], List[Evento]]:
        cfg = self.cfg
        eventos: List[Evento] = []
        validas = []
        for tid, caixa in deteccoes:
            x1, y1, x2, y2 = (float(v) for v in caixa)
            if (x2 - x1) < cfg.min_largura or (y2 - y1) < cfg.min_altura:
                continue
            validas.append((int(tid), (x1, y1, x2, y2)))
        tids_agora = {tid for tid, _ in validas}

        if cfg.eixo == "y":
            limite, margem_px = cfg.linha * altura, cfg.margem * altura
        else:
            limite, margem_px = cfg.linha * largura, cfg.margem * largura

        atuais: List[Rastro] = []
        for tid, caixa in validas:
            x1, y1, x2, y2 = caixa
            centro = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            alt = y2 - y1
            r = self._por_tid.get(tid)
            if r is None:
                r = self._fundir(tid, centro, t, tids_agora)
                if r is None:
                    r = Rastro(rid=next(self._rid), tid=tid, visto_t=t, centro=centro, alt=alt)
                    self._rastros[r.rid] = r
                self._por_tid[tid] = r
            self._observar(r, centro, alt, caixa, t)
            atuais.append(r)
            eventos += self._checar_cruzamento(r, centro, limite, margem_px, t)

        self._limpar(t)
        return atuais, eventos

    def precisa_amostra(self, r: Rastro, t: float, largura: int, altura: int) -> bool:
        cfg = self.cfg
        if len(r.faces) >= cfg.max_amostras_face and len(r.cores) >= cfg.max_amostras_cor:
            return False
        if t - r.ult_amostra < cfg.intervalo_amostra:
            return False
        if cfg.eixo == "y":
            coord, dim, limite = r.centro[1], altura, cfg.linha * altura
        else:
            coord, dim, limite = r.centro[0], largura, cfg.linha * largura
        perto = abs(coord - limite) <= cfg.janela_amostra * dim
        refino = r.cruzou_t is not None and (t - r.cruzou_t) <= cfg.janela_refino
        return perto or refino

    def adicionar_amostra(self, r: Rastro, t: float, face: Optional[np.ndarray],
                          cor: Optional[np.ndarray]) -> List[Evento]:
        cfg = self.cfg
        eventos: List[Evento] = []
        r.ult_amostra = t
        face = _unit(face) if face is not None else None
        if cor is not None and len(r.cores) < cfg.max_amostras_cor:
            r.cores.append(np.asarray(cor, dtype=np.float32))
        if face is None:
            return eventos
        if len(r.faces) < cfg.max_amostras_face:
            r.faces.append(face)

        ident = r.ident
        if ident is None:
            alvo, _ = self._melhor_por_face([face], limite_dentro=cfg.limite_face_ja_dentro)
            r.palpite = alvo
            return eventos

        if not ident.faces and ident.dentro:
            # Identidade provisoria (entrou sem rosto): tenta descobrir quem e.
            alvo, _ = self._melhor_por_face([face], excluir=ident)
            if alvo is not None and not alvo.dentro:
                eventos.append(Evento("mesclar", t, ident=ident, alvo=alvo, confianca="face"))
                alvo.dentro, alvo.seq_entrada = True, ident.seq_entrada
                if ident in self.identidades:
                    self.identidades.remove(ident)
                r.ident = ident = alvo
        eventos += self._absorver(ident, [face], [], t)
        return eventos

    def nome_exibicao(self, r: Rastro) -> str:
        ident = r.ident or r.palpite
        return ident.nome if ident is not None else "?"

    # ------------------------------------------------------------ rastros
    def _observar(self, r: Rastro, centro, alt, caixa, t) -> None:
        dt = t - r.visto_t
        if r.n_obs > 0 and 1e-6 < dt <= 0.5:
            vx = (centro[0] - r.centro[0]) / dt
            vy = (centro[1] - r.centro[1]) / dt
            r.vel = (0.5 * vx + 0.5 * r.vel[0], 0.5 * vy + 0.5 * r.vel[1])
        r.centro, r.alt, r.caixa, r.visto_t = centro, alt, caixa, t
        r.n_obs += 1

    def _fundir(self, tid, centro, t, tids_agora) -> Optional[Rastro]:
        cfg = self.cfg
        melhor, custo_min = None, cfg.fusao_dist
        for r in self._rastros.values():
            if r.tid in tids_agora:
                continue
            dt = t - r.visto_t
            if dt <= 0 or dt > cfg.fusao_tempo:
                continue
            k = min(dt, 0.5)
            px, py = r.centro[0] + r.vel[0] * k, r.centro[1] + r.vel[1] * k
            custo = math.hypot(centro[0] - px, centro[1] - py) / max(r.alt, 1.0)
            if custo < custo_min:
                melhor, custo_min = r, custo
        if melhor is not None:
            if self._por_tid.get(melhor.tid) is melhor:
                del self._por_tid[melhor.tid]
            melhor.tid = tid
        return melhor

    def _limpar(self, t: float) -> None:
        mortos = [rid for rid, r in self._rastros.items() if t - r.visto_t > self.cfg.ttl_rastro]
        for rid in mortos:
            r = self._rastros.pop(rid)
            if self._por_tid.get(r.tid) is r:
                del self._por_tid[r.tid]

    # --------------------------------------------------------- cruzamento
    def _checar_cruzamento(self, r: Rastro, centro, limite, margem_px, t) -> List[Evento]:
        coord = centro[1] if self.cfg.eixo == "y" else centro[0]
        d = coord - limite
        s = 1 if d > margem_px else (-1 if d < -margem_px else 0)
        if r.n_obs == 1:
            r.origem = 1 if d >= 0 else -1
            if s:
                r.lado_ref = s
            return []
        if s == 0:
            return []
        ref = r.lado_ref if r.lado_ref is not None else r.origem
        if s == ref:
            r.lado_ref = s
            return []
        if r.n_obs < self.cfg.min_obs:
            return []                      # pendente: confirma quando tiver observacoes
        r.lado_ref = s
        r.cruzou_t = t
        entrou = (s > 0) == self.cfg.entrada_sentido_positivo
        return self._entrada(r, t) if entrou else self._saida(r, t)

    def _entrada(self, r: Rastro, t: float) -> List[Evento]:
        self.entradas += 1
        eventos: List[Evento] = []
        ident, via = None, "nova"
        if r.faces:
            ident, _ = self._melhor_por_face(r.faces, limite_dentro=self.cfg.limite_face_ja_dentro)
            if ident is not None:
                via = "face"
        if ident is not None and ident.dentro:
            # Consta dentro mas entrou de novo: a saida anterior nao foi vista.
            eventos.append(Evento("fechar", t, ident=ident, confianca="inferida"))
            ident.dentro = False
        if ident is None:
            ident = Identidade(uid=next(self._uid), nome="")
            ident.nome = f"Visitante {ident.uid:04d}"
            self.identidades.append(ident)
            eventos.append(Evento("novo_visitante", t, ident=ident))
        ident.dentro = True
        ident.fechada_estimada = False
        ident.seq_entrada = next(self._seq)
        r.ident = ident
        eventos += self._absorver(ident, r.faces, r.cores, t)
        eventos.append(Evento("abrir", t, ident=ident, confianca=via))
        return eventos

    def _saida(self, r: Rastro, t: float) -> List[Evento]:
        self.saidas += 1
        ident, via = None, ""
        if r.ident is not None and r.ident.dentro:
            ident, via = r.ident, "rastro"
        elif r.faces:
            ident, _ = self._melhor_por_face(r.faces)
            via = "face" if ident is not None else ""
        if ident is None and r.cores and not r.faces:
            ident = self._melhor_por_cor(r)
            via = "aparencia" if ident is not None else ""
        if ident is None and not r.faces:
            ident = self._mais_antigo_dentro()
            via = "estimada" if ident is not None else ""

        if ident is None:
            self.saidas_sem_associacao += 1
            return [Evento("aviso", t, confianca="saida sem entrada associada")]
        if not ident.dentro:
            if ident.fechada_estimada and via == "face":
                return self._corrigir_estimativa(ident, r, t)
            self.saidas_sem_associacao += 1
            return [Evento("aviso", t, ident=ident, confianca="saida de quem nao constava dentro")]

        ident.dentro = False
        r.ident = ident
        eventos = self._absorver(ident, r.faces, [], t)
        ev = Evento("fechar", t, ident=ident, confianca=via)
        ident.fechada_estimada = via == "estimada"
        ident.fechada_quando = ev.quando
        eventos.append(ev)
        return eventos

    def _corrigir_estimativa(self, ident: Identidade, r: Rastro, t: float) -> List[Evento]:
        """Reconheceu por rosto quem ja tinha sido 'fechado' por estimativa: ele sai agora e
        a saida estimada anterior passa para o proximo candidato mais antigo."""
        anterior = ident.fechada_quando
        r.ident = ident
        ev = Evento("fechar", t, ident=ident, confianca="face", dados="corrigida")
        ident.fechada_estimada, ident.fechada_quando = False, ev.quando
        eventos = self._absorver(ident, r.faces, [], t) + [ev]
        outro = self._mais_antigo_dentro()
        if outro is not None:
            outro.dentro = False
            outro.fechada_estimada, outro.fechada_quando = True, anterior
            eventos.append(Evento("fechar", t, ident=outro, confianca="estimada",
                                  quando=anterior, dados="reatribuida"))
        return eventos

    # ------------------------------------------------------ identidades
    def _limite(self, ident: Identidade) -> float:
        return (self.cfg.limite_face_cadastrado if ident.id_pessoa is not None
                else self.cfg.limite_face_visitante)

    def _melhor_por_face(self, faces, excluir=None, limite_dentro=None):
        melhor, melhor_s = None, -1.0
        q = np.vstack(faces)
        for ident in self.identidades:
            if ident is excluir or not ident.faces:
                continue
            s = float((q @ np.vstack(ident.faces).T).max())
            lim = self._limite(ident)
            if ident.dentro and limite_dentro is not None:
                lim = max(lim, limite_dentro)
            if s >= lim and s > melhor_s:
                melhor, melhor_s = ident, s
        return melhor, melhor_s

    def _melhor_por_cor(self, r: Rastro) -> Optional[Identidade]:
        media = np.mean(r.cores, axis=0)
        placar = []
        for ident in self.identidades:
            if ident.dentro and ident.cores:
                placar.append((max(_sim_cor(media, c) for c in ident.cores), ident))
        if not placar:
            return None
        placar.sort(key=lambda p: -p[0])
        if placar[0][0] < self.cfg.limite_cor:
            return None
        if len(placar) > 1 and placar[0][0] - placar[1][0] < self.cfg.margem_cor:
            return None
        return placar[0][1]

    def _mais_antigo_dentro(self) -> Optional[Identidade]:
        cand = [i for i in self.identidades if i.dentro and i.id_pessoa is None]
        return min(cand, key=lambda i: i.seq_entrada) if cand else None

    def _absorver(self, ident: Identidade, faces, cores, t) -> List[Evento]:
        cfg = self.cfg
        novas = []
        for f in faces:
            if len(ident.faces) >= 3 * cfg.max_amostras_face:
                break
            if ident.faces:
                if float((np.vstack(ident.faces) @ f).max()) < self._limite(ident):
                    continue
            if any(f is g for g in ident.faces):
                continue
            ident.faces.append(f)
            novas.append(f)
        for c in cores:
            if len(ident.cores) < 3 * cfg.max_amostras_cor:
                ident.cores.append(c)
        if novas and ident.id_pessoa is None:
            return [Evento("faces", t, ident=ident, dados=novas)]
        return []
