# Jornal Carlos Peixoto — projeto novo

Portal regional em Flask com notícias, regiões, vídeos, profissões, Login Cidadão, painel administrativo e candidaturas profissionais.

## Executar no Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="sua-senha"
$env:SECRET_KEY="uma-chave-longa-e-secreta"
.\.venv\Scripts\python.exe app.py
```

Acesse `http://127.0.0.1:5000`.

## Vercel

Configure `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY` e `POSTGRES_URL` (ou `DATABASE_URL`). Depois publique com `npx vercel --prod`.

## Observação sobre vídeos

O formulário valida vídeos de até 20 MB. A Vercel pode aplicar um limite menor ao corpo das requisições serverless; para uso intenso de vídeos, prefira armazenamento de objetos como Vercel Blob, Cloudinary ou R2.
