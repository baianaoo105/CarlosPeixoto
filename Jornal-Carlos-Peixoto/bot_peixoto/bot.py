import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


BASE_DIR = Path(__file__).resolve().parent
BOT_AUDIO_LIMIT = 50 * 1024 * 1024
BOT_AUDIO_CHUNK_SIZE = 3 * 1024 * 1024
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot_peixoto")


def env_int(name: str, default: int = 0) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"A variavel {name} precisa conter apenas numeros.") from error


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "sim", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    guild_id: int
    news_channel_id: int
    voice_channel_id: int
    site_url: str
    news_interval: int
    music_refresh_interval: int
    autoplay_24_7: bool
    announce_existing_news: bool
    ffmpeg_path: str
    state_file: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Defina DISCORD_TOKEN no arquivo .env ou na hospedagem.")

        site_url = os.environ.get(
            "SITE_URL", "https://carlos-peixoto.vercel.app/"
        ).strip()
        if not site_url.startswith(("http://", "https://")):
            raise RuntimeError("SITE_URL precisa comecar com http:// ou https://.")

        state_value = os.environ.get("BOT_STATE_FILE", "data/state.json").strip()
        state_file = Path(state_value)
        if not state_file.is_absolute():
            state_file = BASE_DIR / state_file

        return cls(
            token=token,
            guild_id=env_int("DISCORD_GUILD_ID"),
            news_channel_id=env_int("NEWS_CHANNEL_ID"),
            voice_channel_id=env_int("VOICE_CHANNEL_ID"),
            site_url=site_url.rstrip("/") + "/",
            news_interval=max(30, env_int("NEWS_CHECK_INTERVAL", 60)),
            music_refresh_interval=max(30, env_int("MUSIC_REFRESH_INTERVAL", 60)),
            autoplay_24_7=env_bool("AUTOPLAY_24_7", True),
            announce_existing_news=env_bool("ANNOUNCE_EXISTING_NEWS"),
            ffmpeg_path=os.environ.get("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg",
            state_file=state_file,
        )


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    thumbnail: str | None
    duration: int | None
    requester: str
    text_channel_id: int
    direct_stream: bool = False
    announce_playback: bool = True


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "duração desconhecida"
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minute:02d}:{second:02d}"
    return f"{minute:d}:{second:02d}"


def canonical_spotify_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in {"spotify.link", "spoti.fi"}:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            url = response.geturl()
        parsed = urlparse(url)

    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[0].lower().startswith("intl-"):
        parts = parts[1:]
    supported = {"track", "album", "playlist", "episode", "show"}
    for index, part in enumerate(parts[:-1]):
        if part.lower() in supported:
            item_id = parts[index + 1].split("?", 1)[0]
            if item_id:
                return f"https://open.spotify.com/{part.lower()}/{item_id}"
    return url


def spotify_search_query(url: str) -> str:
    try:
        canonical_url = canonical_spotify_url(url)
    except Exception as error:
        raise ValueError("Não consegui abrir este link encurtado do Spotify.") from error
    endpoint = "https://open.spotify.com/oembed?" + urlencode({"url": canonical_url})
    request = Request(endpoint, headers={"User-Agent": "BOT-PEIXOTO/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except Exception as error:
        raise ValueError("Não consegui identificar esta música do Spotify.") from error
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("O link do Spotify não informou o título da música.")
    return f"{title} áudio oficial"


def normalize_music_query(query: str) -> str:
    parsed = urlparse(query)
    hostname = (parsed.hostname or "").lower()
    if (
        hostname == "open.spotify.com"
        or hostname.endswith(".spotify.com")
        or hostname in {"spotify.link", "spoti.fi"}
    ):
        return spotify_search_query(query)
    return query


def extract_track(query: str, requester: str, text_channel_id: int) -> Track:
    query = normalize_music_query(query)
    options = {
        "format": "bestaudio/best",
        "default_search": "ytsearch1",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(query, download=False)
    if info and "entries" in info:
        entries = [entry for entry in info.get("entries", []) if entry]
        info = entries[0] if entries else None
    if not info:
        raise ValueError("Nenhuma musica foi encontrada.")

    webpage_url = info.get("webpage_url") or info.get("original_url") or query
    return Track(
        title=info.get("title") or "Faixa sem titulo",
        webpage_url=webpage_url,
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        requester=requester,
        text_channel_id=text_channel_id,
    )


def extract_stream_url(webpage_url: str) -> str:
    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(webpage_url, download=False)
    if info and "entries" in info:
        entries = [entry for entry in info.get("entries", []) if entry]
        info = entries[0] if entries else None
    stream_url = info.get("url") if info else None
    if not stream_url:
        raise ValueError("Nao foi possivel abrir o audio desta musica.")
    return stream_url


def download_track_audio(webpage_url: str) -> tuple[str, Path]:
    working_directory = Path(tempfile.mkdtemp(prefix="bot-peixoto-musica-"))
    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(working_directory / "audio.%(ext)s"),
        "js_runtimes": {"deno": {}, "node": {}},
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(webpage_url, download=True)
            if info and "entries" in info:
                entries = [entry for entry in info.get("entries", []) if entry]
                info = entries[0] if entries else None
            expected = Path(downloader.prepare_filename(info)) if info else None
        if expected and expected.exists():
            return str(expected), working_directory
        candidates = [
            item
            for item in working_directory.iterdir()
            if item.is_file() and item.suffix not in {".part", ".ytdl"}
        ]
        if candidates:
            return str(candidates[0]), working_directory
        raise ValueError("A música foi encontrada, mas o áudio não pôde ser baixado.")
    except Exception:
        shutil.rmtree(working_directory, ignore_errors=True)
        raise


class GuildPlayer:
    def __init__(self, bot: "PeixotoBot", guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: asyncio.Queue[Track] = asyncio.Queue(maxsize=50)
        self.current: Track | None = None
        self.worker = asyncio.create_task(
            self._player_loop(), name=f"player-{guild.id}"
        )

    async def enqueue(self, track: Track) -> int:
        self.queue.put_nowait(track)
        return self.queue.qsize()

    def pending_tracks(self) -> list[Track]:
        return list(self.queue._queue)

    def clear_queue(self) -> None:
        while True:
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def shutdown(self, disconnect: bool = False) -> None:
        self.clear_queue()
        voice = self.guild.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        self.worker.cancel()
        try:
            await self.worker
        except asyncio.CancelledError:
            pass
        if disconnect and voice and voice.is_connected():
            await voice.disconnect(force=True)

    async def _send_now_playing(self, track: Track) -> None:
        channel = self.bot.get_channel(track.text_channel_id)
        if channel is None:
            return
        embed = discord.Embed(
            title="Tocando agora",
            description=f"[{track.title}]({track.webpage_url})",
            color=discord.Color.from_rgb(53, 174, 232),
        )
        embed.add_field(name="Duração", value=format_duration(track.duration))
        embed.add_field(name="Pedido por", value=track.requester)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Nao foi possivel enviar 'Tocando agora' no canal %s", channel)

    async def _send_playback_error(self, track: Track, message: str) -> None:
        channel = self.bot.get_channel(track.text_channel_id)
        if channel is not None:
            try:
                await channel.send(f"Não consegui tocar **{track.title}**: {message}")
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _player_loop(self) -> None:
        while True:
            from_queue = False
            try:
                track = await asyncio.wait_for(self.queue.get(), timeout=3)
                from_queue = True
            except asyncio.TimeoutError:
                if not self.bot.settings.autoplay_24_7:
                    continue
                try:
                    track = await self.bot.next_autoplay_track(self.guild)
                except (DownloadError, ValueError) as error:
                    logger.warning("Musica automatica ignorada: %s", error)
                    await asyncio.sleep(4)
                    continue
                except Exception:
                    logger.exception("Falha ao carregar a programacao automatica")
                    await asyncio.sleep(8)
                    continue
                if track is None:
                    await asyncio.sleep(10)
                    continue

            self.current = track
            temporary_directory: Path | None = None
            try:
                voice = self.guild.voice_client
                if not voice or not voice.is_connected():
                    await self._send_playback_error(
                        track, "o BOT PEIXOTO não está conectado ao canal de voz."
                    )
                    continue

                if track.direct_stream:
                    stream_url = await self.bot.download_uploaded_audio(
                        track.webpage_url
                    )
                else:
                    stream_url, temporary_directory = await asyncio.to_thread(
                        download_track_audio, track.webpage_url
                    )
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(
                        stream_url,
                        executable=self.bot.settings.ffmpeg_path,
                        options="-vn -loglevel warning",
                    ),
                    volume=0.55,
                )
                finished = asyncio.Event()
                playback_error: list[Exception] = []
                loop = asyncio.get_running_loop()

                def after_playback(error: Exception | None) -> None:
                    if error:
                        playback_error.append(error)
                    loop.call_soon_threadsafe(finished.set)

                voice.play(source, after=after_playback)
                if track.announce_playback:
                    await self._send_now_playing(track)
                await finished.wait()
                if playback_error:
                    raise playback_error[0]
            except asyncio.CancelledError:
                raise
            except FileNotFoundError:
                await self._send_playback_error(
                    track, "o FFmpeg não foi encontrado na hospedagem."
                )
            except (DownloadError, ValueError) as error:
                logger.warning("Falha ao preparar musica: %s", error)
                await self._send_playback_error(track, str(error))
            except Exception as error:
                logger.exception("Erro durante a reproducao")
                detail = str(error).strip()
                message = (
                    f"erro técnico: {detail[:220]}"
                    if detail
                    else f"erro técnico do tipo {type(error).__name__}."
                )
                await self._send_playback_error(track, message)
            finally:
                if temporary_directory:
                    shutil.rmtree(temporary_directory, ignore_errors=True)
                self.current = None
                if from_queue:
                    self.queue.task_done()


class PeixotoBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.players: dict[int, GuildPlayer] = {}
        self.http_session: aiohttp.ClientSession | None = None
        self.last_news_id = self._read_last_news_id()
        self.music_items: list[dict[str, Any]] = []
        self.music_index = 0
        self.music_refreshed_at = 0.0
        self.music_lock = asyncio.Lock()
        self.audio_download_lock = asyncio.Lock()
        self.audio_cache_directory = Path(
            tempfile.mkdtemp(prefix="bot-peixoto-programacao-")
        )

    async def setup_hook(self) -> None:
        timeout = aiohttp.ClientTimeout(total=20)
        self.http_session = aiohttp.ClientSession(timeout=timeout)
        self.news_watcher.change_interval(seconds=self.settings.news_interval)
        self.news_watcher.start()
        if self.settings.autoplay_24_7 and self.settings.voice_channel_id:
            self.voice_keeper.start()
        elif self.settings.autoplay_24_7:
            logger.warning(
                "AUTOPLAY_24_7 esta ativo, mas VOICE_CHANNEL_ID nao foi definido"
            )

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("%s comandos sincronizados no servidor configurado", len(synced))
        else:
            synced = await self.tree.sync()
            logger.info("%s comandos globais sincronizados", len(synced))

    async def on_ready(self) -> None:
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="Programação 24h • /tocar",
            )
        )
        logger.info("BOT PEIXOTO conectado como %s", self.user)

    async def close(self) -> None:
        if self.news_watcher.is_running():
            self.news_watcher.cancel()
        if self.voice_keeper.is_running():
            self.voice_keeper.cancel()
        for player in list(self.players.values()):
            await player.shutdown(disconnect=True)
        self.players.clear()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        shutil.rmtree(self.audio_cache_directory, ignore_errors=True)
        await super().close()

    def player_for(self, guild: discord.Guild) -> GuildPlayer:
        player = self.players.get(guild.id)
        if player is None or player.worker.done():
            player = GuildPlayer(self, guild)
            self.players[guild.id] = player
        return player

    async def download_uploaded_audio(self, audio_url: str) -> str:
        if not self.http_session:
            raise ValueError("A conexão do bot com o site ainda não está pronta.")
        cache_name = hashlib.sha256(audio_url.encode("utf-8")).hexdigest() + ".audio"
        destination = self.audio_cache_directory / cache_name
        if destination.exists() and destination.stat().st_size:
            return str(destination)

        async with self.audio_download_lock:
            if destination.exists() and destination.stat().st_size:
                return str(destination)
            temporary = destination.with_suffix(".part")
            downloaded = 0
            total_size: int | None = None
            try:
                with temporary.open("wb") as output:
                    while total_size is None or downloaded < total_size:
                        range_end = downloaded + BOT_AUDIO_CHUNK_SIZE - 1
                        headers = {"Range": f"bytes={downloaded}-{range_end}"}
                        async with self.http_session.get(
                            audio_url, headers=headers
                        ) as response:
                            if response.status not in {200, 206}:
                                response.raise_for_status()
                            payload = await response.read()
                            if not payload:
                                raise ValueError("O site retornou uma parte vazia do áudio.")

                            if response.status == 206:
                                content_range = response.headers.get("Content-Range", "")
                                match = re.fullmatch(
                                    r"bytes (\d+)-(\d+)/(\d+)", content_range
                                )
                                if not match:
                                    raise ValueError("O site retornou uma faixa de áudio inválida.")
                                range_start, range_finish, declared_total = map(
                                    int, match.groups()
                                )
                                if range_start != downloaded:
                                    raise ValueError("As partes do áudio chegaram fora de ordem.")
                                if range_finish - range_start + 1 != len(payload):
                                    raise ValueError("Uma parte do áudio chegou incompleta.")
                                total_size = declared_total
                            else:
                                total_size = len(payload)

                            if total_size > BOT_AUDIO_LIMIT:
                                raise ValueError("O áudio do site ultrapassa o limite de 50 MB.")
                            output.write(payload)
                            downloaded += len(payload)
                            if response.status == 200:
                                break

                if total_size is None or downloaded != total_size:
                    raise ValueError("O download do áudio do site ficou incompleto.")
                temporary.replace(destination)
                return str(destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise

    async def _fetch_music_items(self) -> list[dict[str, Any]]:
        if not self.http_session:
            return []
        api_url = urljoin(self.settings.site_url, "api/musicas")
        async with self.http_session.get(api_url) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
        music = payload.get("music", [])
        return [
            item
            for item in music
            if isinstance(item, dict)
            and item.get("id")
            and (item.get("source_url") or item.get("audio_url"))
        ]

    async def next_autoplay_track(self, guild: discord.Guild) -> Track | None:
        if not self.settings.autoplay_24_7 or not self.settings.voice_channel_id:
            return None
        async with self.music_lock:
            now = time.monotonic()
            if (
                not self.music_items
                or now - self.music_refreshed_at >= self.settings.music_refresh_interval
            ):
                self.music_items = await self._fetch_music_items()
                self.music_refreshed_at = now
                if self.music_items:
                    self.music_index %= len(self.music_items)
                else:
                    self.music_index = 0
            if not self.music_items:
                return None
            item = self.music_items[self.music_index]
            self.music_index = (self.music_index + 1) % len(self.music_items)

        title = str(item.get("title") or "Música da programação")
        if item.get("source_type") == "upload" and item.get("audio_url"):
            return Track(
                title=title,
                webpage_url=urljoin(self.settings.site_url, str(item["audio_url"])),
                thumbnail=None,
                duration=None,
                requester="Programação do Jornal Carlos Peixoto",
                text_channel_id=0,
                direct_stream=True,
                announce_playback=False,
            )

        source_url = str(item.get("source_url") or "")
        track = await asyncio.to_thread(extract_track, source_url, "Programação 24h", 0)
        track.title = title
        track.announce_playback = False
        return track

    async def _configured_voice_channel(self) -> Any | None:
        channel = self.get_channel(self.settings.voice_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.settings.voice_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.exception("Canal de voz 24h nao encontrado ou sem permissao")
                return None
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            logger.error("VOICE_CHANNEL_ID nao corresponde a um canal de voz")
            return None
        return channel

    async def keep_voice_connected(self) -> None:
        channel = await self._configured_voice_channel()
        if channel is None:
            return
        voice = channel.guild.voice_client
        if voice and voice.is_connected():
            if voice.channel != channel:
                await voice.move_to(channel)
        else:
            await channel.connect(self_deaf=True, reconnect=True)
            logger.info("BOT PEIXOTO conectado ao canal de voz 24h: %s", channel)
        self.player_for(channel.guild)

    def _read_last_news_id(self) -> int | None:
        try:
            data = json.loads(self.settings.state_file.read_text(encoding="utf-8"))
            return int(data["last_news_id"])
        except FileNotFoundError:
            return None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Estado de noticias invalido; um novo sera criado")
            return None

    def _save_last_news_id(self, news_id: int) -> None:
        self.settings.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings.state_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"last_news_id": news_id}, indent=2), encoding="utf-8"
        )
        temporary.replace(self.settings.state_file)

    async def _news_channel(self) -> Any | None:
        if not self.settings.news_channel_id:
            return None
        channel = self.get_channel(self.settings.news_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.settings.news_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.exception("Canal de noticias nao encontrado ou sem permissao")
                return None
        return channel

    async def _recover_news_id_from_channel(self, channel: Any) -> int | None:
        if not hasattr(channel, "history"):
            return None
        found: list[int] = []
        try:
            async for message in channel.history(limit=100):
                for embed in message.embeds:
                    footer = embed.footer.text or ""
                    if footer.startswith("JCP-NOTICIA:"):
                        try:
                            found.append(int(footer.split(":", 1)[1]))
                        except ValueError:
                            pass
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Sem permissao para ler o historico do canal de noticias")
        return max(found) if found else None

    async def _fetch_news(self) -> list[dict[str, Any]]:
        if not self.http_session:
            return []
        api_url = urljoin(self.settings.site_url, "api/noticias?limit=50")
        async with self.http_session.get(api_url) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
        news = payload.get("news", [])
        return [item for item in news if isinstance(item, dict) and item.get("id")]

    def _news_embed(self, item: dict[str, Any]) -> discord.Embed:
        article_url = urljoin(self.settings.site_url, str(item.get("url", "")))
        timestamp = None
        try:
            timestamp = datetime.fromisoformat(str(item.get("published_at")))
        except ValueError:
            pass
        embed = discord.Embed(
            title=str(item.get("title", "Nova notícia"))[:256],
            url=article_url,
            description=str(item.get("summary", ""))[:4096],
            color=discord.Color.from_rgb(53, 174, 232),
            timestamp=timestamp,
        )
        embed.set_author(
            name="Nova notícia • Jornal Carlos Peixoto",
            url=self.settings.site_url,
        )
        category = str(item.get("category", "Notícias"))
        embed.add_field(name="Editoria", value=category, inline=True)
        if item.get("source_name"):
            embed.add_field(
                name="Informação fornecida por",
                value=str(item["source_name"])[:1024],
                inline=True,
            )
        image_url = item.get("image_url")
        if image_url:
            embed.set_image(url=urljoin(self.settings.site_url, str(image_url)))
        embed.set_footer(text=f"JCP-NOTICIA:{int(item['id'])}")
        return embed

    async def check_news(self) -> None:
        channel = await self._news_channel()
        if channel is None:
            return
        items = await self._fetch_news()
        if not items:
            return
        newest_id = max(int(item["id"]) for item in items)

        if self.last_news_id is None:
            self.last_news_id = await self._recover_news_id_from_channel(channel)
            if self.last_news_id is None and not self.settings.announce_existing_news:
                self.last_news_id = newest_id
                self._save_last_news_id(newest_id)
                logger.info("Noticias atuais registradas; aguardando a proxima publicacao")
                return
            if self.last_news_id is None:
                self.last_news_id = 0

        new_items = sorted(
            (item for item in items if int(item["id"]) > self.last_news_id),
            key=lambda item: int(item["id"]),
        )
        for item in new_items:
            await channel.send(
                content="📰 **Notícia nova no Jornal Carlos Peixoto!**",
                embed=self._news_embed(item),
            )
            self.last_news_id = int(item["id"])
            self._save_last_news_id(self.last_news_id)
            logger.info("Noticia %s enviada ao Discord", self.last_news_id)

    @tasks.loop(seconds=60.0)
    async def news_watcher(self) -> None:
        try:
            await self.check_news()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha ao verificar noticias; nova tentativa sera feita")

    @news_watcher.before_loop
    async def before_news_watcher(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=30.0)
    async def voice_keeper(self) -> None:
        try:
            await self.keep_voice_connected()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha ao manter o BOT PEIXOTO no canal de voz")

    @voice_keeper.before_loop
    async def before_voice_keeper(self) -> None:
        await self.wait_until_ready()


settings = Settings.from_env()
bot = PeixotoBot(settings)


async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        raise ValueError("Este comando só pode ser usado dentro do servidor.")
    if not interaction.user.voice or not interaction.user.voice.channel:
        raise ValueError("Entre em um canal de voz antes de usar este comando.")

    user_channel = interaction.user.voice.channel
    if (
        bot.settings.autoplay_24_7
        and bot.settings.voice_channel_id
        and user_channel.id != bot.settings.voice_channel_id
    ):
        raise ValueError("Entre no canal de voz da programação 24 horas para pedir músicas.")
    voice = interaction.guild.voice_client
    if voice and voice.is_connected():
        if voice.channel != user_channel:
            await voice.move_to(user_channel)
        return voice
    return await user_channel.connect(self_deaf=True)


def require_same_voice(interaction: discord.Interaction) -> discord.VoiceClient:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        raise ValueError("Este comando só pode ser usado dentro do servidor.")
    voice = interaction.guild.voice_client
    user_voice = interaction.user.voice
    if not voice or not voice.is_connected():
        raise ValueError("O BOT PEIXOTO não está conectado a um canal de voz.")
    if not user_voice or user_voice.channel != voice.channel:
        raise ValueError("Entre no mesmo canal de voz do BOT PEIXOTO.")
    return voice


@bot.tree.command(name="tocar", description="Pesquisa e toca uma música")
@app_commands.describe(busca="Nome da música ou link")
@app_commands.guild_only()
async def play(interaction: discord.Interaction, busca: app_commands.Range[str, 1, 200]):
    await interaction.response.defer(thinking=True)
    try:
        await ensure_voice(interaction)
        if not interaction.guild or not interaction.channel_id:
            raise ValueError("Não foi possível identificar o servidor ou o canal.")
        player = bot.player_for(interaction.guild)
        if player.queue.full():
            raise ValueError("A fila está cheia. Use /parar para limpá-la.")
        track = await asyncio.to_thread(
            extract_track, str(busca), interaction.user.display_name, interaction.channel_id
        )
        position = await player.enqueue(track)
        voice = interaction.guild.voice_client
        if (
            voice
            and player.current
            and not player.current.announce_playback
            and (voice.is_playing() or voice.is_paused())
        ):
            voice.stop()
        await interaction.followup.send(
            f"🎵 **{track.title}** adicionada à fila (posição {position})."
        )
    except (DownloadError, ValueError) as error:
        await interaction.followup.send(f"❌ {error}", ephemeral=True)
    except discord.ClientException as error:
        await interaction.followup.send(f"❌ Não consegui entrar no canal: {error}", ephemeral=True)


@bot.tree.command(name="pausar", description="Pausa a música atual")
@app_commands.guild_only()
async def pause(interaction: discord.Interaction):
    try:
        voice = require_same_voice(interaction)
        if not voice.is_playing():
            raise ValueError("Não existe uma música tocando agora.")
        voice.pause()
        await interaction.response.send_message("⏸️ Música pausada.")
    except ValueError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)


@bot.tree.command(name="continuar", description="Continua a música pausada")
@app_commands.guild_only()
async def resume(interaction: discord.Interaction):
    try:
        voice = require_same_voice(interaction)
        if not voice.is_paused():
            raise ValueError("Não existe uma música pausada agora.")
        voice.resume()
        await interaction.response.send_message("▶️ Música retomada.")
    except ValueError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)


@bot.tree.command(name="pular", description="Pula a música atual")
@app_commands.guild_only()
async def skip(interaction: discord.Interaction):
    try:
        voice = require_same_voice(interaction)
        if not (voice.is_playing() or voice.is_paused()):
            raise ValueError("Não existe uma música para pular.")
        voice.stop()
        await interaction.response.send_message("⏭️ Música pulada.")
    except ValueError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)


@bot.tree.command(name="fila", description="Mostra as músicas da fila")
@app_commands.guild_only()
async def queue(interaction: discord.Interaction):
    if not interaction.guild:
        return
    player = bot.players.get(interaction.guild.id)
    if not player or (not player.current and player.queue.empty()):
        await interaction.response.send_message("A fila está vazia.", ephemeral=True)
        return
    lines = []
    if player.current:
        lines.append(f"**Tocando:** {player.current.title}")
    for index, track in enumerate(player.pending_tracks()[:10], start=1):
        lines.append(f"{index}. {track.title} • {format_duration(track.duration)}")
    remaining = max(0, player.queue.qsize() - 10)
    if remaining:
        lines.append(f"… e mais {remaining} música(s).")
    embed = discord.Embed(
        title="Fila do BOT PEIXOTO",
        description="\n".join(lines),
        color=discord.Color.from_rgb(53, 174, 232),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="parar", description="Para a música e limpa a fila")
@app_commands.guild_only()
async def stop(interaction: discord.Interaction):
    try:
        voice = require_same_voice(interaction)
        player = bot.player_for(interaction.guild)
        player.clear_queue()
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        message = "⏹️ Música parada e fila limpa."
        if bot.settings.autoplay_24_7:
            message += " A programação automática continuará."
        await interaction.response.send_message(message)
    except ValueError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)


@bot.tree.command(name="sair", description="Desconecta o bot do canal de voz")
@app_commands.guild_only()
async def leave(interaction: discord.Interaction):
    try:
        require_same_voice(interaction)
        if not interaction.guild:
            return
        player = bot.players.pop(interaction.guild.id, None)
        if player:
            await player.shutdown(disconnect=True)
        elif interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect(force=True)
        message = "👋 BOT PEIXOTO saiu do canal de voz."
        if bot.settings.autoplay_24_7 and bot.settings.voice_channel_id:
            message += " O modo 24 horas fará a reconexão automática."
        await interaction.response.send_message(message)
    except ValueError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)


@bot.tree.error
async def command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    logger.error(
        "Erro em comando do Discord: %s",
        error,
        exc_info=(type(error), error, error.__traceback__),
    )
    message = "❌ O comando não pôde ser concluído. Tente novamente."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    bot.run(settings.token, log_handler=None)
