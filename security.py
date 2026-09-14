"""
Segurança e autenticação da área administrativa.

Este arquivo é responsável por:
- armazenar a senha do administrador de forma protegida;
- limitar tentativas incorretas de login;
- criar sessões administrativas temporárias;
- validar e encerrar sessões;
- criar os tokens usados contra solicitações indevidas.
"""

import hashlib
import hmac
import re
import secrets
import time

from database import DEFAULT_DB, connect


# ---------------------------------------------------------------------
# Configurações de segurança
# ---------------------------------------------------------------------

# Quantidade de repetições usadas para derivar o hash da senha.
PASSWORD_HASH_ITERATIONS = 600_000

# Mantido com o nome antigo porque outros arquivos podem importá-lo.
ITERATIONS = PASSWORD_HASH_ITERATIONS

# A sessão administrativa permanece válida por até oito horas.
SESSION_SECONDS = 8 * 60 * 60

# Período usado para contar tentativas incorretas de login.
LOGIN_WINDOW = 15 * 60

# Número máximo de tentativas dentro do período definido acima.
MAX_LOGIN_ATTEMPTS = 5

# Nome do cookie utilizado para identificar a sessão no navegador.
COOKIE_NAME = "sa_admin_session"

# Valores falsos utilizados para que a aplicação ainda execute o cálculo
# da senha quando não houver administrador configurado.
#
# Isso ajuda a evitar respostas muito diferentes entre um usuário
# inexistente e uma senha incorreta.
FAKE_SALT = "00" * 16
FAKE_PASSWORD_HASH = "00" * 32


class LoginLimited(Exception):
    """
    Indica que o limite de tentativas de login foi atingido.
    """

    pass


# ---------------------------------------------------------------------
# Preparação das tabelas de segurança
# ---------------------------------------------------------------------

def init_security(db_path=DEFAULT_DB):
    """
    Cria as tabelas necessárias para autenticação e sessões.

    Também adiciona a coluna de revisão aos estabelecimentos antigos,
    caso o banco tenha sido criado antes da área administrativa.
    """

    with connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS admin_account (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                username TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                iterations INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY,
                csrf_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_login_attempts (
                source TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL,
                started_at INTEGER NOT NULL
            );
            """
        )

        add_revision_column(db)


def add_revision_column(db):
    """
    Adiciona a coluna revision em bancos criados por versões antigas.

    Essa coluna permite identificar quando duas páginas administrativas
    tentam alterar o mesmo cadastro ao mesmo tempo.
    """

    columns = {
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(establishments)"
        )
    }

    if "revision" not in columns:
        db.execute(
            """
            ALTER TABLE establishments
            ADD COLUMN revision INTEGER NOT NULL DEFAULT 1
            """
        )


# ---------------------------------------------------------------------
# Proteção da senha
# ---------------------------------------------------------------------

def password_hash(
    password,
    salt,
    iterations=PASSWORD_HASH_ITERATIONS,
):
    """
    Transforma a senha em um hash usando PBKDF2-HMAC-SHA256.

    A senha original não é armazenada no banco. O salt é um valor
    aleatório que faz senhas iguais produzirem resultados diferentes.
    """

    password_bytes = password.encode("utf-8")
    salt_bytes = bytes.fromhex(salt)

    derived_password = hashlib.pbkdf2_hmac(
        "sha256",
        password_bytes,
        salt_bytes,
        iterations,
    )

    return derived_password.hex()


def hash_session_token(token):
    """
    Gera o hash de um token de sessão.

    O navegador recebe o token original, enquanto o banco armazena
    somente seu hash.
    """

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------
# Configuração do administrador
# ---------------------------------------------------------------------

def set_admin(
    username,
    password,
    db_path=DEFAULT_DB,
    replace=False,
):
    """
    Cria ou redefine a conta administrativa.

    Quando replace for verdadeiro, as credenciais anteriores serão
    substituídas. Todas as sessões existentes serão encerradas.
    """

    normalized_username = username.strip().lower()

    valid_username = re.fullmatch(
        r"[a-z0-9_.-]{3,40}",
        normalized_username,
    )

    if not valid_username:
        raise ValueError(
            "Use um usuário de 3 a 40 letras sem acentos, "
            "números, ponto, hífen ou sublinhado."
        )

    if not 12 <= len(password) <= 128:
        raise ValueError(
            "A senha deve ter de 12 a 128 caracteres."
        )

    # Um salt diferente é criado sempre que a senha é definida.
    salt = secrets.token_hex(16)

    digest = password_hash(
        password=password,
        salt=salt,
    )

    with connect(db_path) as db:
        # Impede que outra escrita altere essas informações
        # enquanto a conta está sendo configurada.
        db.execute("BEGIN IMMEDIATE")

        existing_account = db.execute(
            """
            SELECT 1
            FROM admin_account
            WHERE id = 1
            """
        ).fetchone()

        if existing_account and not replace:
            raise ValueError(
                "Já existe um administrador. Para trocar a senha, "
                "execute com --redefinir."
            )

        db.execute(
            """
            INSERT INTO admin_account (
                id,
                username,
                salt,
                password_hash,
                iterations
            )
            VALUES (1, ?, ?, ?, ?)

            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                salt = excluded.salt,
                password_hash = excluded.password_hash,
                iterations = excluded.iterations
            """,
            (
                normalized_username,
                salt,
                digest,
                PASSWORD_HASH_ITERATIONS,
            ),
        )

        # Redefinir as credenciais encerra todas as sessões anteriores.
        db.execute("DELETE FROM admin_sessions")
        db.execute("DELETE FROM admin_login_attempts")


# ---------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------

def login(
    username,
    password,
    source,
    db_path=DEFAULT_DB,
):
    """
    Verifica as credenciais e cria uma sessão administrativa.

    Retorna os dados da nova sessão quando o login for válido.
    Retorna None quando o usuário ou a senha estiver incorreto.
    """

    current_time = int(time.time())
    normalized_username = username.strip().lower()

    with connect(db_path) as db:
        # A transação imediata impede que tentativas simultâneas
        # ultrapassem o limite definido.
        db.execute("BEGIN IMMEDIATE")

        remove_expired_attempts(
            db=db,
            current_time=current_time,
        )

        attempt = db.execute(
            """
            SELECT attempts
            FROM admin_login_attempts
            WHERE source = ?
            """,
            (source,),
        ).fetchone()

        if (
            attempt
            and attempt["attempts"] >= MAX_LOGIN_ATTEMPTS
        ):
            raise LoginLimited()

        register_login_attempt(
            db=db,
            source=source,
            current_time=current_time,
        )

        account = db.execute(
            """
            SELECT *
            FROM admin_account
            WHERE id = 1
            """
        ).fetchone()

        # Mesmo sem uma conta configurada, um hash é calculado.
        # Assim, a resposta não termina imediatamente.
        salt = (
            account["salt"]
            if account
            else FAKE_SALT
        )

        iterations = (
            account["iterations"]
            if account
            else PASSWORD_HASH_ITERATIONS
        )

        stored_hash = (
            account["password_hash"]
            if account
            else FAKE_PASSWORD_HASH
        )

        calculated_hash = password_hash(
            password=password,
            salt=salt,
            iterations=iterations,
        )

        password_matches = hmac.compare_digest(
            calculated_hash,
            stored_hash,
        )

        username_matches = (
            account is not None
            and normalized_username == account["username"]
        )

        if not username_matches or not password_matches:
            # A tentativa incorreta será confirmada no banco
            # quando o contexto da conexão terminar.
            return None

        # O login foi aceito, portanto a contagem de erros é removida.
        db.execute(
            """
            DELETE FROM admin_login_attempts
            WHERE source = ?
            """,
            (source,),
        )

        remove_expired_sessions(
            db=db,
            current_time=current_time,
        )

        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)

        expires_at = current_time + SESSION_SECONDS

        db.execute(
            """
            INSERT INTO admin_sessions (
                token_hash,
                csrf_token,
                expires_at
            )
            VALUES (?, ?, ?)
            """,
            (
                hash_session_token(session_token),
                csrf_token,
                expires_at,
            ),
        )

        return {
            "token": session_token,
            "csrf": csrf_token,
            "username": account["username"],
        }


def register_login_attempt(db, source, current_time):
    """
    Registra uma tentativa de login para determinada origem.
    """

    db.execute(
        """
        INSERT INTO admin_login_attempts (
            source,
            attempts,
            started_at
        )
        VALUES (?, 1, ?)

        ON CONFLICT(source) DO UPDATE SET
            attempts = attempts + 1
        """,
        (
            source,
            current_time,
        ),
    )


def remove_expired_attempts(db, current_time):
    """
    Apaga contagens de login que já ultrapassaram a janela de 15 minutos.
    """

    limit_time = current_time - LOGIN_WINDOW

    db.execute(
        """
        DELETE FROM admin_login_attempts
        WHERE started_at <= ?
        """,
        (limit_time,),
    )


def remove_expired_sessions(db, current_time):
    """
    Remove sessões administrativas que já expiraram.
    """

    db.execute(
        """
        DELETE FROM admin_sessions
        WHERE expires_at <= ?
        """,
        (current_time,),
    )


# ---------------------------------------------------------------------
# Consulta e encerramento da sessão
# ---------------------------------------------------------------------

def get_session(token, db_path=DEFAULT_DB):
    """
    Verifica se um token representa uma sessão válida.

    Retorna os dados da sessão quando ela existe e ainda não expirou.
    Caso contrário, retorna None.
    """

    valid_token_format = (
        token
        and re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    )

    if not valid_token_format:
        return None

    token_digest = hash_session_token(token)
    current_time = int(time.time())

    with connect(db_path) as db:
        row = db.execute(
            """
            SELECT
                sessions.csrf_token,
                sessions.expires_at,
                account.username

            FROM admin_sessions AS sessions

            JOIN admin_account AS account
                ON account.id = 1

            WHERE sessions.token_hash = ?
              AND sessions.expires_at > ?
            """,
            (
                token_digest,
                current_time,
            ),
        ).fetchone()

        return dict(row) if row else None


def logout(token, db_path=DEFAULT_DB):
    """
    Encerra uma sessão removendo seu token do banco.
    """

    if not token:
        return

    token_digest = hash_session_token(token)

    with connect(db_path) as db:
        db.execute(
            """
            DELETE FROM admin_sessions
            WHERE token_hash = ?
            """,
            (token_digest,),
        )