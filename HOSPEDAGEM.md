# Estratégia de hospedagem de baixo custo

Planejamento apenas: nada foi contratado, criado ou implantado. Condições de planos gratuitos mudam
com frequência — confira limites, região dos dados e termos de cada serviço antes de usar.

## Restrição que define a arquitetura

A visão computacional (webcam + YOLO em CPU) **precisa rodar no local**, no PC ligado à câmera.
Nenhuma hospedagem gratuita oferece webcam nem CPU suficiente para inferência contínua. O que pode ir
para a nuvem é só o **painel** (Flask, leve: Flask + Werkzeug + NumPy, ver `requirements-web.txt`) e,
mais tarde, o **banco**.

Hoje câmera e painel compartilham um arquivo SQLite. SQLite não pode ser compartilhado pela rede entre
o PC da câmera e um servidor na nuvem; por isso qualquer painel remoto exige mudar o armazenamento
(etapa 3) ou deixar o painel no próprio PC (etapa 1).

## Etapa 1 — testes com custo zero, dados no PC (recomendada agora)

```
[webcam] -> camera.py -> banco.db (local) <- painel (waitress, 127.0.0.1) <- túnel HTTPS <- navegador
```

- Painel e câmera no mesmo PC; o banco nunca sai da máquina.
- Acesso externo por um **túnel HTTPS de saída** (ex.: Cloudflare Tunnel ou Tailscale Funnel/Serve):
  não abre portas no roteador e entrega HTTPS com certificado válido. Com Tailscale sem Funnel, só
  aparelhos da sua rede privada acessam — a opção mais segura para testes.
- Servidor WSGI no Windows: `waitress` (ainda **não** está nos requirements nem foi testado):
  `waitress-serve --host 127.0.0.1 --port 8000 wsgi:app`.
- Variáveis: `OVERFLOW_AMBIENTE=producao`, `OVERFLOW_SECRET_KEY` (≥ 32 caracteres; sem ela o painel
  não inicia), `OVERFLOW_PROXIES_CONFIAVEIS=1` (há exatamente um proxy: o túnel). Em produção o cookie
  de sessão é sempre `Secure`, `HttpOnly` e `SameSite=Lax`.
- Limitação: o painel só fica no ar com o PC ligado.

## Etapa 2 — demonstração na nuvem com dados fictícios

Para mostrar o painel sem expor dados reais: hospedar só o painel com um banco **fictício**.
- Serviços com disco persistente no plano gratuito (ex.: PythonAnywhere) aceitam SQLite.
- Serviços com disco efêmero e hibernação (ex.: Render free) perdem o SQLite ao reiniciar; só servem
  com banco externo (etapa 3).
- Iniciar com `gunicorn --workers 1 --bind 127.0.0.1:8000 wsgi:app` (Linux; gunicorn não está nos
  requirements nem foi testado). Use **1 worker**: o limite de tentativas de login fica na memória do
  processo e não é compartilhado entre workers. Defina `OVERFLOW_PROXIES_CONFIAVEIS` com o número de
  proxies do provedor; ao carregar, `wsgi.py` ajusta o esquema do banco (só acrescenta tabelas/colunas).

## Etapa 3 — dados centralizados com PostgreSQL

```
PC da câmera --(HTTPS + token do dispositivo)--> API de ingestão --> PostgreSQL gerenciado <-- painel
```

- PostgreSQL gerenciado com plano gratuito (ex.: Neon, Supabase) para testes. Verifique região
  (preferir Brasil/América do Sul quando houver dados reais), limites de armazenamento, retenção de
  backups e se o banco hiberna.
- **A câmera não deve ter a senha do banco.** Recomenda-se uma rota de ingestão no painel
  (`POST /api/movimentacoes`) autenticada por token por dispositivo, que já define o `id_empresa` do
  lado do servidor. Se a câmera precisar gravar direto no banco, use um papel (role) com permissão só
  de `INSERT/UPDATE` em `movimentacao` e `sessao_camera`, TLS obrigatório (`sslmode=verify-full`).
- Fila local: com a internet fora, a câmera precisa guardar os eventos (ex.: no SQLite local) e
  reenviar depois; isso ainda não existe.

### O que muda no código para PostgreSQL

O acesso ao banco usa `sqlite3` diretamente, com SQL específico do SQLite:

| SQLite (hoje) | PostgreSQL |
|---|---|
| placeholders `?` | `%s` (psycopg) ou parâmetros nomeados (SQLAlchemy Core) |
| `PRAGMA table_info`, `sqlite_master`, `PRAGMA journal_mode` | `information_schema`; remover pragmas |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` |
| `cursor.lastrowid` | `INSERT ... RETURNING id` |
| `printf('%04d', x)` | `lpad(x::text, 4, '0')` |
| `CREATE TABLE ... AS SELECT * ... WHERE 0` | DDL explícita |
| `ALTER TABLE ADD COLUMN` em tempo de execução | migrações versionadas (ex.: Alembic) |
| datas/horas como `TEXT` | `date`, `time`/`timestamptz` |
| embeddings em `TEXT`/`BLOB` | `bytea` ou `real[]` (ou `vector` com pgvector) |

Sugestão de ordem: (1) concentrar todo SQL em `overflow/db/` (o painel hoje tem SQL embutido nas rotas);
(2) introduzir SQLAlchemy Core com `DATABASE_URL` vindo do ambiente, mantendo SQLite como padrão local;
(3) migrações versionadas; (4) script que copia dados SQLite → PostgreSQL a partir de uma **cópia** do
banco; (5) rodar a mesma suíte de testes nos dois bancos.

## Segredos

- Somente em variáveis de ambiente / painel de segredos do provedor. Nunca no repositório.
- `.env.example` documenta os nomes, sem valores. Gere chaves com `secrets.token_hex(32)`.
- Trocar `OVERFLOW_SECRET_KEY` encerra todas as sessões abertas (use após incidentes).
- Credenciais de banco: um usuário por aplicação, sem superusuário, senha longa e única.

## HTTPS

- Fornecido pelo túnel ou pelo provedor; o Flask não deve servir HTTPS diretamente.
- Com HTTPS: `OVERFLOW_AMBIENTE=producao` (cookie sempre `Secure`) e `OVERFLOW_PROXIES_CONFIAVEIS`
  igual ao número exato de proxies na frente do painel. Com `0` (padrão) os cabeçalhos
  `X-Forwarded-*` são ignorados; um valor maior que o real deixaria clientes forjarem o IP.
  Ativar HSTS no proxy quando o domínio for definitivo (o painel não envia HSTS).

## Backups

- SQLite: cópia consistente com a API de backup do SQLite (`sqlite3.Connection.backup`, já usada em
  `scripts/redefinir_senha.py`) — nunca copiar o `.db` com o painel/câmera abertos sem incluir o WAL.
  Guardar fora do PC, **criptografado**, com retenção definida (ex.: 7 diários + 4 semanais).
- PostgreSQL: não confiar só no backup do plano gratuito; agendar `pg_dump` criptografado.
- Testar a restauração periodicamente numa pasta/banco separado.

## Isolamento dos dados dos clientes

- Hoje: um banco para todos, com `id_empresa` em `movimentacao`, `pessoa` e `local`, filtrado em cada
  rota a partir da sessão. Os resumos mensais agora são por empresa (`resumo_mensal_empresa`).
  A suíte em `tests/` cobre o isolamento no dashboard, pessoas, edição de pessoas, resumos,
  arquivamento e na associação da câmera e do cadastro à empresa (ver README).
- Lacunas: `visitante`, `visitante_face`, `reconhecimento`, `sessao_camera` e `identificacao` não têm
  `id_empresa`; a pessoa padrão "Desconhecido" (id 1) é compartilhada; `scripts/consultar.py` lista
  todas as empresas (uso administrativo local).
- No PostgreSQL: `id_empresa NOT NULL` com chave estrangeira em todas as tabelas de dados, e
  Row-Level Security (`CREATE POLICY ... USING (id_empresa = current_setting('app.empresa')::int)`)
  como segunda barreira além do filtro da aplicação.

## LGPD (resumo, não é parecer jurídico)

- Embeddings faciais são **dados biométricos** (dado pessoal sensível). Exigem base legal adequada,
  aviso visível no local, finalidade definida, retenção mínima e controle de acesso.
- Contrato de operador de dados com cada provedor; verificar transferência internacional se o
  servidor ficar fora do Brasil.
- Mantenha o reconhecimento facial desativado (como está hoje em `camera.py`) até isso estar resolvido.
