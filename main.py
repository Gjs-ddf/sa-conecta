"""
Arquivo principal da aplicação Sá Conecta.

Responsabilidades:
- iniciar o FastAPI;
- preparar o banco de dados;
- servir as páginas HTML e os arquivos estáticos;
- disponibilizar as rotas públicas da API;
- incluir as rotas protegidas da administração.
"""

import logging
import os
import re
import sqlite3

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
)

from admin import make_admin_router
from database import (
    BASE_DIR,
    CATEGORIES,
    DEFAULT_DB,
    get_approved,
    init_database,
    list_approved,
    save_suggestion,
)
from security import init_security


# ---------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------

APP_TITLE = "Sá Conecta"
APP_VERSION = "0.3.0"

STATIC_DIRECTORY = BASE_DIR / "static"
TEMPLATES_DIRECTORY = BASE_DIR / "templates"


# Categorias aceitas pela API.
#
# O Literal faz o Pydantic recusar automaticamente qualquer categoria
# que não esteja presente nessa lista.
Category = Literal[
    "Alimentação",
    "Mercados",
    "Saúde e bem-estar",
    "Serviços",
    "Moda e beleza",
    "Construção",
]


# Cabeçalhos aplicados às páginas e rotas administrativas.
#
# Eles evitam o armazenamento das páginas no cache e dificultam que
# a administração seja aberta dentro de páginas externas.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


# ---------------------------------------------------------------------
# Modelos de entrada e saída da API
# ---------------------------------------------------------------------

class Suggestion(BaseModel):
    """
    Representa os dados recebidos pelo formulário público.

    O Pydantic verifica tipos, tamanhos e campos desconhecidos antes
    de a sugestão chegar ao banco de dados.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    name: str = Field(min_length=2, max_length=100)
    category: Category
    phone: str = Field(min_length=10, max_length=20)
    address: str = Field(min_length=3, max_length=160)
    hours: str = Field(default="", max_length=100)
    description: str = Field(min_length=5, max_length=400)
    whatsapp: StrictBool = False
    consent: StrictBool
    request_id: UUID

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        """
        Valida o telefone e devolve somente os números.

        São aceitos formatos como:
        - (75) 99999-9999
        - 75999999999
        - (75) 3333-3333
        """

        allowed_format = re.fullmatch(r"[0-9() .-]+", value)

        if not allowed_format:
            raise ValueError(
                "Use apenas números, espaços, parênteses ou hífen "
                "no telefone."
            )

        digits = re.sub(r"[^0-9]", "", value)

        if len(digits) not in (10, 11):
            raise ValueError(
                "Informe 10 ou 11 dígitos, incluindo o DDD, "
                "sem o código 55."
            )

        return digits

    @field_validator("consent")
    @classmethod
    def validate_consent(cls, value):
        """
        Impede o envio sem a confirmação de que os dados podem
        ser fornecidos para publicação no guia.
        """

        if not value:
            raise ValueError(
                "Confirme que pode fornecer as informações para o guia."
            )

        return value


class Establishment(BaseModel):
    """
    Define os campos de um estabelecimento que podem ser enviados
    para o catálogo público.
    """

    id: int
    name: str
    category: str
    phone: str | None
    address: str
    hours: str
    description: str
    whatsapp: bool
    is_demo: bool


class Receipt(BaseModel):
    """
    Resposta apresentada após o recebimento de uma sugestão.
    """

    protocol: int
    message: str


# ---------------------------------------------------------------------
# Criação da aplicação
# ---------------------------------------------------------------------

def create_app(db_path=DEFAULT_DB, seed_demo=True):
    """
    Cria e configura uma instância da aplicação.

    Receber o caminho do banco como argumento permite utilizar um
    banco temporário durante os testes, sem alterar o banco principal.
    """

    db_path = Path(db_path)

    @asynccontextmanager
    async def lifespan(_app):
        """
        Executa as configurações necessárias antes de o servidor
        começar a receber solicitações.
        """

        init_database(
            db_path=db_path,
            seed_demo=seed_demo,
        )

        init_security(db_path)

        yield

    application = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan,
    )

    # A pasta "static" contém somente arquivos que podem ser acessados
    # pelo navegador, como CSS e JavaScript.
    application.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIRECTORY)),
        name="static",
    )

    # Os arquivos HTML ficam na pasta "templates".
    templates = Jinja2Templates(
        directory=str(TEMPLATES_DIRECTORY)
    )

    # Adiciona as rotas de login e administração definidas em admin.py.
    admin_router = make_admin_router(
        db_path=db_path,
        templates=templates,
    )

    application.include_router(admin_router)

    # -----------------------------------------------------------------
    # Segurança das páginas administrativas
    # -----------------------------------------------------------------

    @application.middleware("http")
    async def add_admin_security_headers(request: Request, call_next):
        """
        Acrescenta cabeçalhos de segurança às páginas e rotas
        administrativas.
        """

        response = await call_next(request)

        is_admin_route = request.url.path.startswith(
            ("/admin", "/api/admin")
        )

        if is_admin_route:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers[
                "Content-Security-Policy"
            ] = CONTENT_SECURITY_POLICY

        return response

    # -----------------------------------------------------------------
    # Tratamento de erros
    # -----------------------------------------------------------------

    @application.exception_handler(sqlite3.Error)
    async def handle_database_error(
        _request: Request,
        exception: sqlite3.Error,
    ):
        """
        Intercepta erros do SQLite e devolve uma mensagem compreensível.

        O erro técnico é registrado no terminal, enquanto o visitante
        recebe somente uma mensagem segura e simples.
        """

        logging.error(
            "Falha SQLite: %s",
            type(exception).__name__,
        )

        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Não foi possível acessar o banco. "
                    "Tente novamente em instantes."
                )
            },
        )

    # -----------------------------------------------------------------
    # Página pública
    # -----------------------------------------------------------------

    @application.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def home(request: Request):
        """
        Entrega a página principal do catálogo.
        """

        return templates.TemplateResponse(
            request=request,
            name="index.html",
        )

    # -----------------------------------------------------------------
    # Rotas públicas da API
    # -----------------------------------------------------------------

    @application.get(
        "/api/categorias",
        response_model=list[str],
    )
    def get_categories():
        """
        Retorna as categorias usadas no formulário e nos filtros.
        """

        return list(CATEGORIES)

    @application.get(
        "/api/estabelecimentos",
        response_model=list[Establishment],
    )
    def get_establishments():
        """
        Retorna somente os estabelecimentos aprovados.
        """

        return list_approved(db_path)

    @application.get(
        "/api/estabelecimentos/{item_id}",
        response_model=Establishment,
    )
    def get_establishment(item_id: int):
        """
        Retorna um estabelecimento aprovado pelo protocolo.
        """

        establishment = get_approved(
            item_id=item_id,
            db_path=db_path,
        )

        if establishment is None:
            raise HTTPException(
                status_code=404,
                detail="Estabelecimento não encontrado.",
            )

        return establishment

    @application.post(
        "/api/sugestoes",
        status_code=201,
        response_model=Receipt,
    )
    def create_suggestion(suggestion: Suggestion):
        """
        Recebe uma sugestão pública e a salva como pendente.

        A sugestão somente aparecerá no catálogo após a aprovação
        realizada pela área administrativa.
        """

        suggestion_data = suggestion.model_dump(mode="json")

        try:
            protocol = save_suggestion(
                data=suggestion_data,
                db_path=db_path,
            )
        except ValueError as exception:
            raise HTTPException(
                status_code=409,
                detail=str(exception),
            ) from exception

        return Receipt(
            protocol=protocol,
            message=(
                "Sugestão recebida. Ela ficará pendente "
                "até a revisão administrativa."
            ),
        )

    return application


# ---------------------------------------------------------------------
# Aplicação utilizada pelo Uvicorn
# ---------------------------------------------------------------------

# Por padrão, um banco novo recebe os registros fictícios.
#
# Para iniciar um banco novo sem esses exemplos, defina:
# SA_SEED_DEMO=0
seed_demo_records = os.getenv("SA_SEED_DEMO", "1") == "1"

app = create_app(seed_demo=seed_demo_records)