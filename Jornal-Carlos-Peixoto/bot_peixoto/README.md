# BOT PEIXOTO

Bot do Discord ligado ao **Jornal Carlos Peixoto**. Ele publica automaticamente as novas notícias do site no canal escolhido e oferece comandos de música por barra (`/`).

## O que está incluído

- Consulta `https://carlos-peixoto.vercel.app/api/noticias` a cada 60 segundos.
- Publica somente notícias ainda não divulgadas pelo bot.
- Recupera o último ID pelo histórico do canal para evitar mensagens duplicadas após reinícios.
- Mostra título, resumo, editoria, fonte, foto e link da notícia.
- Toca áudio com pesquisa ou link usando yt-dlp e FFmpeg.
- Mantém uma fila musical separada para cada servidor.
- Entra automaticamente no canal de voz configurado e reconecta se a conexão cair.
- Repete continuamente a programação musical cadastrada no painel do Jornal.
- Dá prioridade aos pedidos feitos com `/tocar` e retoma a programação depois.

## Comandos de música

- `/tocar busca`: pesquisa ou abre o link e adiciona a música à fila.
- `/pausar`: pausa a música atual.
- `/continuar`: continua uma música pausada.
- `/pular`: passa para a próxima música.
- `/fila`: mostra a música atual e as próximas.
- `/parar`: para a reprodução e limpa a fila.
- `/sair`: desconecta o bot do canal de voz.

Use apenas áudios que você tem autorização para reproduzir e respeite as regras da plataforma de origem.

## 1. Publicar a conexão no site

Envie a versão atualizada do projeto do Jornal ao GitHub e aguarde o deploy da Vercel. Depois, abra no navegador:

```text
https://carlos-peixoto.vercel.app/api/noticias
```

Se aparecer um texto com `"news"`, a conexão do site está pronta. Se aparecer erro 404, a atualização ainda não foi publicada.

## 2. Criar o BOT PEIXOTO no Discord

1. Acesse `https://discord.com/developers/applications`.
2. Clique em **New Application** e use o nome **BOT PEIXOTO**.
3. Abra **Bot** e clique em **Reset Token** para gerar o token.
4. Copie o token e guarde-o. Ele funciona como uma senha: não envie em conversa, imagem ou GitHub.
5. Abra **Installation**.
6. Em **Guild Install**, selecione os escopos `bot` e `applications.commands`.
7. Conceda somente estas permissões:
   - View Channels;
   - Send Messages;
   - Embed Links;
   - Read Message History;
   - Connect;
   - Speak;
   - Use Voice Activity.
8. Copie o link de instalação, abra-o e escolha seu servidor.

Não é necessário ativar **Message Content Intent**, pois o bot usa comandos por barra.

## 3. Copiar os IDs do Discord

1. No Discord, abra **Configurações → Avançado** e ative **Modo desenvolvedor**.
2. Clique com o botão direito no ícone do servidor e escolha **Copiar ID do servidor**.
3. Clique com o botão direito no canal que receberá as notícias e escolha **Copiar ID do canal**.
4. Clique com o botão direito no canal de voz da programação 24 horas e copie também o ID.

## 4. Executar no Windows

O bot precisa do Python, do FFmpeg e de um interpretador JavaScript moderno para a pesquisa de músicas. O Node.js 24 que você já instalou atende a essa parte. Para instalar o FFmpeg pelo PowerShell:

```powershell
winget install --id Gyan.FFmpeg -e
```

Feche e reabra o terminal depois da instalação. Dentro da pasta `bot_peixoto`, execute:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

No arquivo `.env`, substitua os quatro valores principais:

```env
DISCORD_TOKEN=token_copiado_no_portal
DISCORD_GUILD_ID=id_do_seu_servidor
NEWS_CHANNEL_ID=id_do_canal_de_noticias
VOICE_CHANNEL_ID=id_do_canal_de_voz_24h
```

Salve e inicie:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Quando aparecer `BOT PEIXOTO conectado`, teste `/tocar` dentro do servidor.

## Programação musical pelo painel do Jornal

1. Entre no painel editorial do site.
2. Clique em **Programação musical**.
3. Clique em **Adicionar música**.
4. Informe um título e uma ordem de reprodução.
5. Cole um link ou envie um arquivo de áudio de até 50 MB.

Arquivos maiores são enviados e lidos em partes automaticamente para funcionar na Vercel. Mantenha o navegador aberto até a barra chegar a 100% e aparecer a confirmação de salvamento.
6. Mantenha a opção **Música ativa** marcada e salve.

Links do SoundCloud e de outras fontes compatíveis são abertos pelo yt-dlp. Um link do Spotify é usado para identificar o título; como o Spotify não fornece o áudio integral ao bot, o BOT PEIXOTO procura uma fonte de áudio compatível para a mesma música.

O bot consulta a programação do painel a cada 60 segundos. Ao chegar ao final, ele volta automaticamente à primeira música.

## 5. Manter o bot online

O site continua na Vercel, mas o bot musical precisa ficar conectado continuamente ao Discord. A Vercel executa funções por tempo limitado e não serve para manter uma conexão de voz e Gateway aberta indefinidamente.

Opções:

- Executar gratuitamente no seu computador. O bot fica offline quando o computador ou o terminal forem fechados.
- Hospedar a pasta `bot_peixoto` como um **worker** em um serviço que aceite Docker e processo contínuo. O `Dockerfile` já instala o FFmpeg.

Na hospedagem, cadastre `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, `NEWS_CHANNEL_ID`, `VOICE_CHANNEL_ID`, `SITE_URL`, `AUTOPLAY_24_7=true` e `MUSIC_REFRESH_INTERVAL=60` como variáveis protegidas. Nunca envie o arquivo `.env`.

Para realmente funcionar 24 horas por dia, a hospedagem do bot também precisa ficar ativa 24 horas. Se o serviço gratuito suspender processos inativos, ou se o computador for desligado, o bot ficará offline até o processo iniciar novamente.

## Primeira verificação de notícias

Por padrão, o bot registra as notícias que já existem e aguarda a próxima publicação. Isso evita divulgar todo o arquivo antigo de uma vez. Para divulgar também as notícias atuais no primeiro início, use:

```env
ANNOUNCE_EXISTING_NEWS=true
```

Depois do primeiro início, volte para `false`.

## Atualizar o reprodutor

Serviços de mídia mudam com frequência. Se a pesquisa deixar de funcionar, atualize o yt-dlp:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade yt-dlp
```
