# Jornal Carlos Peixoto — reconstruído sem bot

Portal Flask independente, sem BOT PEIXOTO, API do bot ou programação musical.

## Rodar no Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:ADMIN_PASSWORD="sua-senha"
$env:SECRET_KEY="uma-chave-secreta-longa"
.\.venv\Scripts\python.exe app.py
```

Abra `http://127.0.0.1:5000`.

## Vercel

Configure `ADMIN_PASSWORD`, `SECRET_KEY` e `DATABASE_URL` nas variáveis do projeto. `DATABASE_URL` deve apontar para o Postgres/Neon já conectado. Em seguida, publique com:

```powershell
npx vercel --prod
```

O ZIP foi organizado com `app.py`, `vercel.json` e as demais pastas diretamente na raiz.
