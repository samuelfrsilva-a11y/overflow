"""Redefine a senha de uma conta do painel, gravando somente o hash.

Uso, a partir da raiz do projeto, com o painel e a câmera FECHADOS:
    .venv\\Scripts\\python.exe scripts\\redefinir_senha.py --email <e-mail> --verificar
    .venv\\Scripts\\python.exe scripts\\redefinir_senha.py --email <e-mail> --backup <pasta-nova>

A senha nova é pedida duas vezes, sem eco na tela. Nenhuma senha ou hash é exibido.
Se qualquer verificação falhar antes da gravação, nada é alterado.

Códigos de saída:
    0   sucesso
    1   erro previsto; nada foi alterado
    2   erro do banco ou de uso; nada foi alterado
    3   a senha FOI alterada, mas a verificação final de integridade falhou (ver mensagem)
    130 cancelado pelo usuário; nada foi alterado

Recuperação a partir do backup (código 3 ou qualquer dúvida depois da gravação):
    1. Feche o painel, a câmera e qualquer script que use o banco.
    2. Crie uma pasta nova com acesso restrito e MOVA para ela banco.db, banco.db-wal, banco.db-shm e
       banco.db-journal (os que existirem). Nunca copie o backup sobre banco.db deixando -wal/-shm antigos
       no lugar: o SQLite poderia combiná-los com o arquivo restaurado.
    3. Confira o SHA-256 do backup e COPIE-o (não mova) para banco.db.
    4. Rode --verificar antes de reabrir o painel.
    A mensagem do código 3 traz esses comandos já com os caminhos certos.

Limitação do --verificar: a comparação do hash do banco e do tamanho do -wal antes e depois da leitura
só detecta alterações que ficaram gravadas em disco durante a leitura. Ela não é garantia: não percebe
gravações ainda não descarregadas no disco, alterações desfeitas antes da segunda comparação nem
gravações que comecem logo depois. A condição exigida continua sendo o painel e a câmera FECHADOS.
"""
import argparse
import getpass
import hashlib
import hmac
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.security import check_password_hash, generate_password_hash

from overflow import config

SENHA_MINIMA = 12

# Mesmo formato reconhecido pelo login em overflow/web/dashboard.py (scrypt e pbkdf2 do werkzeug).
_FORMATO_HASH = re.compile(
    r"(?:scrypt:\d+:\d+:\d+|pbkdf2:sha(?:256|512)(?::\d+)?)\$[A-Za-z0-9]+\$(?:[0-9a-f]{64}|[0-9a-f]{128})"
)


class ErroRedefinicao(Exception):
    """Falha prevista antes de qualquer gravação, com mensagem segura (sem senhas nem hashes)."""


def _senha_confere(armazenada, fornecida):
    if not isinstance(armazenada, str) or not isinstance(fornecida, str):
        return False
    if _FORMATO_HASH.fullmatch(armazenada):
        try:
            return check_password_hash(armazenada, fornecida)
        except (ValueError, TypeError):
            return False
    return hmac.compare_digest(armazenada.encode("utf-8"), fornecida.encode("utf-8"))


# ------------------------------------------------------------------ abertura do banco
def _estado_arquivos(caminho):
    """Hash do arquivo principal e tamanho do -wal: muda se outro processo gravar no banco."""
    wal = Path(f"{caminho}-wal")
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest(), (wal.stat().st_size if wal.exists() else None)


def _abrir(caminho, somente_leitura):
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroRedefinicao(f"banco de dados não encontrado em {caminho}; nenhum arquivo foi criado.")
    # mode=ro/rw: abre somente um banco que já existe; nunca cria um arquivo novo.
    # isolation_level=None: as transações são abertas e fechadas explicitamente.
    parametros, imutavel = "mode=rw", False
    if somente_leitura:
        # immutable=1 faz o SQLite não criar nem alterar -wal/-shm e não usar travas. Isso só é
        # correto se (1) não houver conteúdo pendente no -wal e (2) nenhum outro processo gravar
        # no banco durante a leitura. (1) é conferido aqui; (2) depende de o painel e a câmera
        # estarem fechados e é conferido depois, em verificar(), comparando o estado dos arquivos.
        wal = Path(f"{caminho}-wal")
        imutavel = not wal.exists() or wal.stat().st_size == 0
        parametros = "mode=ro&immutable=1" if imutavel else "mode=ro"
    con = sqlite3.connect(f"{caminho.resolve().as_uri()}?{parametros}", uri=True, timeout=5, isolation_level=None)
    return con, imutavel


def _localizar(con, email):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuario'").fetchone():
        raise ErroRedefinicao("a tabela usuario não existe neste banco.")
    linhas = con.execute("SELECT id_usuario, senha FROM usuario WHERE email = ?", (email,)).fetchall()
    if len(linhas) != 1:
        raise ErroRedefinicao("nenhuma conta encontrada com esse e-mail.")
    return linhas[0]


def _integridade(con):
    return con.execute("PRAGMA integrity_check").fetchone()[0]


def _contagens(con):
    tabelas = [t for (t,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabelas}


def validar_nova_senha(nova, confirmacao, atual):
    if nova != confirmacao:
        raise ErroRedefinicao("as duas senhas digitadas não coincidem.")
    if not nova.strip():
        raise ErroRedefinicao("a senha nova não pode ser vazia nem conter só espaços.")
    if len(nova) < SENHA_MINIMA:
        raise ErroRedefinicao(f"a senha nova precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if _senha_confere(atual, nova):
        raise ErroRedefinicao("a senha nova não pode ser igual à senha atual.")


# ------------------------------------------------------------------ backup protegido
def _eh_windows():
    return os.name == "nt"


def _powershell(script, **variaveis):
    """Executa o Windows PowerShell sem perfil; os valores entram por variáveis de ambiente, nunca no comando.

    O PSModulePath herdado (por exemplo, de um terminal PowerShell 7) é removido: com ele o
    powershell.exe 5.1 tenta carregar módulos do PowerShell 7 e falha. O script usa só a API .NET.
    """
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    env.update({f"OVERFLOW_PS_{k.upper()}": str(v) for k, v in variaveis.items()})
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, env=env, timeout=60)
    if r.returncode != 0 or r.stderr.strip():
        raise ErroRedefinicao("não foi possível consultar as permissões do Windows (PowerShell).")
    return r.stdout.strip()


def _sid_usuario_atual():
    sid = _powershell("[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise ErroRedefinicao("não foi possível identificar o usuário atual do Windows.")
    return sid


def _regras_acesso(caminho):
    saida = _powershell(
        "$p = $env:OVERFLOW_PS_ALVO; "
        "if ([System.IO.Directory]::Exists($p)) { $acl = [System.IO.DirectoryInfo]::new($p).GetAccessControl() } "
        "else { $acl = [System.IO.FileInfo]::new($p).GetAccessControl() }; "
        "'PROTEGIDA=' + $acl.AreAccessRulesProtected; "
        "foreach ($r in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) "
        "{ 'REGRA=' + $r.IdentityReference.Value + '|' + $r.AccessControlType }",
        alvo=caminho)
    linhas = saida.splitlines()
    protegida = [l.split("=", 1)[1].strip() for l in linhas if l.startswith("PROTEGIDA=")]
    if len(protegida) != 1:
        raise ErroRedefinicao("não foi possível ler as permissões do Windows.")
    regras = []
    for l in linhas:
        if l.startswith("REGRA="):
            sid, _, tipo = l[len("REGRA="):].strip().partition("|")
            regras.append({"sid": sid, "tipo": tipo})
    return protegida[0] == "True", regras


def _conferir_somente_usuario(caminho, sid, exigir_protegida, ja_tem_dados=False):
    protegida, regras = _regras_acesso(caminho)
    if (exigir_protegida and not protegida) or not regras or any(
            r.get("sid") != sid or r.get("tipo") != "Allow" for r in regras):
        consequencia = ("o arquivo JÁ contém dados do banco (inclusive a senha antiga): proteja-o ou mova-o "
                        "para um local protegido manualmente." if ja_tem_dados else "nenhum dado do banco foi copiado.")
        raise ErroRedefinicao(f"as permissões de {caminho} não ficaram restritas ao usuário atual; {consequencia}")


def _criar_pasta_protegida(pasta):
    """Cria uma pasta NOVA acessível somente pelo usuário atual (sem herança) e confere o resultado."""
    if not _eh_windows():
        raise ErroRedefinicao("a proteção de acesso do backup só está implementada para Windows; nada foi copiado. "
                              "Alternativa: faça o backup manualmente num local protegido e use --verificar.")
    pasta = Path(pasta)
    if pasta.exists():
        raise ErroRedefinicao(f"a pasta {pasta} já existe; informe uma pasta NOVA "
                              "(pastas e backups existentes não são alterados).")
    sid = _sid_usuario_atual()
    pasta.mkdir(parents=True)
    try:
        r = subprocess.run(["icacls", str(pasta), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise ErroRedefinicao("o icacls não conseguiu restringir as permissões da pasta de backup; nada foi copiado.")
        _conferir_somente_usuario(pasta, sid, exigir_protegida=True)
    except BaseException:
        try:
            pasta.rmdir()
        except OSError:
            pass
        raise
    return pasta, sid


def _nome_backup():
    return f"banco_antes_redefinicao_{datetime.now():%Y%m%d_%H%M%S_%f}.db"


def _avisar_backup_incompleto(pasta, motivo):
    try:
        arquivos = ", ".join(sorted(p.name for p in Path(pasta).iterdir())) or "(vazia)"
    except OSError:
        arquivos = "(não foi possível listar)"
    print(f"Atenção: o backup não foi concluído ({motivo}). Nada foi apagado. Pasta: {pasta}", file=sys.stderr)
    print(f"Conteúdo da pasta: {arquivos}", file=sys.stderr)
    print("Esses arquivos podem conter dados do banco, inclusive a senha antiga. A pasta foi criada com acesso "
          "restrito ao usuário atual; mantenha-a assim até decidir o que fazer com eles.", file=sys.stderr)


def fazer_backup(con, pasta):
    """Cópia consistente (inclui o conteúdo do WAL), em pasta protegida e conferida antes de receber dados.

    Se algo falhar depois de a pasta protegida existir, nada é apagado: os arquivos (possivelmente
    parciais) ficam nela e o caminho é informado.
    """
    pasta, sid = _criar_pasta_protegida(pasta)
    destino = pasta / _nome_backup()
    try:
        with open(destino, "xb"):
            pass
        _conferir_somente_usuario(destino, sid, exigir_protegida=False)
        copia = sqlite3.connect(destino)
        try:
            con.backup(copia)
            integridade = _integridade(copia)
        finally:
            copia.close()
        if integridade != "ok":
            raise ErroRedefinicao(f"o backup {destino} não passou na verificação de integridade.")
        _conferir_somente_usuario(destino, sid, exigir_protegida=False, ja_tem_dados=True)
    except BaseException as e:
        _avisar_backup_incompleto(pasta, str(e) if isinstance(e, ErroRedefinicao) else type(e).__name__)
        raise
    return destino, hashlib.sha256(destino.read_bytes()).hexdigest()


# ------------------------------------------------------------------ operações
def verificar(caminho, email):
    """Somente leitura: confirma que a conta existe e mostra o estado do banco."""
    caminho = Path(caminho)
    antes = _estado_arquivos(caminho) if caminho.is_file() else None
    con, imutavel = _abrir(caminho, somente_leitura=True)
    try:
        id_usuario, _ = _localizar(con, email)
        integridade = _integridade(con)
        contagens = _contagens(con)
    finally:
        con.close()
    if _estado_arquivos(caminho) != antes:
        raise ErroRedefinicao("o banco foi alterado durante a verificação: outro processo está usando o banco. "
                              "Feche o painel e a câmera e repita.")
    print(f"Conta encontrada: id_usuario={id_usuario}.")
    print(f"integrity_check: {integridade}")
    print("Linhas por tabela:", ", ".join(f"{t}={n}" for t, n in contagens.items()))
    if not imutavel:
        print("Aviso: o arquivo -wal tinha dados pendentes; a leitura usou mode=ro, e o SQLite pode ter "
              "atualizado o índice -shm (sem alterar dados).")
    print("Observação: a detecção de outro processo gravando durante a leitura é apenas um indício, não uma "
          "garantia; a verificação só é confiável com o painel e a câmera fechados.")
    print("Modo --verificar: nada foi gravado.")
    return 0 if integridade == "ok" else 1


def _ps(valor):
    """Texto entre aspas simples do PowerShell (aspas simples internas são duplicadas)."""
    return "'" + str(valor).replace("'", "''") + "'"


def _comandos_recuperacao(caminho, destino, sha):
    """Comandos PowerShell para preservar o estado atual e restaurar o backup consistente."""
    banco = Path(caminho).resolve()
    destino = Path(destino).resolve()
    estado = destino.parent.parent / f"{destino.parent.name}_estado_apos_falha"
    auxiliares = ", ".join(_ps(f"{banco}{s}") for s in ("", "-wal", "-shm", "-journal"))
    return [
        f"$estado = {_ps(estado)}",
        "New-Item -ItemType Directory -Path $estado -ErrorAction Stop | Out-Null",
        'icacls $estado /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F"',
        f"Get-Item -LiteralPath {auxiliares} -ErrorAction SilentlyContinue | Move-Item -Destination $estado",
        f"(Get-FileHash -LiteralPath {_ps(destino)} -Algorithm SHA256).Hash -eq {_ps(sha.upper())}",
        f"Copy-Item -LiteralPath {_ps(destino)} -Destination {_ps(banco)}",
        ".\\.venv\\Scripts\\python.exe scripts\\redefinir_senha.py --email <e-mail> --verificar",
    ]


def _avisar_falha_pos_commit(id_usuario, resultado, caminho, destino, sha):
    print(f"ATENÇÃO: a senha de id_usuario={id_usuario} FOI alterada (a gravação foi confirmada), "
          f"mas a verificação final de integridade do banco falhou: {resultado}.", file=sys.stderr)
    print("Não use o painel nem a câmera até resolver. O backup verificado de ANTES da alteração está em:",
          file=sys.stderr)
    print(f"    {destino}", file=sys.stderr)
    print("Procedimento seguro (com o painel, a câmera e qualquer script fechados), no PowerShell, na raiz do "
          "projeto. Ele MOVE o banco atual e os arquivos -wal/-shm/-journal para uma pasta protegida (nada é "
          "apagado), confere o hash do backup (deve mostrar True) e só então o copia para banco.db:", file=sys.stderr)
    for linha in _comandos_recuperacao(caminho, destino, sha):
        print(f"    {linha}", file=sys.stderr)


def redefinir(caminho, email, pasta_backup, pedir_senha=getpass.getpass):
    if not pasta_backup:
        raise ErroRedefinicao("--backup PASTA é obrigatório para redefinir a senha.")
    con, _ = _abrir(caminho, somente_leitura=False)
    try:
        id_usuario, senha_atual = _localizar(con, email)
        integridade_inicial = _integridade(con)
        if integridade_inicial != "ok":
            raise ErroRedefinicao(f"o banco não passou no integrity_check antes da alteração ({integridade_inicial}).")
        print(f"Conta encontrada: id_usuario={id_usuario}. integrity_check inicial: ok.")
        print(f"Use uma senha nova e exclusiva (não usada em nenhum outro serviço), com pelo menos {SENHA_MINIMA} "
              "caracteres.")
        nova = pedir_senha("Nova senha: ")
        confirmacao = pedir_senha("Repita a nova senha: ")
        validar_nova_senha(nova, confirmacao, senha_atual)
        novo_hash = generate_password_hash(nova)

        destino, sha = fazer_backup(con, pasta_backup)
        print(f"Backup criado, verificado (integrity_check: ok) e com acesso restrito ao usuário atual: {destino}")
        print(f"SHA-256 do backup: {sha}")

        antes = _contagens(con)
        con.execute("BEGIN IMMEDIATE")
        try:
            cur = con.execute("UPDATE usuario SET senha = ? WHERE id_usuario = ? AND email = ? AND senha = ?",
                              (novo_hash, id_usuario, email, senha_atual))
            if cur.rowcount != 1:
                raise ErroRedefinicao("a conta foi alterada por outro processo durante a operação.")
            gravada = con.execute("SELECT senha FROM usuario WHERE id_usuario = ?", (id_usuario,)).fetchone()[0]
            if not check_password_hash(gravada, nova):
                raise ErroRedefinicao("a verificação da senha gravada falhou.")
            if _contagens(con) != antes:
                raise ErroRedefinicao("a quantidade de linhas mudou durante a operação.")
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise

        # Daqui em diante a alteração já foi confirmada: nenhuma falha pode ser relatada como "nada foi alterado".
        try:
            integridade = _integridade(con)
        except BaseException as e:
            integridade = f"não foi possível executar ({type(e).__name__})"
    finally:
        con.close()

    if integridade != "ok":
        _avisar_falha_pos_commit(id_usuario, integridade, caminho, destino, sha)
        return 3
    print(f"Senha redefinida para id_usuario={id_usuario} (gravada somente como hash).")
    print("integrity_check final: ok")
    print("Linhas por tabela (iguais antes e depois):", ", ".join(f"{t}={n}" for t, n in antes.items()))
    print("O backup contém a senha ANTIGA: mantenha-o protegido e descarte-o depois de validar o login.")
    print("Recomendado: gere uma nova OVERFLOW_SECRET_KEY para encerrar sessões abertas.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Redefine a senha de uma conta do painel (somente hash).")
    parser.add_argument("--email", required=True, help="e-mail da conta")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--verificar", action="store_true", help="somente leitura: confere a conta e o banco")
    modo.add_argument("--backup", metavar="PASTA", help="pasta NOVA para o backup protegido, criado antes de gravar")
    args = parser.parse_args(argv)
    try:
        if args.verificar:
            return verificar(config.BANCO, args.email)
        return redefinir(config.BANCO, args.email, args.backup)
    except ErroRedefinicao as e:
        print(f"Erro: {e}", file=sys.stderr)
        print("Nenhuma alteração foi feita na senha.", file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print(f"Erro do banco de dados: {e}. Nenhuma alteração foi feita na senha.", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nOperação cancelada. Nenhuma alteração foi feita na senha.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
