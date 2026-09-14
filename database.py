"""
Responsável pela persistência dos dados no SQLite.

Este arquivo:
- cria o banco e suas tabelas;
- adiciona os registros fictícios de demonstração;
- consulta os estabelecimentos aprovados;
- salva novas sugestões como pendentes.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
import os

# Caminho da pasta em que este arquivo está localizado.
BASE_DIR = Path(__file__).resolve().parent

# O banco será criado nessa mesma pasta.
DEFAULT_DB = Path(os.getenv("SA_DB_PATH", BASE_DIR / "banco.db"))


# Categorias disponíveis no formulário e no catálogo.
CATEGORIES = (
    "Alimentação",
    "Mercados",
    "Saúde e bem-estar",
    "Serviços",
    "Moda e beleza",
    "Construção",
)


# Registros usados apenas para demonstrar o funcionamento do site.
# Nenhum telefone ou estabelecimento real é inventado.
DEMO_ROWS = (
    (
        "demo-padaria",
        "Padaria Exemplo",
        "Alimentação",
        "Pães, bolos e lanches para o café da manhã ou da tarde.",
    ),
    (
        "demo-mercado",
        "Mercado Exemplo",
        "Mercados",
        "Alimentos, produtos de limpeza e itens para o dia a dia.",
    ),
    (
        "demo-oficina",
        "Oficina Exemplo",
        "Serviços",
        "Manutenção de motocicletas, revisão e pequenos reparos.",
    ),
    (
        "demo-salao",
        "Salão Exemplo",
        "Moda e beleza",
        "Cortes de cabelo e cuidados de beleza com agendamento.",
    ),
    (
        "demo-farmacia",
        "Farmácia Exemplo",
        "Saúde e bem-estar",
        "Itens de higiene e cuidados pessoais em um só lugar.",
    ),
    (
        "demo-construcao",
        "Construção Exemplo",
        "Construção",
        "Materiais e ferramentas para construir, reformar e reparar.",
    ),
)


@contextmanager
def connect(db_path=DEFAULT_DB):
    """
    Abre uma conexão com o SQLite e a fecha automaticamente.

    A propriedade row_factory permite acessar os resultados pelo nome
    da coluna, como row["name"], em vez de usar apenas posições numéricas.

    Se a operação terminar corretamente, as mudanças são confirmadas.
    Se ocorrer uma exceção, o SQLite desfaz a transação.
    """

    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_database(db_path=DEFAULT_DB, seed_demo=True):
    """
    Cria a estrutura inicial do banco sem apagar dados existentes.

    Quando seed_demo for verdadeiro, os seis registros fictícios serão
    cadastrados apenas uma vez.
    """

    with connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS establishments (
                id INTEGER PRIMARY KEY,

                name TEXT NOT NULL
                    CHECK(length(trim(name)) BETWEEN 2 AND 100),

                category TEXT NOT NULL,
                phone TEXT,
                address TEXT NOT NULL,

                hours TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,

                whatsapp INTEGER NOT NULL DEFAULT 0
                    CHECK(whatsapp IN (0, 1)),

                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'approved', 'rejected')),

                is_demo INTEGER NOT NULL DEFAULT 0
                    CHECK(is_demo IN (0, 1)),

                request_id TEXT UNIQUE,

                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            );

            CREATE INDEX IF NOT EXISTS idx_establishments_status
                ON establishments(status);

            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        if seed_demo:
            insert_demo_records(db)

        update_last_contact_id(db)

        # Permite que o SQLite atualize informações usadas
        # para escolher formas eficientes de executar consultas.
        db.execute("PRAGMA optimize")


def insert_demo_records(db):
    """
    Insere os estabelecimentos fictícios somente na primeira execução.

    A chave demo_seed_v1 funciona como uma marca indicando que os
    exemplos já foram cadastrados.
    """

    demo_already_inserted = db.execute(
        """
        SELECT 1
        FROM app_metadata
        WHERE key = ?
        """,
        ("demo_seed_v1",),
    ).fetchone()

    if demo_already_inserted:
        return

    for request_id, name, category, description in DEMO_ROWS:
        db.execute(
            """
            INSERT INTO establishments (
                name,
                category,
                address,
                hours,
                description,
                status,
                is_demo,
                request_id
            )
            VALUES (?, ?, ?, ?, ?, 'approved', 1, ?)
            """,
            (
                name,
                category,
                "Centro · endereço demonstrativo",
                "Exemplo: segunda a sábado, 8h às 18h",
                description,
                request_id,
            ),
        )

    # Registra que os exemplos já foram inseridos.
    db.execute(
        """
        INSERT INTO app_metadata (key, value)
        VALUES (?, ?)
        """,
        ("demo_seed_v1", "1"),
    )


def update_last_contact_id(db):
    """
    Mantém registrado o maior protocolo já utilizado.

    Isso impede que o protocolo de um contato excluído seja reutilizado
    posteriormente por outro cadastro.
    """

    db.execute(
        """
        INSERT INTO app_metadata (key, value)
        VALUES (
            'last_contact_id',
            (SELECT COALESCE(MAX(id), 0) FROM establishments)
        )
        ON CONFLICT(key) DO UPDATE SET
            value = MAX(
                CAST(value AS INTEGER),
                (SELECT COALESCE(MAX(id), 0) FROM establishments)
            )
        """
    )


def list_approved(db_path=DEFAULT_DB):
    """
    Retorna todos os estabelecimentos aprovados.

    Contatos pendentes e rejeitados não são mostrados no catálogo público.
    """

    with connect(db_path) as db:
        rows = db.execute(
            """
            SELECT *
            FROM establishments
            WHERE status = 'approved'
            ORDER BY id
            """
        ).fetchall()

        return [dict(row) for row in rows]


def get_approved(item_id, db_path=DEFAULT_DB):
    """
    Busca um estabelecimento aprovado pelo seu identificador.

    Retorna None quando o contato não existe ou não está aprovado.
    """

    with connect(db_path) as db:
        row = db.execute(
            """
            SELECT *
            FROM establishments
            WHERE id = ?
              AND status = 'approved'
            """,
            (item_id,),
        ).fetchone()

        return dict(row) if row else None


def save_suggestion(data, db_path=DEFAULT_DB):
    """
    Salva uma sugestão com o status pendente.

    O request_id identifica uma tentativa de envio. Se a resposta do
    servidor se perder e o navegador repetir a mesma solicitação, o
    cadastro existente será devolvido sem criar uma duplicação.
    """

    values = (
        data["name"],
        data["category"],
        data["phone"],
        data["address"],
        data["hours"],
        data["description"],
        int(data["whatsapp"]),
        data["request_id"],
    )

    fields_to_compare = (
        "name",
        "category",
        "phone",
        "address",
        "hours",
        "description",
        "whatsapp",
        "request_id",
    )

    with connect(db_path) as db:
        # Bloqueia temporariamente outras escritas enquanto o protocolo
        # é calculado e o cadastro é inserido.
        db.execute("BEGIN IMMEDIATE")

        existing_suggestion = db.execute(
            """
            SELECT *
            FROM establishments
            WHERE request_id = ?
            """,
            (data["request_id"],),
        ).fetchone()

        if existing_suggestion:
            existing_values = tuple(
                existing_suggestion[field]
                for field in fields_to_compare
            )

            if existing_values != values:
                raise ValueError(
                    "Este identificador já foi usado com outros dados."
                )

            return existing_suggestion["id"]

        metadata = db.execute(
            """
            SELECT value
            FROM app_metadata
            WHERE key = 'last_contact_id'
            """
        ).fetchone()

        last_id = int(metadata["value"]) if metadata else 0
        new_id = last_id + 1

        db.execute(
            """
            INSERT INTO establishments (
                id,
                name,
                category,
                phone,
                address,
                hours,
                description,
                whatsapp,
                request_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id, *values),
        )

        db.execute(
            """
            INSERT INTO app_metadata (key, value)
            VALUES ('last_contact_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(new_id),),
        )

        return new_id