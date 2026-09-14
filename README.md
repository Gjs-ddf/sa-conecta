# Sá Conecta

Plataforma colaborativa para reunir contatos de comércios e serviços de Coronel João Sá — BA.

Projeto desenvolvido para a **Atividade Extensionista II: Tecnologia Aplicada à Inclusão Digital — Projeto**, do curso de **Análise e Desenvolvimento de Sistemas da UNINTER**.

## Objetivo

O Sá Conecta facilita a busca por informações de estabelecimentos e profissionais da cidade. A comunidade pode sugerir novos contatos, que ficam pendentes até serem revisados na área administrativa.

O projeto está relacionado aos seguintes Objetivos de Desenvolvimento Sustentável:

- ODS 8 — Trabalho decente e crescimento econômico;
- ODS 9 — Indústria, inovação e infraestrutura;
- ODS 11 — Cidades e comunidades sustentáveis.

## Funcionalidades

- catálogo de comércios e serviços;
- pesquisa por nome, serviço, endereço ou palavra-chave;
- filtro por categoria;
- formulário colaborativo para sugerir contatos;
- armazenamento das sugestões no SQLite;
- área administrativa com login;
- edição, aprovação, rejeição e exclusão de contatos;
- publicação no catálogo somente após aprovação;
- exibição de telefone e WhatsApp para contatos autorizados.

## Tecnologias utilizadas

- Python;
- FastAPI;
- SQLite;
- Jinja2;
- HTML;
- CSS;
- JavaScript.

## Estrutura do projeto

```text
sa-conecta/
├── static/
│   ├── admin.css
│   ├── admin.js
│   ├── script.js
│   └── style.css
├── templates/
│   ├── admin-login.html
│   ├── admin.html
│   └── index.html
├── tests/
│   ├── test_admin.py
│   └── test_api.py
├── admin.py
├── configurar_admin.py
├── database.py
├── main.py
├── requirements-dev.txt
├── requirements.txt
└── security.py
```

## Como executar no Windows

Abra o PowerShell na pasta que contém o arquivo `main.py`.

Crie o ambiente virtual:

```powershell
py -m venv .venv
```

Instale as dependências:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Inicie o servidor:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Acesse o catálogo em:

```text
http://127.0.0.1:8000
```

Para encerrar o servidor, pressione `Ctrl + C` no terminal.

## Configuração da área administrativa

Antes do primeiro acesso, crie o usuário administrador:

```powershell
.\.venv\Scripts\python.exe configurar_admin.py
```

Depois, acesse:

```text
http://127.0.0.1:8000/admin
```

Para redefinir as credenciais:

```powershell
.\.venv\Scripts\python.exe configurar_admin.py --redefinir
```

Nenhuma senha padrão é incluída no projeto.

## Testes

Instale as dependências de desenvolvimento:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Execute os testes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Resultado verificado durante o desenvolvimento: **13 testes e 9 subtestes aprovados**.

## Observações

- O arquivo `banco.db` é criado automaticamente na primeira execução.
- Os registros de demonstração são identificados como exemplos fictícios.
- Sugestões enviadas pela comunidade entram com situação pendente.
- O banco de dados, o ambiente virtual e possíveis arquivos de configuração local não são enviados ao repositório.
- Não utilize o Live Server nem abra o HTML diretamente; a interface deve ser acessada pelo endereço do FastAPI.

## Autor

**Gabriel de Jesus Santos**  
Curso Superior de Tecnologia em Análise e Desenvolvimento de Sistemas — UNINTER
