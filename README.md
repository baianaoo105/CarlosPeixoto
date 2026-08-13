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

Configure `ADMIN_PASSWORD`, `SECRET_KEY` e a variável do banco nas configurações do projeto. O site reconhece automaticamente `DATABASE_URL`, `STORAGE_URL`, `POSTGRES_URL` ou `POSTGRES_PRISMA_URL` criadas pela integração Postgres/Neon. Em seguida, publique com:

```powershell
npx vercel --prod
```

O ZIP foi organizado com `app.py`, `vercel.json` e as demais pastas diretamente na raiz.

Se a integração criou `STORAGE_URL`, não é necessário renomeá-la: esta versão reconhece esse nome automaticamente.
