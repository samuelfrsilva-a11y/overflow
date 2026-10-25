# Licenças de terceiros

Inventário dos componentes de terceiros usados pelo Overflow. **Nenhum deles está incluído neste
repositório**: as bibliotecas são instaladas pelo `pip` a partir dos `requirements`, os modelos são
baixados à parte e o Chart.js é carregado pelo navegador. Cada componente continua sob a sua própria
licença; a licença do Overflow (AGPL-3.0, ver `LICENSE` e `NOTICE.md`) não se aplica a eles.

Levantamento feito em 2026-10-25 sobre as versões fixadas em `requirements.txt` (Python 3.14.7,
Windows 11, PyTorch CPU). **Verificação:**
- **texto** — licença confirmada pelo arquivo de licença distribuído com a versão instalada;
- **metadados** — confirmada só pela licença declarada no pacote (o texto não foi conferido);
- **página oficial** — confirmada na página oficial do projeto (componentes que não são pacotes Python).

Isto é um inventário técnico, não um parecer jurídico.

## 1. Componente com copyleft forte (define a licença do Overflow)

| Componente | Versão | Licença | Verificação | Fonte oficial |
|---|---|---|---|---|
| `ultralytics` (YOLO, rastreadores ByteTrack/BoT-SORT, treino) | 8.4.173 | AGPL-3.0 (classificador: "v3 or later") ou Licença Enterprise | texto (idêntico ao da gnu.org) | https://github.com/ultralytics/ultralytics · https://www.ultralytics.com/pt/license |
| `ultralytics-platform` (dependência do ultralytics) | 0.1.94 | AGPL-3.0-only | texto | https://github.com/ultralytics/sdk |
| `ultralytics-thop` (dependência do ultralytics) | 2.2.3 | AGPL-3.0 | texto | https://github.com/ultralytics/thop |

**Obrigações:** quem distribui uma obra que combina o Overflow com o ultralytics deve fazê-lo sob a
AGPL-3.0, com o código-fonte correspondente completo. Se uma versão **modificada** for oferecida a
usuários pela rede, ela deve oferecer a esses usuários o código-fonte (AGPL-3.0, seção 13). A
Ultralytics afirma que modelos treinados com o seu código também ficam sob AGPL-3.0, e que uso
comercial sem abrir o projeto exige a Licença Enterprise. Detalhes em `NOTICE.md`.

O rastreador usado pela câmera (`tracker="bytetrack.yaml"`) é a **implementação da Ultralytics**
(`ultralytics/trackers/byte_tracker.py`, AGPL-3.0), não o repositório original do ByteTrack. O arquivo
`bytetrack_custom.yaml` deste projeto usa as mesmas chaves de configuração do
`ultralytics/cfg/trackers/bytetrack.yaml` (AGPL-3.0), com valores próprios; hoje ele não é usado.

## 2. Bibliotecas Python diretas (`requirements.txt` / `requirements-web.txt`)

| Pacote | Versão | Licença | Verificação | Fonte oficial |
|---|---|---|---|---|
| Flask | 3.1.3 | BSD-3-Clause | texto | https://github.com/pallets/flask |
| Werkzeug | 3.1.9 | BSD-3-Clause | texto | https://github.com/pallets/werkzeug |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | texto | https://github.com/numpy/numpy |
| opencv-python | 5.0.0.93 | MIT (empacotamento) + Apache-2.0 (OpenCV) + componentes de terceiros embutidos (ver abaixo) | texto | https://github.com/opencv/opencv-python |
| torch | 2.14.1+cpu | BSD-3-Clause (PyTorch) + Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, BSL-1.0, MIT (componentes embutidos) | texto (95 arquivos) | https://github.com/pytorch/pytorch |
| torchvision | 0.29.1+cpu | BSD-3-Clause | texto | https://github.com/pytorch/vision |
| lap | 0.5.13 | BSD-2-Clause | texto | https://github.com/gatagat/lap |
| ultralytics | 8.4.173 | AGPL-3.0 | texto | ver seção 1 |

**Binários embutidos no `opencv-python`:** o arquivo `LICENSE-3RD-PARTY.txt` do pacote informa que o
**FFmpeg (LGPL-2.1)** é redistribuído em todos os pacotes (no Windows, `opencv_videoio_ffmpeg*.dll`),
o libvpx nos pacotes Linux e o **Qt 5 (LGPL-3.0)** nos pacotes não-headless de Linux e macOS. Isso
não gera obrigação para este repositório, que só contém código-fonte. **Gera obrigações se o Overflow
for distribuído como binário** (instalador, executável, imagem Docker com as bibliotecas): incluir os
avisos e licenças LGPL e permitir a substituição dessas bibliotecas.

## 3. Dependências indiretas instaladas (runtime)

Instaladas automaticamente pelos pacotes acima. Licenças permissivas ou de copyleft fraco, todas
compatíveis com a AGPL-3.0.

| Pacote | Versão | Licença | Verificação | Requerido por |
|---|---|---|---|---|
| Jinja2 | 3.1.6 | BSD-3-Clause | texto | Flask |
| MarkupSafe | 3.0.3 | BSD-3-Clause | texto | Flask/Werkzeug |
| itsdangerous | 2.2.0 | BSD-3-Clause | texto | Flask |
| click | 8.5.0 | BSD-3-Clause | texto | Flask |
| blinker | 1.9.0 | MIT | texto | Flask |
| matplotlib | 3.11.2 | licença matplotlib (baseada na PSF) | texto | ultralytics |
| contourpy | 1.4.0 | BSD-3-Clause | texto | matplotlib |
| cycler | 0.12.1 | BSD-3-Clause | texto | matplotlib |
| fonttools | 4.67.0 | MIT | texto | matplotlib |
| kiwisolver | 1.5.1 | BSD-3-Clause | texto | matplotlib |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | texto | matplotlib |
| pyparsing | 3.3.3 | MIT | texto | matplotlib |
| python-dateutil | 3.0.0 | Apache-2.0 e BSD-3-Clause (dupla) | texto | matplotlib |
| six | 1.17.0 | MIT | texto | python-dateutil |
| tzdata | 2026.5 | Apache-2.0 | texto | python-dateutil |
| pillow | 12.3.0 | MIT-CMU (HPND) | texto | ultralytics |
| polars | 2.0.0 | MIT | texto | ultralytics |
| polars-runtime-32 | 2.0.0 | MIT | texto | polars |
| psutil | 7.2.2 | BSD-3-Clause | texto | ultralytics |
| PyYAML | 6.0.3 | MIT | texto | ultralytics |
| requests | 2.34.2 | Apache-2.0 | texto | ultralytics |
| urllib3 | 2.8.0 | MIT | texto | requests |
| idna | 3.20 | BSD-3-Clause | texto | requests |
| charset-normalizer | 3.5.2 | MIT | texto | requests |
| certifi | 2026.10.23 | MPL-2.0 | **metadados** | requests |
| httpx | 0.28.1 | BSD-3-Clause | texto | ultralytics-platform |
| httpcore | 1.0.9 | BSD-3-Clause | texto | httpx |
| h11 | 0.16.0 | MIT | texto | httpcore |
| anyio | 4.15.1 | MIT | texto | httpx |
| nvidia-ml-py | 13.615.71 | BSD | **metadados** (pacote sem arquivo de licença) | ultralytics |
| filelock | 3.32.3 | MIT | texto | torch |
| fsspec | 2026.7.0 | BSD-3-Clause | texto | torch |
| networkx | 3.6.1 | BSD-3-Clause | texto | torch |
| sympy | 1.14.0 | BSD-3-Clause | texto | torch |
| mpmath | 1.3.0 | BSD-3-Clause | texto | sympy |
| setuptools | 78.1.0 | MIT | texto | torch |
| typing_extensions | 4.16.0 | PSF-2.0 | texto | torch |

Dependências condicionais do PyTorch para Linux com GPU (`nvidia-*-cu13`, `cuda-*`, `triton`) não são
instaladas na configuração CPU no Windows e **não foram verificadas**. Quem instalar em Linux com CUDA
deve revisar as licenças desses pacotes (algumas bibliotecas NVIDIA têm termos proprietários de
redistribuição).

## 4. Modelos (pesos) — não incluídos

| Modelo | Uso no Overflow | Licença | Verificação | Fonte oficial |
|---|---|---|---|---|
| `yolo26n.pt` (YOLO26 nano, pré-treinado no COCO) | detecção de pessoas (`camera.py`) | AGPL-3.0 ou Licença Enterprise (termos da Ultralytics para seus modelos) | página oficial | https://github.com/ultralytics/assets/releases · https://docs.ultralytics.com |
| `face_detection_yunet_2023mar.onnx` (YuNet) | cadastro de rosto | MIT | página oficial | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |
| `face_recognition_sface_2021dec.onnx` (SFace) | cadastro de rosto | Apache-2.0 | página oficial | https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface |

**Não verificado:** os termos dos **conjuntos de dados** usados para treinar esses modelos. O YOLO26
pré-treinado usa o COCO, cujos termos (anotações e imagens de origem) não foram conferidos nesta
auditoria; as páginas do YuNet e do SFace não identificam os dados de treino. Isso não muda a licença dos pesos declarada pelos autores,
mas deve ser revisado antes de redistribuir os pesos ou usá-los comercialmente.

**Citação pedida pelos autores do YuNet:** Wu, W.; Peng, H.; Yu, S. "YuNet: A Tiny Millisecond-level
Face Detector". *Machine Intelligence Research*, 20(5), 656–665, 2023.

## 5. Componentes carregados pelo navegador

| Componente | Versão | Licença | Verificação | Fonte oficial |
|---|---|---|---|---|
| Chart.js | **não fixada** (`https://cdn.jsdelivr.net/npm/chart.js`, versão mais recente no momento do acesso) | MIT ("Copyright (c) 2014-2024 Chart.js Contributors") | página oficial | https://github.com/chartjs/Chart.js |

O arquivo não é distribuído pelo repositório; o navegador o baixa do CDN jsDelivr. Pendência
recomendada: fixar a versão e usar Subresource Integrity (SRI).

## 6. Biblioteca padrão e ferramentas

O Overflow também usa apenas a biblioteca padrão do Python (licença PSF). Nenhum código de terceiros foi
copiado para este repositório: a busca por cabeçalhos de copyright, licenças e trechos atribuídos a
terceiros no código, nos scripts e nos templates não encontrou ocorrências.
