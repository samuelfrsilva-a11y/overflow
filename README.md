# Overflow — contagem de pessoas

Conta entradas e saídas de pessoas com uma webcam (YOLO + ByteTrack, somente CPU) e
mostra os dados num painel web (Flask) com login, separado por empresa.

```
overflow/
  config.py          caminhos e configuração (variáveis de ambiente)
  db/                acesso ao SQLite: sessões, resumos mensais, empresa, repositório
  visao/camera.py    captura da webcam, detecção, rastreamento e contagem
  visao/contador.py  lógica de contagem/reidentificação (sem OpenCV; usada nos testes)
  web/dashboard.py   painel Flask (login, CSRF, dashboard, pessoas, resumos)
scripts/             criação/migração do banco, consulta, cadastro de rosto, redefinição de senha
templates/           páginas HTML do painel
tests/               testes (unittest) com banco descartável e dados fictícios
wsgi.py              ponto de entrada para servidor WSGI
```

## Requisitos

- Python 3.14 (versão usada no desenvolvimento; outras versões não foram testadas).
- Windows 11 para a câmera (o código tenta os backends DirectShow, Media Foundation e o padrão do OpenCV).
- Uma webcam, somente para a contagem. O painel funciona sem câmera.

## Instalação (PowerShell)

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
# completa (painel + câmera; baixa PyTorch CPU, ~centenas de MB):
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# ou somente o painel web:
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
```

### Modelos (não vêm no repositório)

Os pesos são de terceiros e ficam fora do Git. Baixe-os **somente das fontes oficiais** e coloque-os
nestes caminhos (ou aponte outro caminho com `OVERFLOW_MODELO_DETECCAO` / `OVERFLOW_MODELOS_DIR`):

| Arquivo | Uso | Licença | Fonte oficial |
|---|---|---|---|
| `yolo26n.pt` (raiz do projeto) | detecção de pessoas na câmera | AGPL-3.0 ou Licença Enterprise (Ultralytics) | https://github.com/ultralytics/assets/releases |
| `modelos/face_detection_yunet_2023mar.onnx` | cadastro de rosto | MIT | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |
| `modelos/face_recognition_sface_2021dec.onnx` | cadastro de rosto | Apache-2.0 | https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface |

O pacote `ultralytics` também baixa os pesos oficiais automaticamente quando recebe só o nome do modelo
(ex.: `YOLO("yolo26n.pt")`); com o caminho absoluto usado pelo Overflow, não foi verificado se o
download automático acontece — se o arquivo faltar, baixe-o manualmente. O repositório **não inclui**
datasets nem modelos treinados: não há modelo próprio de uniformes, e as imagens locais de uniformes
não podem ser publicadas (origem e direitos de uso não comprovados).

## Configuração

Toda a configuração vem de variáveis de ambiente; veja `.env.example`, que traz só nomes e exemplos
fictícios (o Overflow **não** lê arquivos `.env` automaticamente). Nenhum segredo fica no código.
Valores inválidos interrompem a execução com uma mensagem clara; chaves nunca são exibidas.

Em desenvolvimento nada é obrigatório: sem `OVERFLOW_SECRET_KEY`, o painel gera uma chave temporária
(os logins caem ao reiniciar) e avisa no terminal.

| Variável | Padrão | Para quê |
|---|---|---|
| `OVERFLOW_AMBIENTE` | `desenvolvimento` | `producao` liga as exigências de produção; qualquer outro valor interrompe |
| `OVERFLOW_SECRET_KEY` | (temporária) | assina o cookie de login; **obrigatória em produção**, ≥ 32 caracteres |
| `OVERFLOW_BANCO` | `banco.db` na raiz | caminho do SQLite |
| `OVERFLOW_ID_EMPRESA` | (única empresa) | empresa da câmera e do cadastro; obrigatória se houver mais de uma |
| `OVERFLOW_CAMERA_FONTE` | `0` | índice da webcam (≥ 0) |
| `OVERFLOW_MODELO_DETECCAO` | `yolo26n.pt` na raiz | pesos do YOLO |
| `OVERFLOW_MODELOS_DIR` | `modelos` | pasta dos modelos ONNX de rosto |
| `OVERFLOW_HOST` / `OVERFLOW_PORTA` | `127.0.0.1` / `5000` | endereço do painel (porta 1–65535) |
| `OVERFLOW_PROXIES_CONFIAVEIS` | `0` | número **exato** de proxies reversos na frente do painel (0–5); `0` ignora `X-Forwarded-*` |
| `OVERFLOW_COOKIE_SECURE` | — | só em desenvolvimento: `1` força cookie `Secure` (em produção ele é sempre `Secure`) |
| `OVERFLOW_ADMIN_PASSWORD` | — | usada só por `scripts/migrar_banco.py` para criar o primeiro administrador |

```powershell
$env:OVERFLOW_SECRET_KEY = (.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))")
```

## Produção (preparação; nada foi implantado)

- `OVERFLOW_AMBIENTE=producao` e `OVERFLOW_SECRET_KEY` guardada no gerenciador de segredos do servidor.
  Sem chave válida o painel não inicia.
- O cookie de sessão fica `Secure`, `HttpOnly` e `SameSite=Lax`: o painel **precisa** de HTTPS, fornecido
  por um proxy reverso ou túnel. O Flask não serve HTTPS.
- Mantenha `OVERFLOW_HOST=127.0.0.1` e defina `OVERFLOW_PROXIES_CONFIAVEIS` (normalmente `1`).
- Use um servidor WSGI com `wsgi:app` e **1 processo** (o limite de tentativas de login fica na memória
  do processo). Detalhes e opções de hospedagem em `HOSPEDAGEM.md`.

## Banco de dados

Banco novo (ou atualização de um existente — os scripts criam tabelas/colunas que faltam e não apagam
dados; `migrar_banco.py` associa à primeira empresa os registros que ainda não têm empresa):

```powershell
.\.venv\Scripts\python.exe scripts\estrutura_banco.py
.\.venv\Scripts\python.exe scripts\indice_banco.py
$env:OVERFLOW_ADMIN_PASSWORD = "<senha forte>"     # só na primeira vez
.\.venv\Scripts\python.exe scripts\migrar_banco.py
Remove-Item Env:OVERFLOW_ADMIN_PASSWORD
```

O administrador inicial é `admin@teste.com`. Troque a senha depois do primeiro acesso com
`scripts\redefinir_senha.py --email admin@teste.com --backup <pasta-nova>`.

**Faça uma cópia do banco antes de rodar qualquer script num banco com dados reais.**
Ao abrir o painel, os meses anteriores ao atual são resumidos e seus registros movidos para
`movimentacao_arquivo` (nada é apagado).

## Execução

```powershell
# painel: http://127.0.0.1:5000
.\.venv\Scripts\python.exe -m overflow.web.dashboard

# câmera (janela do OpenCV; tecla q encerra)
.\.venv\Scripts\python.exe -m overflow.visao.camera

# cadastrar uma pessoa a partir de uma foto com um único rosto
.\.venv\Scripts\python.exe scripts\cadastrar_pessoa_rosto.py

# listar movimentações no terminal (todas as empresas)
.\.venv\Scripts\python.exe scripts\consultar.py
```

O `app.run` do Flask é o servidor de desenvolvimento. Para hospedar, use um servidor WSGI com `wsgi:app`
(veja `HOSPEDAGEM.md`).

## Testes

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -t .
```

A suíte não instala nada. Cada execução cria bancos descartáveis numa pasta temporária, com dados
fictícios gerados pelos próprios scripts do projeto, e apaga tudo ao terminar. O pacote `tests`
configura `OVERFLOW_BANCO` antes de importar a aplicação e bloqueia `sqlite3.connect` para qualquer
banco em arquivo fora dessa pasta (inclusive `banco.db`). Senhas e chaves de teste são geradas na hora.

| Módulo | Cobre |
|---|---|
| `test_empresa.py` | movimentações da câmera e cadastros associados à empresa certa; recusa quando é ambíguo |
| `test_resumos.py` | resumos mensais isolados por empresa, resumos antigos, arquivamento, virada de mês |
| `test_estrutura_banco.py` | esquema criado por `scripts/estrutura_banco.py`, atualização de bancos antigos, idempotência |
| `test_producao.py` | modos desenvolvimento/produção, chave secreta, cookies, cabeçalhos, proxy, configuração, servidor real, requirements e `.env.example` |
| `test_painel.py` | login, CSRF, limite de tentativas, logout, isolamento no dashboard e na página de pessoas |
| `test_scripts.py` | migração segura, hash da senha, consulta, verificação de conta somente leitura |
| `test_contagem.py` | lógica de contagem do `Contador` (sem OpenCV) |
| `test_integracao.py` | fluxo cadastro → câmera → painel → resumo, pontos de entrada, sintaxe, proteções da suíte |
| `test_pacote.py` | ausência de bancos, modelos, mídia, segredos, `.env`, ambientes e arquivos grandes no pacote |

Não cobrem: captura real da webcam, inferência do YOLO/ByteTrack, reconhecimento facial com fotos reais
(o cadastro é testado com um `cv2` simulado) e servidores WSGI (waitress/gunicorn não estão nos
requirements nem foram testados). Sem OpenCV/ultralytics instalados, os testes da câmera são pulados.

## Privacidade

O banco guarda **embeddings faciais**, que são dados biométricos (dado pessoal sensível na LGPD).
Nunca versione bancos, fotos, vídeos ou backups; o `.gitignore` bloqueia esses formatos.

O pacote `ultralytics` envia por padrão métricas de uso anônimas (não envia imagens, segundo
https://docs.ultralytics.com/help/privacy/). Em instalações com câmera, desligue uma vez no ambiente:

```powershell
.\.venv\Scripts\python.exe -c "from ultralytics import settings; settings.update({'sync': False})"
```

## Licença

O Overflow é software livre sob a **GNU Affero General Public License v3.0** (`AGPL-3.0-only`) —
texto oficial completo em [`LICENSE`](LICENSE), aviso de copyright e explicações em
[`NOTICE.md`](NOTICE.md).

- O projeto usa o **Ultralytics YOLO** (AGPL-3.0). Por isso todo o Overflow é aberto sob a mesma
  licença: quem distribuir o Overflow, ou oferecer uma versão **modificada** pela rede, deve
  disponibilizar o código-fonte correspondente completo sob AGPL-3.0.
- Uso comercial **sem** abrir o código exige a Licença Enterprise da Ultralytics
  (https://www.ultralytics.com/pt/license).
- Componentes de terceiros (bibliotecas, modelos, Chart.js) **não estão incluídos** e mantêm as próprias
  licenças — inventário completo, com versões e fontes oficiais, em
  [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
- Se o Overflow for distribuído como binário (instalador, executável, Docker), inclua também as
  licenças LGPL do FFmpeg/Qt embutidos no `opencv-python` (ver `THIRD_PARTY_LICENSES.md`).
