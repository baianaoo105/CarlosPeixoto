# Jornal Carlos Peixoto

Portal de notícias em Flask preparado para publicação na Vercel.

## Recursos

- Fundo responsivo em azul-claro suave, combinando com a identidade do jornal.
- Foto opcional do profissional que forneceu a informação em cada notícia.
- Prévia com imagem, título e descrição ao compartilhar links do site ou das notícias.
- Contato particular com título, descrição, mensagem e até 3 fotos privadas.
- Exclusão individual de mensagens pelo administrador, com confirmação.
- Foto opcional do escritório ou local de atendimento em cada perfil profissional.
- O painel exige novo login quando é reaberto em outra aba ou após fechar a aba anterior.
- Crédito opcional do profissional que forneceu a informação em cada notícia.
- Notícias e profissionais organizados por editoria.
- Painel administrativo protegido por variável de ambiente.
- Cadastro, edição e exclusão de profissionais, horários e serviços pelo painel.
- Cadastro, edição e exclusão de notícias.
- Comentários públicos persistentes.
- Fotos armazenadas no banco para não desaparecerem na Vercel.
- Chat particular entre cada visitante e o administrador.
- Link do servidor do Discord no rodapé.
- Banco local SQLite para desenvolvimento e Postgres/Neon na Vercel.

## Executar no Windows

Dentro da pasta do projeto, execute:

```powershell
py -m venv .venv
```

Não é obrigatório ativar o ambiente. Instale diretamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Defina as configurações somente nesta janela:

```powershell
$env:ADMIN_PASSWORD="sua-senha-administrativa"
$env:SECRET_KEY="uma-chave-secreta-longa-e-diferente-da-senha"
```

Inicie:

```powershell
.\.venv\Scripts\python.exe app.py
```

Abra `http://127.0.0.1:5000`.

## Configuração obrigatória na Vercel

O SQLite funciona no computador, mas não aceita gravações persistentes na Vercel. Para comentários, notícias, fotos e chat funcionarem online, conecte um banco Postgres.

### 1. Criar o banco gratuito

1. Abra seu projeto na Vercel.
2. Entre em **Storage** ou **Marketplace**.
3. Procure por **Neon**.
4. Clique em **Install**.
5. Escolha o plano **Free ($0)**.
6. Crie o banco e conecte-o ao projeto `carlos-peixoto`.
7. Confirme que a Vercel adicionou a variável `DATABASE_URL` em **Settings → Environment Variables**.

O aplicativo cria automaticamente as tabelas e os dados de exemplo no primeiro acesso.

### 2. Variáveis protegidas

Em **Settings → Environment Variables**, mantenha estas três variáveis em Production e Preview:

- `ADMIN_PASSWORD`: senha escolhida para o painel.
- `SECRET_KEY`: chave longa e aleatória, diferente da senha.
- `DATABASE_URL`: criada automaticamente pela integração Neon.

Nunca escreva os valores dessas variáveis nos arquivos ou no GitHub.

### 3. Publicar novamente

Depois de conectar o banco e enviar estes arquivos atualizados, faça um **Redeploy** ou execute:

```powershell
vercel --prod
```

## Acessos

- Site: `https://carlos-peixoto.vercel.app`
- Painel: `https://carlos-peixoto.vercel.app/admin`
- Chat particular: `https://carlos-peixoto.vercel.app/contato`

As conversas recebidas aparecem no botão **Mensagens** do painel. Cada visitante identifica sua conversa por um cookie assinado; se apagar os dados do navegador, ele perde o acesso ao histórico daquela conversa.

## Observação sobre imagens

As fotos das notícias e dos profissionais são salvas no Postgres para garantir persistência na Vercel. O limite por imagem é 8 MB, mas imagens menores economizam o espaço do plano gratuito. Prefira JPG ou WEBP comprimido.
