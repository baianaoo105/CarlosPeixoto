# Jornal Carlos Peixoto

Portal de notícias responsivo em Flask, com identidade própria, SQLite, painel editorial, upload de fotos e comentários.

## Recursos

- Página inicial com destaque, notícias do dia e área principal do jornalista.
- Editorias Polícia, Médicos, Bombeiros, Juiz, Advogado e Jornalista.
- Perfis profissionais e todas as seções de serviço solicitadas.
- Painel protegido para cadastrar, editar e excluir notícias.
- Upload de PNG, JPG, WEBP e GIF (máximo de 8 MB).
- Comentários persistentes em cada notícia.
- Banco SQLite criado automaticamente, já com dados de exemplo.
- Layout responsivo, validações básicas e páginas de erro.

## Como executar no Windows

1. Instale o Python 3.10 ou mais recente em https://www.python.org/downloads/ e marque **Add Python to PATH** durante a instalação.
2. Extraia o ZIP e abra o PowerShell dentro da pasta `Jornal-Carlos-Peixoto`.
3. Crie o ambiente virtual:

```powershell
python -m venv .venv
```

4. Ative-o:

```powershell
.\.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativação, execute uma vez na mesma janela:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

5. Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

6. Defina a senha administrativa e uma chave secreta (obrigatório):

```powershell
$env:ADMIN_PASSWORD="a-senha-administrativa-escolhida"
$env:SECRET_KEY="uma-chave-secreta-longa-e-aleatoria"
```

7. Inicie o site:

```powershell
python app.py
```

8. Abra `http://127.0.0.1:5000` no navegador. O painel fica em `http://127.0.0.1:5000/admin`.

Por segurança, o painel não possui senha padrão e não funciona enquanto `ADMIN_PASSWORD` não estiver configurada. A senha nunca deve ser escrita nos arquivos HTML, no código ou em um repositório público.

### Configuração na Vercel

No projeto da Vercel, abra **Settings → Environment Variables** e adicione:

- `ADMIN_PASSWORD`: a senha administrativa escolhida.
- `SECRET_KEY`: uma sequência longa, aleatória e diferente da senha.

Marque os ambientes **Production**, **Preview** e **Development**, salve e faça um novo **Redeploy**. Não escreva os valores dessas variáveis no código.

## Estrutura e dados

- `app.py`: aplicação e rotas.
- `templates/`: páginas HTML.
- `static/`: CSS, JavaScript e ícone.
- `schema.sql` e `seed.sql`: estrutura e conteúdo inicial.
- `uploads/`: fotos enviadas pelo painel.
- `jornal.db`: banco criado na primeira execução.

Para restaurar os dados de exemplo, pare o servidor, exclua apenas `jornal.db` e inicie novamente. Para publicar na internet, use um servidor WSGI, HTTPS e uma senha forte.
