"""O pacote de publicacao nao pode conter dados, modelos, midia, segredos nem ambientes,
e deve trazer os arquivos de licenciamento corretos."""
import hashlib
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

PASTAS_IGNORADAS = {"__pycache__", ".git"}
PASTAS_PROIBIDAS = {".venv", "venv", "env", "_backup", "modelos", "uniforme", "dados", "runs",
                    "pessoa_video", "rosto_video", "datasets"}
EXTENSOES_PROIBIDAS = {".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".db-journal", ".bak",
                       ".pt", ".pth", ".onnx", ".engine", ".tflite",
                       ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif",
                       ".mp4", ".avi", ".mov", ".mkv", ".pem", ".key", ".pyc", ".log", ".zip"}
TAMANHO_MAXIMO = 512 * 1024

PADROES_SEGREDO = [
    ("chave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("chave AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("hash de senha", re.compile(r"(?:scrypt:\d+:\d+:\d+|pbkdf2:sha\d+(?::\d+)?)\$[A-Za-z0-9]+\$[0-9a-f]{32,}")),
    ("URL com senha", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@")),
    ("variavel secreta preenchida", re.compile(r"^OVERFLOW_(?:SECRET_KEY|ADMIN_PASSWORD)=\S", re.M)),
]


def _arquivos():
    for p in RAIZ.rglob("*"):
        partes = set(p.relative_to(RAIZ).parts)
        if p.is_file() and not partes & PASTAS_IGNORADAS:
            yield p


class PacoteTest(unittest.TestCase):
    def test_sem_pastas_proibidas(self):
        achadas = [str(p.relative_to(RAIZ)) for p in RAIZ.rglob("*")
                   if p.is_dir() and p.name in PASTAS_PROIBIDAS]
        self.assertEqual(achadas, [])

    def test_sem_extensoes_proibidas(self):
        achados = [str(p.relative_to(RAIZ)) for p in _arquivos()
                   if p.suffix.lower() in EXTENSOES_PROIBIDAS or p.name.lower().endswith((".db-wal", ".db-shm"))]
        self.assertEqual(achados, [])

    def test_sem_env_real(self):
        achados = [str(p.relative_to(RAIZ)) for p in _arquivos()
                   if p.name.startswith(".env") and p.name != ".env.example"]
        self.assertEqual(achados, [])

    def test_sem_arquivos_grandes(self):
        achados = [str(p.relative_to(RAIZ)) for p in _arquivos() if p.stat().st_size > TAMANHO_MAXIMO]
        self.assertEqual(achados, [])

    def test_sem_segredos_no_texto(self):
        achados = []
        for p in _arquivos():
            try:
                texto = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                achados.append(f"{p.relative_to(RAIZ)}: arquivo binario")
                continue
            for tipo, padrao in PADROES_SEGREDO:
                if padrao.search(texto):
                    achados.append(f"{p.relative_to(RAIZ)}: {tipo}")    # so o tipo, nunca o valor
        self.assertEqual(achados, [])


# SHA-256 de https://www.gnu.org/licenses/agpl-3.0.txt (identico ao LICENSE do ultralytics 8.4.173).
SHA256_AGPL3_OFICIAL = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"


class LicenciamentoTest(unittest.TestCase):
    def test_license_e_o_texto_oficial_da_agpl3(self):
        conteudo = (RAIZ / "LICENSE").read_bytes()
        self.assertEqual(hashlib.sha256(conteudo).hexdigest(), SHA256_AGPL3_OFICIAL)
        self.assertTrue(conteudo.lstrip().startswith(b"GNU AFFERO GENERAL PUBLIC LICENSE"))

    def test_avisos_declaram_a_licenca(self):
        notice = (RAIZ / "NOTICE.md").read_text(encoding="utf-8")
        self.assertIn("AGPL-3.0-only", notice)
        self.assertIn("Copyright (C)", notice)
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Licença", readme)
        for arquivo in ("LICENSE", "NOTICE.md", "THIRD_PARTY_LICENSES.md"):
            self.assertIn(arquivo, readme)

    def test_inventario_cobre_todos_os_requirements(self):
        inventario = (RAIZ / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        fixados = []
        for nome in ("requirements.txt", "requirements-web.txt"):
            for linha in (RAIZ / nome).read_text(encoding="utf-8").splitlines():
                m = re.fullmatch(r"([A-Za-z0-9_.-]+)==(\S+)", linha.strip())
                if m:
                    fixados.append(m.groups())
        self.assertGreater(len(fixados), 5)
        for pacote, versao in fixados:
            linha = re.search(rf"^\|\s*{re.escape(pacote)}\s*\|\s*{re.escape(versao)}\s*\|.*$", inventario, re.M)
            self.assertIsNotNone(linha, f"{pacote}=={versao} ausente do THIRD_PARTY_LICENSES.md")

    def test_modelos_documentados_e_ausentes(self):
        inventario = (RAIZ / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        for modelo in ("yolo26n.pt", "face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"):
            self.assertIn(modelo, inventario)
            self.assertEqual(list(RAIZ.rglob(modelo)), [], f"{modelo} nao pode estar no pacote")


if __name__ == "__main__":
    unittest.main()
