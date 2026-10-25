import hmac
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from collections import deque
from datetime import date, datetime

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from overflow import config
from overflow.db import resumo
from overflow.db.repositorio import Repositorio

BANCO = str(config.BANCO)
app = Flask(__name__, root_path=str(config.BASE_DIR))

# CHAVE SECRETA: assina o cookie de sessão (login) do Flask.
# Vem de OVERFLOW_SECRET_KEY. Em produção é obrigatória e precisa ter pelo menos
# SECRET_KEY_MINIMA caracteres; em desenvolvimento, sem ela, usa uma chave aleatória
# válida só nesta execução. As mensagens nunca exibem a chave.
SECRET_KEY_MINIMA = 32


def _carregar_secret_key():
    chave = os.environ.get("OVERFLOW_SECRET_KEY", "").strip()
    if config.PRODUCAO:
        if not chave:
            raise SystemExit("Configuracao invalida: OVERFLOW_SECRET_KEY e obrigatoria com OVERFLOW_AMBIENTE=producao.")
        if len(chave) < SECRET_KEY_MINIMA:
            raise SystemExit(f"Configuracao invalida: OVERFLOW_SECRET_KEY precisa ter pelo menos {SECRET_KEY_MINIMA} "
                             'caracteres. Gere uma com: python -c "import secrets; print(secrets.token_hex(32))"')
        return chave
    if chave:
        return chave
    print(
        "AVISO: OVERFLOW_SECRET_KEY não configurada. Usando uma chave aleatória temporária; "
        "os logins serão perdidos ao reiniciar o painel. "
        'No PowerShell: $env:OVERFLOW_SECRET_KEY = "<sua chave>" (vale só para este terminal).',
        file=sys.stderr,
    )
    return secrets.token_hex(32)


app.secret_key = _carregar_secret_key()

# Cookie de sessão: HttpOnly e SameSite=Lax sempre. Secure (só HTTPS) sempre em produção;
# em desenvolvimento, só com OVERFLOW_COOKIE_SECURE=1, pois em HTTP o navegador não devolveria o cookie.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.PRODUCAO or os.environ.get("OVERFLOW_COOKIE_SECURE", "").strip() == "1",
)

# Atrás de proxies reversos (HTTPS, túnel), o IP real e o esquema chegam em X-Forwarded-*.
# Só são lidos com OVERFLOW_PROXIES_CONFIAVEIS=<n>, o número exato de proxies na frente do painel;
# com 0 (padrão) esses cabeçalhos são ignorados, pois qualquer cliente pode forjá-los (e burlar,
# por exemplo, o limite de tentativas de login, que usa o IP).
if config.PROXIES_CONFIAVEIS:
    _n = config.PROXIES_CONFIAVEIS
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_n, x_proto=_n, x_host=_n)

# SQL que identifica cada pessoa por empresa
CHAVE_PESSOA = "CASE WHEN m.id_visitante IS NOT NULL THEN 'v' || m.id_visitante ELSE 'p' || m.id_pessoa END"
NOME_PESSOA = (
    "CASE WHEN m.id_visitante IS NOT NULL THEN 'Visitante ' || printf('%04d', m.id_visitante) "
    "ELSE COALESCE(p.nome, 'Pessoa ' || m.id_pessoa) END"
)

_ultima_virada = 0.0


def conectar():
    conexao = sqlite3.connect(BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row
    return conexao


def preparar_banco():
    """Garante colunas/tabelas novas (idempotente)."""
    Repositorio(BANCO).fechar_conexao()
    con = sqlite3.connect(BANCO, timeout=10)
    try:
        resumo.garantir_tabelas(con)
    finally:
        con.close()


def virar_mes_se_preciso(forcar=False):
    """Roda a virada de mes no maximo 1x por minuto (e a cada abertura do painel)."""
    global _ultima_virada
    if not forcar and time.monotonic() - _ultima_virada < 60:
        return []
    _ultima_virada = time.monotonic()
    con = sqlite3.connect(BANCO, timeout=10)
    try:
        return resumo.virar_mes(con)
    finally:
        con.close()


# ------------------------------------------------------------------ AUTENTICAÇÃO E SEGURANÇA
def _csrf_token():
    """Token CSRF da sessão (criado na primeira vez em que um formulário é exibido)."""
    token = session.get("_csrf")
    if not token:
        token = session["_csrf"] = secrets.token_urlsafe(32)
    return token


app.jinja_env.globals["csrf_token"] = _csrf_token


@app.before_request
def verificar_csrf():
    """Recusa qualquer POST sem o token CSRF da sessão, antes de executar a rota."""
    if request.method != "POST":
        return
    enviado = request.form.get("csrf_token", "")
    esperado = session.get("_csrf", "")
    if esperado and hmac.compare_digest(enviado.encode("utf-8"), esperado.encode("utf-8")):
        return
    if request.endpoint == "login":
        return render_template("login.html", erro="A página expirou. Tente entrar novamente."), 400
    abort(400)


# Limite de tentativas de login, em memória (zera ao reiniciar o painel).
# A chave é IP + e-mail: quem erra a senha bloqueia só a si mesmo, sem conseguir
# bloquear a conta de outra pessoa a partir de outra máquina.
LOGIN_MAX_FALHAS = 5
LOGIN_JANELA_SEGUNDOS = 15 * 60
LOGIN_MAX_CHAVES = 10000
_falhas_login = {}
_falhas_lock = threading.Lock()
_relogio = time.monotonic


def _chave_login(email):
    return (request.remote_addr or "", (email or "").strip().lower())


def _login_bloqueado(chave):
    agora = _relogio()
    with _falhas_lock:
        fila = _falhas_login.get(chave)
        while fila and agora - fila[0] > LOGIN_JANELA_SEGUNDOS:
            fila.popleft()
        if fila is not None and not fila:
            del _falhas_login[chave]
        return bool(fila) and len(fila) >= LOGIN_MAX_FALHAS


def _registrar_falha_login(chave):
    agora = _relogio()
    with _falhas_lock:
        if chave not in _falhas_login and len(_falhas_login) >= LOGIN_MAX_CHAVES:
            vencidas = [k for k, f in _falhas_login.items() if not f or agora - f[-1] > LOGIN_JANELA_SEGUNDOS]
            for k in vencidas:
                del _falhas_login[k]
            if len(_falhas_login) >= LOGIN_MAX_CHAVES:
                del _falhas_login[next(iter(_falhas_login))]
        _falhas_login.setdefault(chave, deque(maxlen=LOGIN_MAX_FALHAS)).append(agora)


def _limpar_falhas_login(chave):
    with _falhas_lock:
        _falhas_login.pop(chave, None)


@app.after_request
def cabecalhos_de_seguranca(resposta):
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    return resposta


@app.before_request
def verificar_autenticacao():
    """Bloqueia o acesso a qualquer página se o usuário não estiver logado."""
    # Libera a página de login e arquivos estáticos (CSS, imagens)
    if request.endpoint in ("login", "static") or request.endpoint is None:
        return

    # Se não houver usuário na sessão, redireciona para a tela de login
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    # Para as páginas do painel, executa a verificação do mês
    if request.endpoint in ("dashboard", "resumos", "resumo_mes"):
        virar_mes_se_preciso()


# Formatos gerados por werkzeug.security.generate_password_hash (scrypt e pbkdf2).
_FORMATO_HASH = re.compile(
    r"(?:scrypt:\d+:\d+:\d+|pbkdf2:sha(?:256|512)(?::\d+)?)\$[A-Za-z0-9]+\$(?:[0-9a-f]{64}|[0-9a-f]{128})"
)


def _senha_em_hash(armazenada):
    return isinstance(armazenada, str) and _FORMATO_HASH.fullmatch(armazenada) is not None


def _senha_confere(armazenada, fornecida):
    if not isinstance(armazenada, str) or not isinstance(fornecida, str):
        return False
    if _senha_em_hash(armazenada):
        try:
            return check_password_hash(armazenada, fornecida)
        except (ValueError, TypeError):
            return False
    # Conta antiga com senha em texto puro (transição): comparação em tempo constante.
    return hmac.compare_digest(armazenada.encode("utf-8"), fornecida.encode("utf-8"))


def _converter_senha_para_hash(conexao, usuario, senha):
    """Após um login válido com senha antiga em texto puro, grava o hash no lugar dela."""
    try:
        conexao.execute(
            "UPDATE usuario SET senha = ? WHERE id_usuario = ? AND senha = ?",
            (generate_password_hash(senha), usuario["id_usuario"], usuario["senha"]),
        )
        conexao.commit()
    except sqlite3.Error:
        conexao.rollback()
        app.logger.warning("Não foi possível converter a senha para hash; nova tentativa no próximo login.")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        chave = _chave_login(email)
        if _login_bloqueado(chave):
            return render_template(
                "login.html", erro="Muitas tentativas de login. Aguarde alguns minutos e tente novamente."
            ), 429

        conexao = conectar()
        try:
            usuario = conexao.execute(
                """
                SELECT id_usuario, id_empresa, senha
                FROM usuario WHERE email = ?
            """,
                (email,),
            ).fetchone()
            valida = usuario is not None and _senha_confere(usuario["senha"], senha)
            if valida and not _senha_em_hash(usuario["senha"]):
                _converter_senha_para_hash(conexao, usuario, senha)
        finally:
            conexao.close()

        if valida:
            _limpar_falhas_login(chave)
            # Sessão nova a cada login (o token CSRF é recriado na próxima página exibida)
            session.clear()
            # Salva na sessão o ID do usuário e a qual EMPRESA ele pertence
            session["id_usuario"] = usuario["id_usuario"]
            session["id_empresa"] = usuario["id_empresa"]
            return redirect(url_for("dashboard"))

        _registrar_falha_login(chave)
        return render_template("login.html", erro="E-mail ou senha inválidos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------ DASHBOARD
@app.route("/")
def dashboard():
    filtro_data = request.args.get("data")
    filtro_mes = request.args.get("mes")

    # Pega o id da empresa a partir do usuário logado
    id_empresa = session["id_empresa"]

    conexao = conectar()
    cursor = conexao.cursor()

    # FILTRO OBRIGATÓRIO: Garante que apenas os dados desta empresa sejam consultados
    where_clauses = ["m.id_empresa = ?"]
    params = [id_empresa]

    if filtro_data:
        where_clauses.append("m.data_entrada = ?")
        params.append(filtro_data)
    if filtro_mes:
        where_clauses.append("substr(m.data_entrada, 1, 7) = ?")
        params.append(filtro_mes)

    where_sql = "WHERE " + " AND ".join(where_clauses)
    e = "AND"

    total_entradas = cursor.execute(
        f"SELECT COUNT(*) FROM movimentacao m {where_sql}", params
    ).fetchone()[0]

    total_saidas = cursor.execute(
        f"SELECT COUNT(*) FROM movimentacao m {where_sql} {e} data_saida IS NOT NULL",
        params,
    ).fetchone()[0]

    pessoas_dentro = cursor.execute(
        "SELECT COUNT(*) FROM movimentacao WHERE data_saida IS NULL AND data_entrada = ? AND id_empresa = ?",
        (date.today().strftime("%Y-%m-%d"), id_empresa),
    ).fetchone()[0]

    pessoas_diferentes = cursor.execute(
        f"SELECT COUNT(DISTINCT {CHAVE_PESSOA}) FROM movimentacao m {where_sql}",
        params,
    ).fetchone()[0]

    media_tempo = (
        cursor.execute(
            f"SELECT AVG(tempo_dentro) FROM movimentacao m {where_sql} {e} tempo_dentro IS NOT NULL",
            params,
        ).fetchone()[0]
        or 0
    )

    tipos = {"funcionario": 0, "visitante": 0, "desconhecido": 0}
    for linha in cursor.execute(
        f"""
        SELECT CASE WHEN m.id_visitante IS NOT NULL THEN 'desconhecido' ELSE p.tipo_pessoa END AS tipo,
               COUNT(DISTINCT {CHAVE_PESSOA}) AS total
        FROM movimentacao m
        LEFT JOIN pessoa p ON m.id_pessoa = p.id_pessoa
        {where_sql}
        GROUP BY tipo""",
        params,
    ).fetchall():
        if linha["tipo"] in tipos:
            tipos[linha["tipo"]] = linha["total"]

    por_hora = cursor.execute(
        f"""
        SELECT substr(hora_entrada, 1, 2) AS hora, COUNT(*) AS total
        FROM movimentacao m {where_sql} GROUP BY hora ORDER BY hora""",
        params,
    ).fetchall()

    por_dia = cursor.execute(
        f"""
        SELECT data_entrada AS data, COUNT(*) AS total
        FROM movimentacao m {where_sql} GROUP BY data_entrada ORDER BY data_entrada""",
        params,
    ).fetchall()

    por_mes = cursor.execute(
        f"""
        SELECT substr(data_entrada, 1, 7) AS mes, COUNT(*) AS total
        FROM movimentacao m {where_sql} GROUP BY mes ORDER BY mes""",
        params,
    ).fetchall()

    movimentacoes = cursor.execute(
        f"""
        SELECT m.id_movimentacao,
               {NOME_PESSOA} AS pessoa,
               CASE WHEN m.id_visitante IS NOT NULL THEN 'desconhecido' ELSE p.tipo_pessoa END AS tipo_pessoa,
               l.nome AS local,
               m.data_entrada, m.hora_entrada, m.data_saida, m.hora_saida, m.tempo_dentro, m.confianca
        FROM movimentacao m
        LEFT JOIN pessoa p ON m.id_pessoa = p.id_pessoa
        LEFT JOIN local l ON m.id_local = l.id_local
        {where_sql}
        ORDER BY m.id_movimentacao DESC
        LIMIT 300""",
        params,
    ).fetchall()

    conexao.close()

    return render_template(
        "dashboard.html",
        total_entradas=total_entradas,
        total_saidas=total_saidas,
        pessoas_dentro=pessoas_dentro,
        pessoas_diferentes=pessoas_diferentes,
        media_tempo=round(media_tempo),
        tipos=tipos,
        por_hora=por_hora,
        por_dia=por_dia,
        por_mes=por_mes,
        movimentacoes=movimentacoes,
        limitado=total_entradas > 300,
        filtro_data=filtro_data or "",
        filtro_mes=filtro_mes or "",
        aviso=request.args.get("aviso", ""),
        hoje=date.today().strftime("%Y-%m-%d"),
    )


# ------------------------------------------------------------------ RESUMOS
@app.route("/resumos")
def resumos():
    id_empresa = session["id_empresa"]
    con = sqlite3.connect(BANCO, timeout=10)
    try:
        lista = resumo.listar_resumos(con, id_empresa)
    finally:
        con.close()
    return render_template(
        "resumos.html", resumos=lista, mes_atual=date.today().strftime("%Y-%m")
    )


@app.route("/resumo/<mes>")
def resumo_mes(mes):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        abort(404)
    id_empresa = session["id_empresa"]
    con = sqlite3.connect(BANCO, timeout=10)
    try:
        dados = resumo.carregar_resumo(con, mes, id_empresa)
        parcial = False
        if dados is None and mes == date.today().strftime("%Y-%m"):
            dados, parcial = resumo.gerar_resumo(con, mes, id_empresa), True
    finally:
        con.close()
    return render_template("resumo.html", r=dados, mes=mes, parcial=parcial)


# ------------------------------------------------------------------ LIMPEZA / ARQUIVAR
@app.route("/arquivar", methods=["POST"])
def arquivar():
    ate = request.form.get("ate", "")
    if request.form.get("confirmacao", "").strip().upper() != "ARQUIVAR":
        return redirect(
            url_for(
                "dashboard",
                aviso="Nada foi feito: digite ARQUIVAR para confirmar.",
            )
        )
    try:
        datetime.strptime(ate, "%Y-%m-%d")
    except ValueError:
        return redirect(url_for("dashboard", aviso="Data invalida."))

    id_empresa = session["id_empresa"]
    con = sqlite3.connect(BANCO, timeout=10)
    try:
        n = resumo.arquivar(
            con,
            "data_entrada <= ? AND id_empresa = ?",
            (ate, id_empresa),
            f"limpeza manual ate {ate}",
        )
    finally:
        con.close()
    return redirect(
        url_for(
            "dashboard",
            aviso=f"{n} registro(s) arquivado(s) (ficam guardados no banco).",
        )
    )


# ------------------------------------------------------------------- PESSOAS
@app.route("/pessoas")
def pessoas():
    id_empresa = session["id_empresa"]
    conexao = conectar()
    lista = conexao.execute(
        """
        SELECT id_pessoa, nome, codigo_pessoa, tipo_pessoa
        FROM pessoa
        WHERE id_empresa = ?
        ORDER BY id_pessoa""",
        (id_empresa,),
    ).fetchall()
    conexao.close()
    return render_template("pessoas.html", pessoas=lista)


@app.route("/pessoas/atualizar", methods=["POST"])
def atualizar_pessoa():
    id_pessoa = request.form["id_pessoa"]
    tipo_pessoa = request.form["tipo_pessoa"]
    id_empresa = session["id_empresa"]

    if tipo_pessoa not in ("desconhecido", "funcionario", "visitante"):
        abort(400)

    conexao = conectar()
    conexao.execute(
        "UPDATE pessoa SET tipo_pessoa = ? WHERE id_pessoa = ? AND id_empresa = ?",
        (tipo_pessoa, id_pessoa, id_empresa),
    )
    conexao.commit()
    conexao.close()
    return redirect("/pessoas")


def main():
    preparar_banco()
    virar_mes_se_preciso(forcar=True)
    # Servidor de desenvolvimento do Flask: para uso local e testes.
    # Em hospedagem, use um servidor WSGI com wsgi:app (veja HOSPEDAGEM.md).
    app.run(host=config.WEB_HOST, port=config.WEB_PORTA, debug=False)


if __name__ == "__main__":
    main()