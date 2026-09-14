# Sá Conecta — FastAPI, SQLite e administração

**Já tem a versão anterior funcionando? Leia `ATUALIZAR_ADMIN.md` primeiro.**
Ele explica como atualizar preservando o banco e configurar seu login.

Esta versão conecta a interface ao servidor e ao banco. Mantém HTML, CSS e
JavaScript separados, com o visual da primeira versão.

## Executar no Windows

1. Extraia a pasta `sa-conecta` do ZIP. Não execute dentro do arquivo compactado.
2. Abra no VS Code a pasta que contém `main.py` e `database.py`.
3. Se já criou `.venv` na sua pasta de projeto, copie o conteúdo de `sa-conecta`
   para ela, mantendo `.venv`. Aceite substituir o HTML/JS anteriores apenas
   se não tiver alterações próprias; faça uma cópia antes se tiver editado.
4. Se precisar criar o ambiente nesta nova pasta, execute `py -m venv .venv`.
5. No terminal PowerShell, execute:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

6. Aguarde `Application startup complete` e abra http://127.0.0.1:8000.
   Não use Live Server nem abra o HTML diretamente nesta versão.
7. Para parar, use Ctrl+C no terminal. Para iniciar novamente, repita apenas
   o comando do Uvicorn. Mantenha o terminal aberto enquanto usar a página.

Se a porta 8000 estiver ocupada, acrescente `--port 8001` ao comando e use
http://127.0.0.1:8001. Se aparecer `Could not import module main`, confira
se o terminal está na pasta que contém `main.py`.

## O que já funciona

- O servidor entrega HTML, CSS e JavaScript pela mesma origem.
- O SQLite cria `banco.db` na pasta de `database.py`, sem instalação separada.
- Seis estabelecimentos fictícios são inseridos apenas uma vez.
- A página obtém categorias e estabelecimentos pela API; busca e filtros
  são aplicados no JavaScript sobre a lista de aprovados retornada pelo servidor.
- O formulário grava sugestões reais no banco local como `pending`.
- Nome, categoria, telefone, endereço, descrição e consentimento são validados
  também no servidor. Não é possível enviar `status=approved` no formulário/API.
- Sugestões pendentes não são retornadas pelo catálogo nem pelo endpoint de detalhe.
- Repetir o mesmo envio após uma falha de rede não duplica a sugestão enquanto
  a página mantém o mesmo identificador e os mesmos dados.
- Os contatos aprovados podem mostrar telefone e link para WhatsApp quando
  o responsável tiver marcado que o número recebe mensagens.

## Testar manualmente

Abra o site, busque `saude` (sem acento), escolha categorias e abra detalhes.
Envie uma sugestão de teste: anote o protocolo exibido. A sugestão não aparecerá
no catálogo porque está pendente. Pare e reinicie o servidor: o banco permanece.
Para confirmar a gravação sem instalar ferramentas adicionais, execute na pasta
do projeto (também funciona com o servidor parado):

```powershell
.\.venv\Scripts\python.exe conferir_pendentes.py
```

Não apague `banco.db` para reiniciar: isso apagaria os cadastros. O ZIP não inclui
banco pré-criado nem ambiente virtual. Os exemplos são identificados em cada card
e não têm números de telefone. `SA_SEED_DEMO=0` desativa a inserção de exemplos
em um banco novo; não remove exemplos já existentes.

## Administração

Execute `configurar_admin.py` pelo Python da sua `.venv` para definir usuário
e senha. Entre em http://127.0.0.1:8000/admin para revisar, editar, aprovar,
rejeitar e excluir contatos. As ações exigem sessão e proteção CSRF no servidor.
Consulte `ATUALIZAR_ADMIN.md` para o passo a passo e redefinição de senha.
A publicação na internet é uma etapa posterior; o uso atual é local.

## Arquivos

- `main.py`: rotas HTTP e validação de entrada/saída.
- `database.py`: esquema, exemplos e operações SQLite parametrizadas.
- `templates/index.html`: interface servida por Jinja2.
- `static/style.css`: estilos preservados da primeira versão.
- `static/script.js`: busca, modais e comunicação com a API.
- `tests/test_api.py`: integração com banco temporário, sem alterar `banco.db`.

Para executar os testes opcionais:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verificação desta entrega: testes de API e banco temporário executados com
sucesso, incluindo autenticação, autorização e moderação. Sintaxe JavaScript
e referências de arquivos também verificadas. Sem inspeção visual em navegador.

Referências de implementação: [templates e arquivos estáticos](https://fastapi.tiangolo.com/advanced/templates/)
e [inicialização com lifespan](https://fastapi.tiangolo.com/advanced/events/),
na documentação oficial do FastAPI.
