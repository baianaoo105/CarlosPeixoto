# Jornal Carlos Peixoto — versão sem bot

Portal de notícias em Flask sem conexão com bot, Discord API ou programação musical.

## Recursos

- Notícias e comentários persistentes.
- Painel administrativo para notícias, profissionais e mensagens.
- Fotos de notícias, fontes, profissionais e escritórios.
- Profissional em destaque com motivo do destaque.
- Contato particular entre visitante e administrador.
- SQLite no computador e Postgres/Neon na Vercel.
- Layout responsivo em português do Brasil.

## Executar no Windows

Abra o PowerShell dentro desta pasta e execute:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:ADMIN_PASSWORD="sua-senha-administrativa"
$env:SECRET_KEY="uma-chave-secreta-longa-e-diferente"
.\.venv\Scripts\python.exe app.py
```

Abra `http://127.0.0.1:5000`.

## Publicar na Vercel

Mantenha no projeto as variáveis `ADMIN_PASSWORD`, `SECRET_KEY` e `DATABASE_URL`.
O `DATABASE_URL` deve apontar para um banco Postgres/Neon para que os dados online sejam persistentes.

Depois envie a pasta ao GitHub conectado à Vercel ou execute `vercel --prod`.

## Acessos

- Página inicial: `/`
- Painel: `/admin`
- Contato particular: `/contato`

Esta versão não contém a pasta do BOT PEIXOTO e bloqueia as antigas rotas de API e música.
