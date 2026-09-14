# Instalar a área administrativa — Sá Conecta

## Para quem já tem o site funcionando

1. Pare o servidor com **Ctrl+C** no terminal.
2. Faça uma cópia de segurança do arquivo `banco.db` em outra pasta.
3. Extraia o ZIP e copie o **conteúdo** de `sa-conecta` para sua pasta atual,
   onde estão `main.py`, `database.py`, `banco.db` e `.venv`.
   Aceite substituir os arquivos de código com o mesmo nome e mescle as pastas
   `static`, `templates` e `tests`. Se tiver feito mudanças próprias no código,
   guarde uma cópia delas antes.
4. **Mantenha seu `banco.db` e sua `.venv`.** O pacote não contém nenhum deles.
   A atualização acrescenta tabelas de administração e uma coluna de controle,
   preservando os cadastros, IDs, telefones e situações existentes.
5. Abra o PowerShell nessa pasta e configure sua conta:

```powershell
.\.venv\Scripts\python.exe configurar_admin.py
```

6. Escolha um usuário (ex.: `gabriel`) e uma senha de **12 a 128 caracteres**.
   Repita a senha quando solicitado. A senha não aparece ao digitar: é normal.
   O usuário aceita letras sem acento, números, ponto, hífen e sublinhado.
   Não há senha padrão e não é necessário enviar sua senha a ninguém.
7. Inicie novamente o servidor:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

8. Abra **http://127.0.0.1:8000/admin** e entre com a conta criada.

O login usa as dependências que você já instalou. Não é necessário instalar
uma biblioteca nova para esta atualização. Se recriar o ambiente, instale
normalmente com `python.exe -m pip install -r requirements.txt`.

## Primeiro teste

O painel abre em **Pendentes**. Localize a sugestão que você enviou:

- **Editar:** revise nome, categoria, telefone, endereço, horário e descrição.
  Salvar mantém o status. Se já estiver aprovado, a edição altera o catálogo.
- **Aprovar:** confirme o nome do contato. Abra o guia público e recarregue;
  o contato deve aparecer na busca e na categoria correspondente.
- **Rejeitar:** mantém o cadastro no painel, mas fora do catálogo público.
- **Revisar:** devolve para pendentes e retira da listagem pública.
- **Excluir:** pede confirmação e remove definitivamente o contato do banco.
  O painel não oferece desfazer. Para apenas ocultar, use Rejeitar ou Revisar.
- **Sair:** encerra a sessão no servidor. O login será necessário novamente.

Os seis exemplos continuam identificados como fictícios. Você pode excluí-los
individualmente quando terminar os testes; eles não são recriados no reinício.
Editar um exemplo não o transforma em um cadastro real. Use o formulário
público e a aprovação para adicionar contatos reais.

## Se esquecer a senha

No seu computador, execute o comando abaixo e defina novamente o usuário e a
senha. As sessões existentes serão encerradas; os contatos serão preservados.

```powershell
.\.venv\Scripts\python.exe configurar_admin.py --redefinir
```

Cinco tentativas incorretas no mesmo endereço de origem bloqueiam novas
tentativas por 15 minutos. Se ainda não criou a conta, use o configurador.

## Organização

- `admin.py`: rotas e permissões do painel.
- `security.py`: verificação de senha, sessão e limite de tentativas.
- `configurar_admin.py`: criação ou redefinição da conta pelo terminal.
- `templates/admin-login.html` e `templates/admin.html`: páginas separadas.
- `static/admin.css` e `static/admin.js`: visual e interações do painel.
- `main.py` e `database.py`: integração e preservação dos dados existentes.

As senhas são armazenadas como derivação PBKDF2-HMAC-SHA256 com salt individual
e 600 mil iterações. Sessões duram até 8 horas, usam tokens aleatórios, são
revogadas ao sair ou redefinir a senha e usam cookie HttpOnly/SameSite Strict.
Cada mutação exige autorização no servidor e token CSRF. O painel evita cache,
enquadramento por outro site e execução de scripts externos. As edições usam
controle de revisão para não sobrescrever silenciosamente outra alteração.

Esta entrega segue o uso local atual. Ao hospedar na internet, será necessário
HTTPS e configurar `SA_COOKIE_SECURE=1` no ambiente do servidor, além de revisar
origem/proxy, backup e proteção do formulário público contra spam. Não use essa
opção no endereço HTTP local, pois o navegador não enviará o cookie seguro.

## Verificação

Os testes automatizados de API e banco temporário cobrem acesso sem sessão,
login, cookie, CSRF, edição, mudanças de status, exclusão, expiração, saída,
troca de senha, limite de tentativas, validação, conflito de revisão e sugestões.
Também foram conferidos a sintaxe JavaScript e os vínculos entre as páginas e
os arquivos. Não foi realizada inspeção visual em navegador nesta entrega.

Para repetir os testes opcionais no seu computador:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Referências: [armazenamento de senhas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[sessões](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
e [proteção CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), OWASP.
