"""
Configura o usuário e a senha da área administrativa.

Este arquivo deve ser executado diretamente pelo terminal.
Nenhuma senha padrão é fornecida com o projeto.

Exemplos:

Criar o primeiro administrador:
    python configurar_admin.py

Redefinir as credenciais:
    python configurar_admin.py --redefinir
"""

import argparse
from getpass import getpass

from database import init_database
from security import init_security, set_admin


def create_argument_parser():
    """
    Configura os argumentos que podem ser recebidos pelo terminal.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Criar ou redefinir o administrador local "
            "do Sá Conecta."
        )
    )

    parser.add_argument(
        "--redefinir",
        action="store_true",
        help=(
            "Trocar as credenciais e encerrar "
            "todas as sessões administrativas."
        ),
    )

    return parser


def request_credentials():
    """
    Solicita o usuário e a senha pelo terminal.

    getpass oculta a senha durante a digitação.
    """

    username = input(
        "Nome de usuário (ex.: gabriel): "
    )

    password = getpass(
        "Senha (12 a 128 caracteres; não aparece ao digitar): "
    )

    password_confirmation = getpass(
        "Repita a senha: "
    )

    if password != password_confirmation:
        raise ValueError(
            "As senhas não são iguais. Execute novamente."
        )

    return username, password


def main():
    """
    Prepara o banco e configura a conta administrativa.

    Retorna 0 quando a configuração termina corretamente
    e 1 quando ocorre algum problema.
    """

    parser = create_argument_parser()
    arguments = parser.parse_args()

    # Garante que o banco e as tabelas necessárias existam.
    #
    # seed_demo=False evita inserir exemplos fictícios caso este
    # comando seja executado antes da primeira inicialização do site.
    init_database(seed_demo=False)
    init_security()

    try:
        username, password = request_credentials()

        set_admin(
            username=username,
            password=password,
            replace=arguments.redefinir,
        )

    except (ValueError, EOFError, KeyboardInterrupt) as error:
        print(
            f"\nConfiguração não concluída. {error}"
        )
        return 1

    print(
        "\nAdministrador configurado com sucesso."
    )
    print(
        "Entre em: http://127.0.0.1:8000/admin"
    )

    return 0


# Este bloco só é executado quando o arquivo é iniciado diretamente.
# Ele não será executado caso o arquivo seja importado por outro módulo.
if __name__ == "__main__":
    raise SystemExit(main())