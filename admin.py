"""
Rotas da área administrativa do Sá Conecta.

Este arquivo conecta as páginas do painel às funções de autenticação
e às operações no banco de dados.

As consultas administrativas exigem uma sessão válida.
As alterações também exigem a verificação do token CSRF.
"""

import hmac
import os
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
)

from database import connect
from security import (
    COOKIE_NAME,
    SESSION_SECONDS,
    LoginLimited,
    get_session,
    login,
    logout,
)


# Valores aceitos para a situação de um cadastro:
# pending: aguarda revisão; approved: publicado; rejected: rejeitado.
Status = Literal["pending", "approved", "rejected"]


# Modelos dos dados recebidos pela API.

class LoginData(BaseModel):
    """Dados necessários para tentar entrar no painel."""

    # Recusa campos adicionais que não fazem parte do modelo.
    # A senha mantém seus espaços, pois eles podem fazer parte dela.
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class Revision(BaseModel):
    """Versão do cadastro que o administrador está visualizando."""

    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)


class ChangeStatus(Revision):
    """Recebe a revisão atual e a nova situação do contato."""

    status: Status


class EditContact(BaseModel):
    """Campos que podem ser alterados durante a revisão de um contato."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    revision: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=100)

    category: Literal[
        "Alimentação",
        "Mercados",
        "Saúde e bem-estar",
        "Serviços",
        "Moda e beleza",
        "Construção",
    ]

    phone: str = Field(max_length=20)
    address: str = Field(min_length=3, max_length=160)
    hours: str = Field(default="", max_length=100)
    description: str = Field(min_length=5, max_length=400)
    whatsapp: StrictBool = False

    @field_validator("phone")
    @classmethod
    def phone_digits(cls, value):
        """
        Verifica o formato do telefone e retorna somente os dígitos.

        O campo vazio é aceito aqui porque os exemplos não têm telefone.
        A rota de edição exige telefone quando o cadastro é real.
        """

        if not value:
            return ""

        if not re.fullmatch(r"[0-9() .-]+", value):
            raise ValueError("Telefone inválido.")

        digits = re.sub(r"[^0-9]", "", value)

        if len(digits) not in (10, 11):
            raise ValueError(
                "Telefone deve conter 10 ou 11 dígitos com DDD."
            )

        return digits


def make_admin_router(db_path, templates):
    """
    Cria as rotas administrativas usando o banco e os templates
    recebidos de main.py.

    As funções internas compartilham essas configurações.
    """

    router = APIRouter()

    # No ambiente com HTTPS, SA_COOKIE_SECURE=1 faz o navegador
    # enviar o cookie de sessão somente por conexões seguras.
    secure_cookie = os.getenv("SA_COOKIE_SECURE", "0") == "1"

    # Verificações compartilhadas pelas rotas.

    def session(request: Request):
        """Exige uma sessão existente e ainda válida no servidor."""

        token = request.cookies.get(COOKIE_NAME)
        current = get_session(token, db_path)

        if not current:
            raise HTTPException(
                status_code=401,
                detail="Sua sessão terminou. Entre novamente.",
            )

        return current

    def same_origin(request: Request):
        """
        Recusa solicitações identificadas como vindas de outro site.

        Quando o cabeçalho Origin está presente, compara seu endereço
        com a origem da aplicação, incluindo protocolo e porta.
        """

        origin = request.headers.get("origin")
        application_origin = str(request.base_url).rstrip("/")

        if origin and origin != application_origin:
            raise HTTPException(
                status_code=403,
                detail="Origem da solicitação não permitida.",
            )

        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(
                status_code=403,
                detail="Origem da solicitação não permitida.",
            )

    def mutation(request: Request, current=Depends(session)):
        """
        Protege as ações que alteram dados.

        Depends(session) verifica o login antes desta função.
        Depois, o token CSRF enviado pela página deve corresponder
        ao token associado à sessão no servidor.
        """

        same_origin(request)

        received_token = request.headers.get("x-csrf-token", "")
        expected_token = current["csrf_token"]

        tokens_match = hmac.compare_digest(
            received_token.encode("utf-8"),
            expected_token.encode("utf-8"),
        )

        if not tokens_match:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Não foi possível validar a ação. "
                    "Recarregue a página."
                ),
            )

        return current

    def find_item(db, item_id, revision):
        """
        Busca o cadastro e verifica se sua revisão ainda é a mesma.

        Isso evita que uma página desatualizada sobrescreva alterações
        feitas por outra aba ou sessão administrativa.
        """

        item = db.execute(
            """
            SELECT *
            FROM establishments
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

        if not item:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Este contato não existe mais. "
                    "Atualize a lista."
                ),
            )

        if item["revision"] != revision:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Este contato foi alterado em outra sessão. "
                    "Atualize a lista antes de continuar."
                ),
            )

        return item

    # Páginas de login e administração.

    @router.get("/admin/login", include_in_schema=False)
    def login_page(request: Request):
        """Exibe o formulário ou encaminha quem já está conectado."""

        token = request.cookies.get(COOKIE_NAME)

        if get_session(token, db_path):
            return RedirectResponse(
                "/admin",
                status_code=303,
            )

        return templates.TemplateResponse(
            request=request,
            name="admin-login.html",
        )

    @router.get("/admin", include_in_schema=False)
    def dashboard(request: Request):
        """Entrega o painel somente quando a sessão é válida."""

        token = request.cookies.get(COOKIE_NAME)

        if not get_session(token, db_path):
            return RedirectResponse(
                "/admin/login",
                status_code=303,
            )

        return templates.TemplateResponse(
            request=request,
            name="admin.html",
        )

    # Entrada, consulta da sessão e saída.

    @router.post("/api/admin/login")
    def sign_in(
        data: LoginData,
        request: Request,
        response: Response,
    ):
        """Verifica as credenciais e entrega o cookie da nova sessão."""

        same_origin(request)

        # O JavaScript do login envia este cabeçalho.
        # Ele complementa a proteção de origem; não substitui a senha.
        if request.headers.get("x-requested-with") != "SaConecta":
            raise HTTPException(
                status_code=403,
                detail="Abra a página de login para entrar.",
            )

        # Usa o endereço do cliente recebido pelo servidor para
        # identificar a origem na contagem de tentativas.
        source = (
            request.client.host
            if request.client
            else "unknown"
        )

        try:
            result = login(
                username=data.username,
                password=data.password,
                source=source,
                db_path=db_path,
            )
        except LoginLimited:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Muitas tentativas. Aguarde 15 minutos "
                    "antes de tentar novamente."
                ),
            )

        if not result:
            raise HTTPException(
                status_code=401,
                detail="Usuário ou senha incorretos.",
            )

        # Um novo login substitui a sessão anterior deste navegador.
        previous_token = request.cookies.get(COOKIE_NAME)

        if previous_token:
            logout(previous_token, db_path)

        response.set_cookie(
            key=COOKIE_NAME,
            value=result["token"],
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            max_age=SESSION_SECONDS,
            path="/",
        )

        return {"username": result["username"]}

    @router.get("/api/admin/session")
    def whoami(current=Depends(session)):
        """
        Informa o usuário conectado e o token CSRF usado pelo painel.

        O token que identifica a sessão permanece no cookie HttpOnly.
        """

        return {
            "username": current["username"],
            "csrf": current["csrf_token"],
        }

    @router.post(
        "/api/admin/logout",
        dependencies=[Depends(mutation)],
    )
    def sign_out(request: Request, response: Response):
        """Revoga a sessão no banco e remove o cookie do navegador."""

        logout(
            token=request.cookies[COOKIE_NAME],
            db_path=db_path,
        )

        response.delete_cookie(
            key=COOKIE_NAME,
            path="/",
            secure=secure_cookie,
            httponly=True,
            samesite="strict",
        )

        return {"message": "Sessão encerrada."}

    # Consulta e manutenção dos contatos.

    @router.get(
        "/api/admin/contatos",
        dependencies=[Depends(session)],
    )
    def contacts():
        """
        Lista os contatos de todas as situações, dos mais novos
        para os mais antigos.
        """

        with connect(db_path) as db:
            rows = db.execute(
                """
                SELECT
                    id,
                    name,
                    category,
                    phone,
                    address,
                    hours,
                    description,
                    whatsapp,
                    status,
                    is_demo,
                    created_at,
                    revision
                FROM establishments
                ORDER BY id DESC
                """
            )

            return [dict(row) for row in rows]

    @router.put(
        "/api/admin/contatos/{item_id}",
        dependencies=[Depends(mutation)],
    )
    def edit(item_id: int, data: EditContact):
        """Atualiza as informações, mantendo a situação do cadastro."""

        with connect(db_path) as db:
            # Mantém a consulta da revisão e a alteração na mesma
            # transação, impedindo outra escrita entre essas etapas.
            db.execute("BEGIN IMMEDIATE")

            item = find_item(
                db=db,
                item_id=item_id,
                revision=data.revision,
            )

            if not item["is_demo"] and not data.phone:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Informe um telefone com DDD "
                        "para este contato."
                    ),
                )

            # Sem telefone, o cadastro não pode oferecer WhatsApp.
            whatsapp_enabled = int(
                data.whatsapp and bool(data.phone)
            )

            db.execute(
                """
                UPDATE establishments
                SET
                    name = ?,
                    category = ?,
                    phone = ?,
                    address = ?,
                    hours = ?,
                    description = ?,
                    whatsapp = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (
                    data.name,
                    data.category,
                    data.phone or None,
                    data.address,
                    data.hours,
                    data.description,
                    whatsapp_enabled,
                    item_id,
                ),
            )

        return {
            "message": (
                "Informações salvas. "
                "O status do contato foi mantido."
            )
        }

    @router.patch(
        "/api/admin/contatos/{item_id}/status",
        dependencies=[Depends(mutation)],
    )
    def change_status(item_id: int, data: ChangeStatus):
        """Aprova, rejeita ou devolve um contato para revisão."""

        with connect(db_path) as db:
            db.execute("BEGIN IMMEDIATE")

            find_item(
                db=db,
                item_id=item_id,
                revision=data.revision,
            )

            db.execute(
                """
                UPDATE establishments
                SET
                    status = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (
                    data.status,
                    item_id,
                ),
            )

        # O catálogo público consulta apenas contatos aprovados.
        # Por isso, alterar o status também altera sua visibilidade.
        messages = {
            "approved": "Contato aprovado e publicado no catálogo.",
            "pending": "Contato voltou para revisão e saiu do catálogo.",
            "rejected": "Contato rejeitado e retirado do catálogo.",
        }

        return {"message": messages[data.status]}

    @router.delete(
        "/api/admin/contatos/{item_id}",
        dependencies=[Depends(mutation)],
    )
    def delete(item_id: int, data: Revision):
        """Remove definitivamente um contato após verificar sua revisão."""

        with connect(db_path) as db:
            db.execute("BEGIN IMMEDIATE")

            find_item(
                db=db,
                item_id=item_id,
                revision=data.revision,
            )

            db.execute(
                """
                DELETE FROM establishments
                WHERE id = ?
                """,
                (item_id,),
            )

        return {"message": "Contato excluído definitivamente."}

    return router