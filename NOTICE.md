# Avisos — Overflow

## Copyright e licença

Overflow — contagem de pessoas com visão computacional e painel web.
Copyright (C) 2026 Samuel Fernando.

Esse aviso de copyright abrange **apenas o código e a documentação originais do Overflow** contidos
neste repositório. O titular acima não detém direitos sobre as bibliotecas, os modelos, os conjuntos
de dados nem os demais componentes de terceiros citados neste arquivo e em
`THIRD_PARTY_LICENSES.md`, que pertencem aos seus respectivos autores e seguem as próprias licenças.

Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob os termos da
GNU Affero General Public License, versão 3, publicada pela Free Software Foundation
(identificador SPDX: `AGPL-3.0-only`).

Este programa é distribuído na esperança de que seja útil, mas SEM NENHUMA GARANTIA; sem mesmo a
garantia implícita de COMERCIABILIDADE ou ADEQUAÇÃO A UM PROPÓSITO ESPECÍFICO. Veja a GNU Affero
General Public License para mais detalhes. O texto completo e oficial (em inglês, que é a versão com
valor legal) está no arquivo `LICENSE`, idêntico ao publicado em
https://www.gnu.org/licenses/agpl-3.0.txt.

A licença do Overflow cobre **somente o código e a documentação deste repositório**. Componentes de
terceiros mantêm as próprias licenças (inventário em `THIRD_PARTY_LICENSES.md`).

## Por que AGPL-3.0: o uso do Ultralytics YOLO

O módulo `overflow/visao/camera.py` importa a biblioteca `ultralytics` (AGPL-3.0) para detecção
(YOLO26n) e rastreamento (implementação ByteTrack da Ultralytics). A Ultralytics oferece o software sob
AGPL-3.0 ou sob uma Licença Enterprise paga (https://www.ultralytics.com/pt/license). O Overflow segue
o caminho AGPL-3.0: **todo o projeto é publicado como código aberto sob a mesma licença.** Na prática:

1. **Distribuir o Overflow** (código, cópias, versões modificadas) exige manter a AGPL-3.0, este aviso
   e o código-fonte correspondente completo, incluindo scripts e arquivos de configuração.
2. **Oferecer o Overflow pela rede** (por exemplo, o painel hospedado): se a versão em execução tiver
   sido **modificada**, os usuários que interagem com ela devem poder obter o código-fonte dessa versão
   (AGPL-3.0, seção 13). Manter o repositório público atualizado com o código em produção atende a isso.
3. **Modelos:** segundo a Ultralytics, modelos treinados ou ajustados com o seu código também ficam
   sob AGPL-3.0 por padrão. Se um modelo próprio (por exemplo, de uniformes) for treinado no futuro,
   os pesos, os scripts e a configuração de treino seguem a mesma regra — e o **conjunto de dados
   continua sujeito aos direitos de quem o produziu**: só pode ser publicado com autorização.
4. **Uso comercial:** a AGPL-3.0 não proíbe uso comercial, desde que as obrigações acima sejam
   cumpridas. A Ultralytics declara que usar o YOLO em produto ou serviço comercial **sem** abrir o
   projeto exige a Licença Enterprise. Para uso comercial fechado, essa licença é obrigatória.
5. **Painel sem câmera:** `overflow/web` e `requirements-web.txt` não importam o `ultralytics`, mas o
   repositório é distribuído como uma obra única sob AGPL-3.0.

Este resumo não substitui o texto da licença nem aconselhamento jurídico.

## Componentes NÃO incluídos neste repositório

| Item | Por quê | Como obter |
|---|---|---|
| Bibliotecas Python | instaladas pelo `pip` | `requirements.txt` / `requirements-web.txt` (PyPI e índice CPU oficial do PyTorch) |
| `yolo26n.pt` | pesos de terceiros (Ultralytics, AGPL-3.0) | releases oficiais em https://github.com/ultralytics/assets/releases ou download automático do pacote `ultralytics` |
| `face_detection_yunet_2023mar.onnx` | pesos de terceiros (MIT) | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |
| `face_recognition_sface_2021dec.onnx` | pesos de terceiros (Apache-2.0) | https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface |
| Chart.js | carregado do CDN jsDelivr pelo navegador (MIT) | https://github.com/chartjs/Chart.js |
| Bancos de dados, embeddings faciais, fotos, vídeos | **dados pessoais** (inclusive biométricos) | não se distribuem |
| Imagens de uniformes (dataset local) | origem e direitos de uso **não comprovados** | não se distribuem; ver `README.md` |
| Modelo personalizado de uniformes | **não existe** até o momento | — |

## Atribuições

- **Ultralytics YOLO** — Copyright Ultralytics, AGPL-3.0. https://github.com/ultralytics/ultralytics
- **ByteTrack** — algoritmo de Zhang et al.; a implementação usada é a incluída no pacote
  `ultralytics` (AGPL-3.0). O `bytetrack_custom.yaml` usa as chaves de configuração desse rastreador.
- **YuNet** — Wu, W.; Peng, H.; Yu, S. "YuNet: A Tiny Millisecond-level Face Detector". *Machine
  Intelligence Research*, 20(5), 656–665, 2023. Modelo do OpenCV Zoo, MIT.
- **SFace** — modelo do OpenCV Zoo, Apache-2.0; referência: https://github.com/zhongyy/SFace
- **OpenCV** — Apache-2.0; o pacote `opencv-python` embute FFmpeg (LGPL-2.1) e, em Linux/macOS, Qt
  (LGPL-3.0). Distribuições **binárias** do Overflow precisam incluir esses avisos.
- **Chart.js** — Copyright (c) 2014-2024 Chart.js Contributors, MIT.

"Ultralytics", "YOLO", "OpenCV", "PyTorch" e demais nomes são marcas de seus respectivos titulares; o
Overflow não é afiliado a eles nem endossado por eles.

## Privacidade

- O pacote `ultralytics` envia por padrão métricas de uso anônimas e, em certas condições, relatórios de
  erro (não envia imagens, segundo https://docs.ultralytics.com/help/privacy/). Em instalações com
  câmera, recomenda-se desligar: `from ultralytics import settings; settings.update({"sync": False})`.
- Embeddings faciais são dados biométricos (dado pessoal sensível na LGPD) e nunca devem ser publicados.
