"""Etapa 4: configuracao por ambiente, modo de producao, cookies, proxy e arquivos de implantacao.

A configuracao e lida no import; por isso cada cenario roda num subprocesso com ambiente proprio.
A chave de producao e gerada na hora e os testes conferem que ela nunca aparece na saida.
"""
import importlib.metadata
import json
import re
import secrets
import subprocess
import sys
import time
import unittest
import urllib.request

from tests import BANCO, RAIZ
from tests import helpers as h

CHAVE = secrets.token_hex(32)

# Importa o painel (via wsgi) com a configuracao do ambiente e exercita login, CSRF e rotas.
SONDA_PAINEL = h.BLOQUEIO_VISAO + r"""
import json, re, sys
import wsgi
app, base, senha = wsgi.app, sys.argv[1], sys.argv[2]
c = app.test_client()
r = {"secure": app.config["SESSION_COOKIE_SECURE"], "httponly": app.config["SESSION_COOKIE_HTTPONLY"],
     "samesite": app.config["SESSION_COOKIE_SAMESITE"], "proxyfix": type(app.wsgi_app).__name__}
r["sem_login"] = c.get("/", base_url=base).status_code
pagina = c.get("/login", base_url=base)
r["cabecalhos"] = {k: pagina.headers.get(k) for k in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy")}
token = re.search(r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)).group(1)
r["login_sem_csrf"] = c.post("/login", base_url=base, data={"email": "admin@teste.com", "senha": senha}).status_code
r["login_errado"] = c.post("/login", base_url=base,
                           data={"email": "admin@teste.com", "senha": "errada", "csrf_token": token}).status_code
resp = c.post("/login", base_url=base, data={"email": "admin@teste.com", "senha": senha, "csrf_token": token})
r["login"] = resp.status_code
r["set_cookie"] = [re.sub(r"session=[^;]*", "session=<oculto>", v) for v in resp.headers.getlist("Set-Cookie")]
for url in ("/", "/pessoas", "/resumos"):
    r[url] = c.get(url, base_url=base).status_code
r["post_sem_csrf"] = c.post("/arquivar", base_url=base,
                            data={"ate": "2999-12-31", "confirmacao": "ARQUIVAR"}).status_code
print("RESULTADO=" + json.dumps(r))
"""

# Cinco senhas erradas, cada uma com um X-Forwarded-For diferente, e depois a senha certa.
SONDA_PROXY = h.BLOQUEIO_VISAO + r"""
import json, re, sys
import wsgi
c = wsgi.app.test_client()
def tentar(ip, senha):
    t = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
    return c.post("/login", data={"email": "admin@teste.com", "senha": senha, "csrf_token": t},
                  headers={"X-Forwarded-For": ip}).status_code
for i in range(5):
    tentar(f"203.0.113.{i}", "errada")
print("RESULTADO=" + json.dumps({"sexta": tentar("203.0.113.99", sys.argv[1])}))
"""


class Base(unittest.TestCase):
    def setUp(self):
        h.criar_banco(1)

    def assertSemSegredo(self, r):
        saida = r.stdout + r.stderr
        self.assertNotIn(CHAVE, saida)
        self.assertNotIn(h.SENHA_ADMIN, saida)

    def falha_limpa(self, r, texto):
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(texto, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertSemSegredo(r)

    def assertPainelFunciona(self, d):
        self.assertEqual((d["sem_login"], d["login_sem_csrf"], d["login_errado"], d["login"]), (302, 400, 200, 302))
        self.assertEqual((d["/"], d["/pessoas"], d["/resumos"], d["post_sem_csrf"]), (200, 200, 200, 400))
        self.assertEqual(d["cabecalhos"], {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff",
                                           "Referrer-Policy": "same-origin"})


class DesenvolvimentoTest(Base):
    def test_sem_chave_funciona_e_avisa(self):
        r = h.python(["-c", SONDA_PAINEL, "http://localhost", h.SENHA_ADMIN])
        d = h.resultado_sonda(r)
        self.assertIn("AVISO: OVERFLOW_SECRET_KEY", r.stderr)
        self.assertEqual((d["secure"], d["httponly"], d["samesite"]), (False, True, "Lax"))
        self.assertPainelFunciona(d)
        self.assertSemSegredo(r)

    def test_cookie_secure_opcional(self):
        d = h.resultado_sonda(h.python(["-c", SONDA_PAINEL, "https://localhost", h.SENHA_ADMIN],
                                       OVERFLOW_COOKIE_SECURE="1"))
        self.assertTrue(d["secure"])


class ProducaoTest(Base):
    def test_sem_chave_falha(self):
        self.falha_limpa(h.python(["-c", "import wsgi"], OVERFLOW_AMBIENTE="producao"),
                         "OVERFLOW_SECRET_KEY e obrigatoria")

    def test_chave_so_com_espacos_falha(self):
        self.falha_limpa(h.python(["-c", "import wsgi"], OVERFLOW_AMBIENTE="producao", OVERFLOW_SECRET_KEY="   "),
                         "OVERFLOW_SECRET_KEY e obrigatoria")

    def test_chave_curta_falha_sem_exibir(self):
        curta = CHAVE[:20]
        r = h.python(["-c", "import wsgi"], OVERFLOW_AMBIENTE="producao", OVERFLOW_SECRET_KEY=curta)
        self.falha_limpa(r, "pelo menos 32 caracteres")
        self.assertNotIn(curta, r.stdout + r.stderr)

    def test_falha_antes_de_tocar_o_banco(self):
        antes = BANCO.read_bytes()
        h.python(["-c", "import wsgi"], OVERFLOW_AMBIENTE="producao")
        self.assertEqual(BANCO.read_bytes(), antes)

    def test_ambiente_invalido_falha(self):
        self.falha_limpa(h.python(["-c", "import wsgi"], OVERFLOW_AMBIENTE="prod", OVERFLOW_SECRET_KEY=CHAVE),
                         "OVERFLOW_AMBIENTE deve ser")

    def test_chave_valida(self):
        r = h.python(["-c", SONDA_PAINEL, "https://localhost", h.SENHA_ADMIN],
                     OVERFLOW_AMBIENTE="producao", OVERFLOW_SECRET_KEY=CHAVE)
        d = h.resultado_sonda(r)
        self.assertNotIn("AVISO", r.stderr)
        self.assertEqual((d["secure"], d["httponly"], d["samesite"]), (True, True, "Lax"))
        for atributo in ("Secure", "HttpOnly", "SameSite=Lax"):
            self.assertIn(atributo, d["set_cookie"][0])
        self.assertPainelFunciona(d)
        self.assertNotEqual(d["proxyfix"], "ProxyFix")      # sem proxy configurado
        self.assertSemSegredo(r)

    def test_cookie_secure_nao_pode_ser_desligado(self):
        d = h.resultado_sonda(h.python(["-c", SONDA_PAINEL, "https://localhost", h.SENHA_ADMIN],
                                       OVERFLOW_AMBIENTE="producao", OVERFLOW_SECRET_KEY=CHAVE,
                                       OVERFLOW_COOKIE_SECURE="0"))
        self.assertTrue(d["secure"])


class ProxyTest(Base):
    def test_sem_proxy_ignora_x_forwarded_for(self):
        d = h.resultado_sonda(h.python(["-c", SONDA_PROXY, h.SENHA_ADMIN]))
        self.assertEqual(d["sexta"], 429)          # trocar o cabecalho nao burla o limite de tentativas

    def test_com_proxy_configurado_usa_ip_encaminhado(self):
        d = h.resultado_sonda(h.python(["-c", SONDA_PROXY, h.SENHA_ADMIN], OVERFLOW_PROXIES_CONFIAVEIS="1"))
        self.assertEqual(d["sexta"], 302)          # cada IP real tem o proprio contador

    def test_proxyfix_usa_a_contagem_configurada(self):
        r = h.python(["-c", h.BLOQUEIO_VISAO + "from overflow.web.dashboard import app; w = app.wsgi_app; "
                      "print(type(w).__name__, w.x_for, w.x_proto, w.x_host)"], OVERFLOW_PROXIES_CONFIAVEIS="2")
        self.assertEqual(r.stdout.split(), ["ProxyFix", "2", "2", "2"], r.stderr)

    def test_valores_invalidos(self):
        for valor in ("abc", "-1", "6"):
            r = h.python(["-c", "from overflow import config"], OVERFLOW_PROXIES_CONFIAVEIS=valor)
            self.assertNotEqual(r.returncode, 0, valor)
            self.assertIn("OVERFLOW_PROXIES_CONFIAVEIS", r.stderr)


class ConfiguracaoTest(unittest.TestCase):
    def test_variaveis(self):
        r = h.python(["-c", "from overflow import config as c; import json; print(json.dumps([str(c.BANCO), "
                      "str(c.MODELOS_DIR), str(c.MODELO_DETECCAO), str(c.MODELO_FACE_DETECTOR), c.CAMERA_FONTE, "
                      "c.WEB_HOST, c.WEB_PORTA, c.ID_EMPRESA, c.AMBIENTE]))"],
                     OVERFLOW_MODELOS_DIR=r"C:\ficticio\modelos", OVERFLOW_MODELO_DETECCAO=r"C:\ficticio\yolo.pt",
                     OVERFLOW_CAMERA_FONTE="2", OVERFLOW_HOST="0.0.0.0", OVERFLOW_PORTA="8081",
                     OVERFLOW_ID_EMPRESA="3")
        self.assertEqual(json.loads(r.stdout), [str(BANCO), r"C:\ficticio\modelos", r"C:\ficticio\yolo.pt",
                                                r"C:\ficticio\modelos\face_detection_yunet_2023mar.onnx",
                                                2, "0.0.0.0", 8081, 3, "desenvolvimento"])

    def test_padroes(self):
        # So le a configuracao (nao abre nenhum banco): sem OVERFLOW_BANCO, o padrao e banco.db na raiz.
        env = {k: v for k, v in h.env_teste().items() if k != "OVERFLOW_BANCO"}
        r = subprocess.run([sys.executable, "-B", "-c", "from overflow import config as c; import json; "
                            "print(json.dumps([str(c.BANCO), str(c.MODELO_DETECCAO), c.CAMERA_FONTE, c.WEB_HOST, "
                            "c.WEB_PORTA, c.PROXIES_CONFIAVEIS, c.PRODUCAO, c.ID_EMPRESA]))"],
                           cwd=RAIZ, env=env, capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(json.loads(r.stdout), [str(RAIZ / "banco.db"), str(RAIZ / "yolo26n.pt"),
                                                0, "127.0.0.1", 5000, 0, False, None])

    def test_valores_invalidos(self):
        for nome, valor in (("OVERFLOW_PORTA", "0"), ("OVERFLOW_PORTA", "70000"), ("OVERFLOW_PORTA", "abc"),
                            ("OVERFLOW_CAMERA_FONTE", "-1"), ("OVERFLOW_CAMERA_FONTE", "x"),
                            ("OVERFLOW_ID_EMPRESA", "0"), ("OVERFLOW_ID_EMPRESA", "abc")):
            r = h.python(["-c", "from overflow import config"], **{nome: valor})
            self.assertNotEqual(r.returncode, 0, (nome, valor))
            self.assertIn(nome, r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_camera_usa_configuracao(self):
        r = h.python(["-c", "from overflow.visao import camera; print(camera.FONTE, camera.MODELO_DETECCAO)"],
                     OVERFLOW_CAMERA_FONTE="3", OVERFLOW_MODELO_DETECCAO=r"C:\ficticio\yolo.pt")
        self.assertEqual(r.stdout.split(), ["3", r"C:\ficticio\yolo.pt"], r.stderr)

    def test_parametros_de_deteccao_inalterados(self):
        r = h.python(["-c", "from overflow.visao import camera as c; print(c.FONTE, c.IMGSZ, c.CONFIANCA, c.IOU, "
                      "c.MAX_DET, c.LINHA_SUPERIOR, c.LINHA_INFERIOR)"])
        self.assertEqual(r.stdout.split(), ["0", "640", "0.2", "0.5", "50", "0.425", "0.575"], r.stderr)


class ServidorRealTest(Base):
    def test_sobe_no_host_e_porta_configurados(self):
        porta = str(h.porta_livre())
        proc = subprocess.Popen([sys.executable, "-B", "-m", "overflow.web.dashboard"], cwd=RAIZ,
                                env=h.env_teste(OVERFLOW_PORTA=porta, OVERFLOW_SECRET_KEY=CHAVE),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        try:
            status = None
            for _ in range(60):
                try:
                    status = urllib.request.urlopen(f"http://127.0.0.1:{porta}/login", timeout=2).status
                    break
                except OSError:
                    time.sleep(0.5)
            self.assertEqual(status, 200)
        finally:
            proc.terminate()
            saida, _ = proc.communicate(timeout=20)
        self.assertIn(f"127.0.0.1:{porta}", saida)
        self.assertNotIn(CHAVE, saida)


class ArquivosDeImplantacaoTest(unittest.TestCase):
    def test_env_example_sem_segredos_e_completo(self):
        texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
        valores = dict(re.findall(r"^(OVERFLOW_[A-Z_]+)=(.*)$", texto, re.M))
        self.assertEqual(valores["OVERFLOW_SECRET_KEY"], "")
        self.assertEqual(valores["OVERFLOW_ADMIN_PASSWORD"], "")
        codigo = "".join(p.read_text(encoding="utf-8") for p in (RAIZ / "overflow").rglob("*.py"))
        codigo += (RAIZ / "scripts" / "migrar_banco.py").read_text(encoding="utf-8")
        self.assertEqual(set(valores), set(re.findall(r'"(OVERFLOW_[A-Z_]+)"', codigo)))

    def test_requirements_fixados_e_iguais_ao_instalado(self):
        fixados = {}
        for nome in ("requirements.txt", "requirements-web.txt"):
            for linha in (RAIZ / nome).read_text(encoding="utf-8").splitlines():
                m = re.fullmatch(r"([A-Za-z0-9_.-]+)==(\S+)", linha.strip())
                if m:
                    fixados[m.group(1)] = m.group(2)
        self.assertEqual(set(fixados), {"Flask", "Werkzeug", "numpy", "opencv-python", "ultralytics", "lap",
                                        "torch", "torchvision"})
        for pacote, versao in fixados.items():
            self.assertEqual(importlib.metadata.version(pacote), versao, pacote)

    def test_painel_sem_visao_computacional(self):
        h.criar_banco(1)
        r = h.python(["-c", h.BLOQUEIO_VISAO + "import wsgi; print(wsgi.app.test_client().get('/login').status_code)"])
        self.assertEqual(r.stdout.strip(), "200", r.stderr)


if __name__ == "__main__":
    unittest.main()
