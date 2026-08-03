import os
import math
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from flask import (Flask, Response, abort, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import defer
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_AUDIO_SIZE = 50 * 1024 * 1024
AUDIO_UPLOAD_CHUNK_SIZE = 3 * 1024 * 1024
AUDIO_RESPONSE_CHUNK_SIZE = 3 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "m4a", "ogg", "opus", "wav", "webm", "aac", "flac"}
ALLOWED_AUDIO_MIMETYPES = {
    "audio/aac",
    "audio/flac",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/opus",
    "audio/wav",
    "audio/webm",
    "audio/x-wav",
    "application/ogg",
}
CATEGORIES = ["Polícia", "Médicos", "Bombeiros", "Juiz", "Advogado", "Jornalista"]
CATEGORY_SLUGS = {
    "policia": "Polícia",
    "medicos": "Médicos",
    "bombeiros": "Bombeiros",
    "juiz": "Juiz",
    "advogado": "Advogado",
    "jornalista": "Jornalista",
}
CATEGORY_TO_SLUG = {name: slug for slug, name in CATEGORY_SLUGS.items()}
BAHIA_TIMEZONE = timezone(timedelta(hours=-3))


def database_uri():
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        return f"sqlite:///{(BASE_DIR / 'jornal.db').as_posix()}"
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "somente-desenvolvimento-local"),
    SQLALCHEMY_DATABASE_URI=database_uri(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
)
db = SQLAlchemy(app)


def utc_now():
    return datetime.now(timezone.utc)


class News(db.Model):
    __tablename__ = "news"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(350), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    source_name = db.Column(db.String(120))
    source_image_mimetype = db.Column(db.String(80))
    source_image_data = db.Column(db.LargeBinary)
    image = db.Column(db.String(255))
    image_mimetype = db.Column(db.String(80))
    image_data = db.Column(db.LargeBinary)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    comments = db.relationship("Comment", back_populates="article", cascade="all, delete-orphan")


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    news_id = db.Column(db.Integer, db.ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True)
    author = db.Column(db.String(80), nullable=False)
    content = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    article = db.relationship("News", back_populates="comments")


class Professional(db.Model):
    __tablename__ = "professionals"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer)
    role = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(250))
    hours = db.Column(db.String(250))
    sections = db.Column(db.Text, nullable=False)
    image_mimetype = db.Column(db.String(80))
    image_data = db.Column(db.LargeBinary)
    office_image_mimetype = db.Column(db.String(80))
    office_image_data = db.Column(db.LargeBinary)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    featured_reason = db.Column(db.String(300))


class MusicTrack(db.Model):
    __tablename__ = "music_tracks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    source_url = db.Column(db.String(1000))
    audio_filename = db.Column(db.String(255))
    audio_mimetype = db.Column(db.String(100))
    audio_data = db.Column(db.LargeBinary)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MusicUploadChunk(db.Model):
    __tablename__ = "music_upload_chunks"
    __table_args__ = (
        db.UniqueConstraint("upload_token", "chunk_index", name="uq_music_upload_chunk"),
    )

    id = db.Column(db.Integer, primary_key=True)
    upload_token = db.Column(db.String(36), nullable=False, index=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    total_chunks = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True)
    visitor_name = db.Column(db.String(80))
    title = db.Column(db.String(140))
    description = db.Column(db.String(600))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, index=True)
    messages = db.relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.String(36),
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender = db.Column(db.String(10), nullable=False)
    content = db.Column(db.String(2000), nullable=False)
    read_by_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    conversation = db.relationship("Conversation", back_populates="messages")
    attachments = db.relationship(
        "ChatAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ChatAttachment.id",
    )


class ChatAttachment(db.Model):
    __tablename__ = "chat_attachments"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = db.Column(db.String(255), nullable=False)
    image_mimetype = db.Column(db.String(80), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=False)
    message = db.relationship("ChatMessage", back_populates="attachments")


def seed_database():
    if db.session.scalar(db.select(func.count(News.id))):
        return

    db.session.add_all([
        News(title="Mutirão de serviços reúne moradores neste sábado", summary="Ação comunitária oferece orientação, saúde preventiva e atividades culturais.", content="A comunidade recebe neste sábado uma programação gratuita com serviços de orientação, cuidados preventivos e atividades para toda a família. A iniciativa reúne profissionais e voluntários locais.\n\nOs atendimentos serão realizados por ordem de chegada. A organização recomenda levar documento de identificação e comprovante de residência.", category="Jornalista", featured=True),
        News(title="Operação reforça segurança em áreas comerciais", summary="Equipes ampliam rondas e ações educativas no centro.", content="A operação começou nesta semana e inclui rondas em horários de maior movimento. Comerciantes também recebem orientações sobre prevenção e canais de atendimento.", category="Polícia"),
        News(title="Nova clínica amplia atendimento preventivo", summary="Espaço terá consultas agendadas e ações de conscientização.", content="A nova unidade inicia os atendimentos na próxima segunda-feira. Entre os serviços estão consultas, acompanhamento preventivo e palestras abertas à comunidade.", category="Médicos"),
        News(title="Bombeiros promovem campanha contra acidentes domésticos", summary="Ação ensina cuidados com eletricidade, gás e primeiros socorros.", content="A campanha reúne recomendações práticas para reduzir riscos dentro de casa e informa quando acionar o atendimento de emergência.", category="Bombeiros"),
        News(title="Projeto aproxima o Judiciário da comunidade", summary="Encontros explicam direitos e serviços disponíveis.", content="O projeto promove rodas de conversa em linguagem acessível, com foco em cidadania, direitos e formas de acesso aos serviços públicos.", category="Juiz"),
        News(title="Orientação jurídica gratuita atende moradores", summary="Profissionais explicam procedimentos e encaminham demandas.", content="A atividade oferece informações jurídicas gerais e encaminhamento aos órgãos adequados. O atendimento não substitui consulta individual quando necessária.", category="Advogado"),
    ])
    db.session.add_all([
        Professional(category="Polícia", name="Marina Almeida", age=38, role="Delegada de Polícia", hours="Segunda a sexta, 8h às 17h", sections="Lista de procurados|Pessoas desaparecidas|Lista de presos|Orientações de segurança"),
        Professional(category="Médicos", name="Dr. Rafael Santos", age=44, role="Médico clínico geral", address="Av. Central, 250 — Centro", hours="Segunda a sexta, 7h às 18h", sections="Inauguração de consultório ou clínica|Serviços oferecidos|Entrevistas e artigos|Agenda de atendimento"),
        Professional(category="Bombeiros", name="Camila Ferreira", age=35, role="Capitã do Corpo de Bombeiros", hours="Plantão 24 horas", sections="Incêndios combatidos|Desaparecimentos|Pessoas salvas|Prevenção e primeiros socorros"),
        Professional(category="Juiz", name="Dr. André Ribeiro", age=49, role="Juiz de Direito", hours="Segunda a sexta, 9h às 16h", sections="Campanhas de conscientização|Ações e projetos do Poder Judiciário|Entrevistas sobre temas jurídicos"),
        Professional(category="Advogado", name="Paula Nascimento", age=41, role="Advogada", address="Rua das Palmeiras, 90 — Sala 4", hours="Segunda a sexta, 8h às 17h", sections="Inauguração ou ampliação do escritório|Serviços oferecidos|Informações objetivas ao cidadão"),
        Professional(category="Jornalista", name="Carlos Peixoto", age=35, role="Jornalista e editor responsável", hours="Contato editorial: segunda a sexta, 9h às 18h", sections="Reportagens e entrevistas exclusivas|Economia, política, educação, saúde, cultura e esportes|Investigações jornalísticas|Projetos jornalísticos e vídeos|Campanhas solidárias e utilidade pública|Reportagens, assessoria, fotografia e produção de conteúdo para empresas"),
    ])
    db.session.commit()


def migrate_legacy_sqlite():
    """Atualiza automaticamente o banco local criado pela primeira versão."""
    if db.engine.dialect.name != "sqlite" or "news" not in inspect(db.engine).get_table_names():
        return
    columns = {column["name"] for column in inspect(db.engine).get_columns("news")}
    additions = {
        "image_mimetype": "VARCHAR(80)",
        "image_data": "BLOB",
    }
    with db.engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE news ADD COLUMN {name} {definition}"))

    legacy_uploads = BASE_DIR / "uploads"
    if legacy_uploads.exists():
        articles = db.session.execute(
            db.select(News).where(News.image.is_not(None), News.image_data.is_(None))
        ).scalars().all()
        for article in articles:
            path = legacy_uploads / article.image
            if path.is_file():
                article.image_data = path.read_bytes()
                extension = path.suffix.lower().lstrip(".")
                article.image_mimetype = "image/jpeg" if extension in {"jpg", "jpeg"} else f"image/{extension}"
        db.session.commit()


def migrate_professional_images():
    """Adiciona os campos de foto nos bancos criados por versões anteriores."""
    inspector = inspect(db.engine)
    if "professionals" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("professionals")}
    binary_type = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
    boolean_type = (
        "BOOLEAN NOT NULL DEFAULT FALSE"
        if db.engine.dialect.name == "postgresql"
        else "BOOLEAN NOT NULL DEFAULT 0"
    )
    additions = {
        "image_mimetype": "VARCHAR(80)",
        "image_data": binary_type,
        "office_image_mimetype": "VARCHAR(80)",
        "office_image_data": binary_type,
        "featured": boolean_type,
        "featured_reason": "VARCHAR(300)",
    }

    with db.engine.begin() as connection:
        for name, definition in additions.items():
            if name in columns:
                continue
            if db.engine.dialect.name == "postgresql":
                connection.execute(
                    text(f"ALTER TABLE professionals ADD COLUMN IF NOT EXISTS {name} {definition}")
                )
            else:
                connection.execute(
                    text(f"ALTER TABLE professionals ADD COLUMN {name} {definition}")
                )


def migrate_news_source_name():
    """Adiciona o crédito da fonte às notícias dos bancos já existentes."""
    inspector = inspect(db.engine)
    if "news" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("news")}
    binary_type = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
    additions = {
        "source_name": "VARCHAR(120)",
        "source_image_mimetype": "VARCHAR(80)",
        "source_image_data": binary_type,
    }
    with db.engine.begin() as connection:
        for name, definition in additions.items():
            if name in columns:
                continue
            if db.engine.dialect.name == "postgresql":
                connection.execute(
                    text(f"ALTER TABLE news ADD COLUMN IF NOT EXISTS {name} {definition}")
                )
            else:
                connection.execute(text(f"ALTER TABLE news ADD COLUMN {name} {definition}"))


def migrate_conversation_details():
    """Adiciona título e descrição às conversas criadas por versões anteriores."""
    inspector = inspect(db.engine)
    if "conversations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("conversations")}
    additions = {
        "title": "VARCHAR(140)",
        "description": "VARCHAR(600)",
    }
    with db.engine.begin() as connection:
        for name, definition in additions.items():
            if name in columns:
                continue
            if db.engine.dialect.name == "postgresql":
                connection.execute(
                    text(f"ALTER TABLE conversations ADD COLUMN IF NOT EXISTS {name} {definition}")
                )
            else:
                connection.execute(
                    text(f"ALTER TABLE conversations ADD COLUMN {name} {definition}")
                )


def save_image(file):
    if not file or not file.filename:
        return None
    original = secure_filename(file.filename)
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato inválido. Use PNG, JPG, JPEG, WEBP ou GIF.")
    data = file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise ValueError("A imagem ultrapassa o limite de 8 MB.")
    return {
        "image": f"{uuid4().hex}.{extension}",
        "image_mimetype": file.mimetype or f"image/{extension}",
        "image_data": data,
    }


def validate_audio_metadata(filename, mimetype):
    original = secure_filename(filename or "")
    if not original:
        raise ValueError("O arquivo de áudio precisa ter um nome válido.")
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError(
            "Formato inválido. Use MP3, M4A, OGG, OPUS, WAV, WEBM, AAC ou FLAC."
        )
    if (
        mimetype
        and mimetype != "application/octet-stream"
        and mimetype not in ALLOWED_AUDIO_MIMETYPES
    ):
        raise ValueError("O arquivo enviado não foi reconhecido como áudio.")
    return original


def save_audio(file):
    if not file or not file.filename:
        return None
    original = validate_audio_metadata(file.filename, file.mimetype)
    data = file.read(MAX_AUDIO_SIZE + 1)
    if len(data) > MAX_AUDIO_SIZE:
        raise ValueError("O áudio ultrapassa o limite de 50 MB.")
    return {
        "audio_filename": original,
        "audio_mimetype": file.mimetype or "application/octet-stream",
        "audio_data": data,
    }


def normalized_upload_token(value):
    try:
        return str(UUID((value or "").strip()))
    except (AttributeError, ValueError) as error:
        raise ValueError("O identificador do envio de áudio é inválido.") from error


def consume_audio_upload(upload_token):
    token = normalized_upload_token(upload_token)
    chunks = db.session.execute(
        db.select(MusicUploadChunk)
        .where(MusicUploadChunk.upload_token == token)
        .order_by(MusicUploadChunk.chunk_index.asc())
    ).scalars().all()
    if not chunks:
        raise ValueError("O envio do áudio não foi encontrado. Selecione o arquivo novamente.")

    total_chunks = chunks[0].total_chunks
    expected_indexes = list(range(total_chunks))
    if len(chunks) != total_chunks or [item.chunk_index for item in chunks] != expected_indexes:
        raise ValueError("O envio do áudio ficou incompleto. Selecione o arquivo novamente.")
    if any(
        item.total_chunks != total_chunks
        or item.filename != chunks[0].filename
        or item.mimetype != chunks[0].mimetype
        for item in chunks
    ):
        raise ValueError("As partes do áudio não correspondem ao mesmo arquivo.")

    original = validate_audio_metadata(chunks[0].filename, chunks[0].mimetype)
    size = sum(len(item.data) for item in chunks)
    if size > MAX_AUDIO_SIZE:
        raise ValueError("O áudio ultrapassa o limite de 50 MB.")
    if size == 0:
        raise ValueError("O arquivo de áudio está vazio.")

    data = b"".join(item.data for item in chunks)
    for item in chunks:
        db.session.delete(item)
    return {
        "audio_filename": original,
        "audio_mimetype": chunks[0].mimetype or "application/octet-stream",
        "audio_data": data,
    }


def valid_music_url(value):
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def save_chat_attachments(files):
    photos = [photo for photo in files if photo and photo.filename]
    if len(photos) > 3:
        raise ValueError("Envie no máximo 3 fotos por mensagem.")

    attachments = []
    total_size = 0
    for photo in photos:
        saved = save_image(photo)
        total_size += len(saved["image_data"])
        if total_size > MAX_IMAGE_SIZE:
            raise ValueError("As fotos juntas ultrapassam o limite de 8 MB.")
        attachments.append({
            "filename": saved["image"],
            "image_mimetype": saved["image_mimetype"],
            "image_data": saved["image_data"],
        })
    return attachments


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            flash("Entre no painel para continuar.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        if not session.get("admin_token"):
            session["admin_token"] = uuid4().hex
        return view(*args, **kwargs)
    return wrapped


def get_visitor_conversation():
    conversation_id = session.get("chat_id")
    conversation = db.session.get(Conversation, conversation_id) if conversation_id else None
    if conversation is None:
        conversation_id = str(uuid4())
        conversation = Conversation(id=conversation_id)
        db.session.add(conversation)
        db.session.commit()
        session["chat_id"] = conversation_id
    return conversation


@app.context_processor
def globals_for_templates():
    return {
        "categories": CATEGORIES,
        "category_links": [{"name": name, "slug": CATEGORY_TO_SLUG[name]} for name in CATEGORIES],
        "category_slug": CATEGORY_TO_SLUG,
        "current_year": datetime.now().year,
    }


@app.template_filter("datetime_br")
def datetime_br(value):
    if not value:
        return "Sem atualização"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BAHIA_TIMEZONE).strftime("%d/%m/%Y às %H:%M")


@app.route("/")
def index():
    featured = db.session.execute(db.select(News).order_by(News.featured.desc(), News.created_at.desc()).limit(1)).scalar_one_or_none()
    news = db.session.execute(db.select(News).order_by(News.created_at.desc()).limit(9)).scalars().all()
    journalist = db.session.execute(
        db.select(Professional)
        .where(Professional.category == "Jornalista")
        .order_by(Professional.featured.desc(), Professional.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    return render_template("index.html", featured=featured, news=news, journalist=journalist)


@app.route("/api/noticias")
def news_api():
    """Lista publica e resumida usada pelo BOT PEIXOTO."""
    limit = request.args.get("limit", default=20, type=int) or 20
    limit = max(1, min(limit, 50))
    items = db.session.execute(
        db.select(News).order_by(News.id.desc()).limit(limit)
    ).scalars().all()
    response = jsonify(
        {
            "site": url_for("index"),
            "news": [
                {
                    "id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "category": item.category,
                    "source_name": item.source_name,
                    "published_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                    "url": url_for("news_detail", news_id=item.id),
                    "image_url": (
                        url_for("uploaded_file", news_id=item.id)
                        if item.image_data
                        else url_for("static", filename="img/icone.png")
                    ),
                }
                for item in items
            ],
        }
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/api/musicas")
def music_api():
    items = db.session.execute(
        db.select(MusicTrack)
        .options(defer(MusicTrack.audio_data))
        .where(MusicTrack.enabled.is_(True))
        .order_by(MusicTrack.position.asc(), MusicTrack.id.asc())
    ).scalars().all()
    response = jsonify(
        {
            "site": url_for("index"),
            "music": [
                {
                    "id": item.id,
                    "title": item.title,
                    "source_type": "upload" if item.audio_filename else "link",
                    "source_url": item.source_url,
                    "audio_url": (
                        url_for(
                            "music_audio",
                            music_id=item.id,
                            v=int(item.updated_at.timestamp()),
                        )
                        if item.audio_filename
                        else None
                    ),
                    "position": item.position,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in items
            ],
        }
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/categoria/<slug>")
def category(slug):
    category_name = CATEGORY_SLUGS.get(slug.lower())
    if category_name is None and slug in CATEGORIES:
        category_name = slug
    if category_name is None:
        abort(404)
    professionals = db.session.execute(
        db.select(Professional)
        .where(Professional.category == category_name)
        .order_by(Professional.featured.desc(), Professional.name.asc())
    ).scalars().all()
    news = db.session.execute(db.select(News).where(News.category == category_name).order_by(News.created_at.desc())).scalars().all()
    return render_template("category.html", category=category_name, professionals=professionals, news=news)


@app.route("/noticia/<int:news_id>", methods=["GET", "POST"])
def news_detail(news_id):
    article = db.get_or_404(News, news_id)
    if request.method == "POST":
        author = request.form.get("author", "").strip()
        content = request.form.get("content", "").strip()
        if not author or not content:
            flash("Informe seu nome e escreva um comentário.", "error")
        elif len(author) > 80 or len(content) > 1000:
            flash("Comentário muito longo.", "error")
        else:
            db.session.add(Comment(news_id=news_id, author=author, content=content))
            db.session.commit()
            flash("Comentário publicado.", "success")
            return redirect(url_for("news_detail", news_id=news_id) + "#comentarios")
    comments = db.session.execute(db.select(Comment).where(Comment.news_id == news_id).order_by(Comment.created_at.desc())).scalars().all()
    return render_template("news_detail.html", article=article, comments=comments)


@app.route("/contato", methods=["GET", "POST"])
def visitor_chat():
    conversation = get_visitor_conversation()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        content = request.form.get("content", "").strip()
        if not name or not title or not description or not content:
            flash("Preencha seu nome, título, descrição e mensagem.", "error")
        elif len(name) > 80 or len(title) > 140 or len(description) > 600 or len(content) > 2000:
            flash("Um dos campos ultrapassa o limite permitido.", "error")
        else:
            try:
                attachment_values = save_chat_attachments(request.files.getlist("photos"))
            except ValueError as error:
                flash(str(error), "error")
                return render_template("chat.html", conversation=conversation)
            conversation.visitor_name = name
            conversation.title = title
            conversation.description = description
            conversation.updated_at = utc_now()
            message = ChatMessage(conversation_id=conversation.id, sender="visitor", content=content)
            for values in attachment_values:
                message.attachments.append(ChatAttachment(**values))
            db.session.add(message)
            db.session.commit()
            flash("Mensagem enviada somente ao administrador.", "success")
            return redirect(url_for("visitor_chat") + "#mensagens")
    return render_template("chat.html", conversation=conversation)


@app.route("/admin/entrar", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        expected = os.environ.get("ADMIN_PASSWORD")
        if not expected:
            app.logger.error("ADMIN_PASSWORD não foi configurada.")
            flash("O acesso administrativo ainda não foi configurado.", "error")
            return render_template("admin/login.html"), 503
        if request.form.get("password") == expected:
            session["admin"] = True
            session["admin_token"] = uuid4().hex
            session.permanent = False
            flash("Acesso liberado.", "success")
            target = request.args.get("next", "")
            if not target.startswith("/admin") or target.startswith("//"):
                target = url_for("admin_dashboard")
            separator = "&" if "?" in target else "?"
            return redirect(f"{target}{separator}login=1")
        flash("Senha incorreta.", "error")
    return render_template("admin/login.html")


@app.route("/admin/sair")
def admin_logout():
    session.pop("admin", None)
    session.pop("admin_token", None)
    if request.args.get("relogin"):
        flash("A sessão anterior foi encerrada. Digite a senha novamente.", "warning")
        return redirect(url_for("admin_login"))
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    category_sections = []
    for category_name in CATEGORIES:
        items = db.session.execute(db.select(News).where(News.category == category_name).order_by(News.updated_at.desc(), News.created_at.desc())).scalars().all()
        category_sections.append({"name": category_name, "news_items": items, "last_updated": items[0].updated_at if items else None})
    unread_messages = db.session.scalar(db.select(func.count(ChatMessage.id)).where(ChatMessage.sender == "visitor", ChatMessage.read_by_admin.is_(False))) or 0
    return render_template("admin/dashboard.html", category_sections=category_sections, unread_messages=unread_messages)


@app.route("/admin/conversas")
@admin_required
def admin_conversations():
    conversations = db.session.execute(db.select(Conversation).order_by(Conversation.updated_at.desc())).scalars().all()
    return render_template("admin/conversations.html", conversations=conversations)


@app.route("/admin/conversa/<conversation_id>/excluir", methods=["POST"])
@admin_required
def admin_conversation_delete(conversation_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    db.session.delete(conversation)
    db.session.commit()
    flash("Conversa excluída.", "success")
    return redirect(url_for("admin_conversations"))


@app.route("/admin/profissionais")
@admin_required
def admin_professionals():
    professionals = db.session.execute(db.select(Professional)).scalars().all()
    ordered_professionals = sorted(
        professionals,
        key=lambda item: (
            CATEGORIES.index(item.category),
            not item.featured,
            item.name.lower(),
        ),
    )
    return render_template(
        "admin/professionals.html", professionals=ordered_professionals
    )


@app.route("/admin/musicas")
@admin_required
def admin_music():
    tracks = db.session.execute(
        db.select(MusicTrack)
        .options(defer(MusicTrack.audio_data))
        .order_by(MusicTrack.position.asc(), MusicTrack.id.asc())
    ).scalars().all()
    return render_template("admin/music.html", tracks=tracks)


def music_form_values(track=None):
    title = request.form.get("title", "").strip()
    source_url = request.form.get("source_url", "").strip()
    upload_token = request.form.get("uploaded_audio_token", "").strip()
    direct_audio = request.files.get("audio")
    position_text = request.form.get("position", "0").strip() or "0"
    enabled = request.form.get("enabled") == "on"
    try:
        position = int(position_text)
    except ValueError as error:
        raise ValueError("Informe uma ordem válida para a música.") from error

    if not title:
        raise ValueError("Informe o título da música.")
    if len(title) > 180 or len(source_url) > 1000:
        raise ValueError("O título ou o link ultrapassa o limite permitido.")
    if not 0 <= position <= 9999:
        raise ValueError("A ordem deve ficar entre 0 e 9999.")
    if source_url and not valid_music_url(source_url):
        raise ValueError("Informe um link começando com http:// ou https://.")

    if upload_token and direct_audio and direct_audio.filename:
        raise ValueError("O formulário recebeu o mesmo áudio de duas formas.")
    if source_url and (upload_token or (direct_audio and direct_audio.filename)):
        raise ValueError("Escolha somente uma fonte: link ou arquivo de áudio.")
    saved_audio = (
        consume_audio_upload(upload_token)
        if upload_token
        else save_audio(direct_audio)
    )

    values = {
        "title": title,
        "position": position,
        "enabled": enabled,
    }
    if saved_audio:
        values.update(saved_audio)
        values["source_url"] = None
    elif source_url:
        values.update(
            {
                "source_url": source_url,
                "audio_filename": None,
                "audio_mimetype": None,
                "audio_data": None,
            }
        )
    elif not track or not track.audio_data:
        raise ValueError("Envie um arquivo de áudio ou informe um link de música.")
    return values


@app.route("/admin/musica/upload/chunk", methods=["POST"])
@admin_required
def admin_music_upload_chunk():
    try:
        token = normalized_upload_token(request.form.get("upload_token"))
        chunk_index = int(request.form.get("chunk_index", ""))
        total_chunks = int(request.form.get("total_chunks", ""))
        filename = validate_audio_metadata(
            request.form.get("filename", ""),
            request.form.get("mimetype", "").strip(),
        )
        mimetype = request.form.get("mimetype", "").strip() or "application/octet-stream"
        chunk_file = request.files.get("chunk")

        maximum_chunks = math.ceil(MAX_AUDIO_SIZE / AUDIO_UPLOAD_CHUNK_SIZE)
        if not 1 <= total_chunks <= maximum_chunks:
            raise ValueError("A quantidade de partes do áudio é inválida.")
        if not 0 <= chunk_index < total_chunks:
            raise ValueError("A posição da parte do áudio é inválida.")
        if not chunk_file:
            raise ValueError("Uma parte do áudio não foi recebida.")

        data = chunk_file.read(AUDIO_UPLOAD_CHUNK_SIZE + 1)
        if not data:
            raise ValueError("Uma parte vazia do áudio foi recebida.")
        if len(data) > AUDIO_UPLOAD_CHUNK_SIZE:
            raise ValueError("Uma parte do áudio ultrapassou o tamanho permitido.")

        stale_before = utc_now() - timedelta(hours=2)
        stale_chunks = db.session.execute(
            db.select(MusicUploadChunk).where(
                MusicUploadChunk.created_at < stale_before
            )
        ).scalars().all()
        for stale in stale_chunks:
            db.session.delete(stale)

        if chunk_index == 0:
            previous_chunks = db.session.execute(
                db.select(MusicUploadChunk).where(
                    MusicUploadChunk.upload_token == token
                )
            ).scalars().all()
            for previous in previous_chunks:
                db.session.delete(previous)
            db.session.flush()
            existing = None
        else:
            existing = db.session.execute(
                db.select(MusicUploadChunk).where(
                    MusicUploadChunk.upload_token == token,
                    MusicUploadChunk.chunk_index == chunk_index,
                )
            ).scalar_one_or_none()

        if existing:
            existing.total_chunks = total_chunks
            existing.filename = filename
            existing.mimetype = mimetype
            existing.data = data
            existing.created_at = utc_now()
        else:
            db.session.add(
                MusicUploadChunk(
                    upload_token=token,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    filename=filename,
                    mimetype=mimetype,
                    data=data,
                )
            )
        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "received": chunk_index + 1,
                "total": total_chunks,
            }
        )
    except (TypeError, ValueError) as error:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(error)}), 400


@app.route("/admin/musica/nova", methods=["GET", "POST"])
@admin_required
def admin_music_create():
    if request.method == "POST":
        try:
            db.session.add(MusicTrack(**music_form_values()))
            db.session.commit()
            flash("Música adicionada à programação do BOT PEIXOTO.", "success")
            return redirect(url_for("admin_music"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/music_form.html", track=None)


@app.route("/admin/musica/<int:music_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_music_edit(music_id):
    track = db.get_or_404(MusicTrack, music_id)
    if request.method == "POST":
        try:
            for key, value in music_form_values(track).items():
                setattr(track, key, value)
            db.session.commit()
            flash("Programação musical atualizada.", "success")
            return redirect(url_for("admin_music"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/music_form.html", track=track)


@app.route("/admin/musica/<int:music_id>/excluir", methods=["POST"])
@admin_required
def admin_music_delete(music_id):
    track = db.get_or_404(MusicTrack, music_id)
    title = track.title
    db.session.delete(track)
    db.session.commit()
    flash(f"Música '{title}' excluída da programação.", "success")
    return redirect(url_for("admin_music"))


def professional_form_values():
    category_name = request.form.get("category", "").strip()
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "").strip()
    address = request.form.get("address", "").strip()
    hours = request.form.get("hours", "").strip()
    age_text = request.form.get("age", "").strip()
    featured_choice = request.form.get("featured_choice", "normal")
    if featured_choice not in {"normal", "featured"}:
        raise ValueError("Escolha uma opção válida para o destaque.")
    featured = featured_choice == "featured"
    featured_reason = request.form.get("featured_reason", "").strip()
    section_lines = [
        line.strip()
        for line in request.form.get("sections", "").splitlines()
        if line.strip()
    ]

    try:
        age = int(age_text)
    except ValueError as error:
        raise ValueError("Informe uma idade válida entre 18 e 120 anos.") from error

    if category_name not in CATEGORIES:
        raise ValueError("Escolha uma editoria válida.")
    if not name or not role or not hours or not section_lines:
        raise ValueError("Preencha nome, função, horário e pelo menos um serviço.")
    if not 18 <= age <= 120:
        raise ValueError("Informe uma idade válida entre 18 e 120 anos.")
    if len(name) > 120 or len(role) > 150 or len(address) > 250 or len(hours) > 250:
        raise ValueError("Um dos campos ultrapassa o limite permitido.")
    if any(len(section) > 180 for section in section_lines):
        raise ValueError("Cada informação ou serviço deve ter no máximo 180 caracteres.")

    if featured and not featured_reason:
        raise ValueError("Explique no que este profissional se destacou.")
    if len(featured_reason) > 300:
        raise ValueError("O motivo do destaque deve ter no maximo 300 caracteres.")

    return {
        "category": category_name,
        "name": name,
        "age": age,
        "role": role,
        "address": address or None,
        "hours": hours,
        "sections": "|".join(section_lines),
        "featured": featured,
        "featured_reason": featured_reason if featured else None,
    }


def clear_featured_professionals(category_name, keep_id=None):
    statement = db.select(Professional).where(
        Professional.category == category_name,
        Professional.featured.is_(True),
    )
    if keep_id is not None:
        statement = statement.where(Professional.id != keep_id)
    for professional in db.session.execute(statement).scalars():
        professional.featured = False
        professional.featured_reason = None


def professional_photo_values():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return None
    saved = save_image(photo)
    return {
        "image_mimetype": saved["image_mimetype"],
        "image_data": saved["image_data"],
    }


def professional_office_photo_values():
    photo = request.files.get("office_photo")
    if not photo or not photo.filename:
        return None
    saved = save_image(photo)
    return {
        "office_image_mimetype": saved["image_mimetype"],
        "office_image_data": saved["image_data"],
    }


@app.route("/admin/profissional/novo", methods=["GET", "POST"])
@admin_required
def admin_professional_create():
    if request.method == "POST":
        try:
            professional = Professional(**professional_form_values())
            if professional.featured:
                clear_featured_professionals(professional.category)
            photo_values = professional_photo_values()
            if photo_values:
                for key, value in photo_values.items():
                    setattr(professional, key, value)
            office_photo_values = professional_office_photo_values()
            if office_photo_values:
                for key, value in office_photo_values.items():
                    setattr(professional, key, value)
            db.session.add(professional)
            db.session.commit()
            flash("Novo profissional cadastrado.", "success")
            return redirect(url_for("admin_professionals"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/professional_form.html", professional=None)


@app.route("/admin/profissional/<int:professional_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_professional_edit(professional_id):
    professional = db.get_or_404(Professional, professional_id)
    if request.method == "POST":
        try:
            form_values = professional_form_values()
            for key, value in form_values.items():
                setattr(professional, key, value)
            if professional.featured:
                clear_featured_professionals(
                    professional.category, keep_id=professional.id
                )
            photo_values = professional_photo_values()
            if photo_values:
                for key, value in photo_values.items():
                    setattr(professional, key, value)
            elif request.form.get("remove_photo"):
                professional.image_mimetype = None
                professional.image_data = None
            office_photo_values = professional_office_photo_values()
            if office_photo_values:
                for key, value in office_photo_values.items():
                    setattr(professional, key, value)
            elif request.form.get("remove_office_photo"):
                professional.office_image_mimetype = None
                professional.office_image_data = None
            db.session.commit()
            flash(f"Perfil de {professional.category} atualizado.", "success")
            return redirect(url_for("admin_professionals"))
        except ValueError as error:
            flash(str(error), "error")

    return render_template(
        "admin/professional_form.html", professional=professional
    )


@app.route("/admin/profissional/<int:professional_id>/excluir", methods=["POST"])
@admin_required
def admin_professional_delete(professional_id):
    professional = db.get_or_404(Professional, professional_id)
    name = professional.name
    db.session.delete(professional)
    db.session.commit()
    flash(f"Cadastro de {name} excluído.", "success")
    return redirect(url_for("admin_professionals"))


@app.route("/admin/conversa/<conversation_id>", methods=["GET", "POST"])
@admin_required
def admin_conversation(conversation_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if not content:
            flash("Escreva uma resposta.", "error")
        elif len(content) > 2000:
            flash("A resposta ultrapassa o limite permitido.", "error")
        else:
            conversation.updated_at = utc_now()
            db.session.add(ChatMessage(conversation_id=conversation.id, sender="admin", content=content, read_by_admin=True))
            db.session.commit()
            flash("Resposta enviada.", "success")
            return redirect(url_for("admin_conversation", conversation_id=conversation.id) + "#mensagens")
    changed = False
    for message in conversation.messages:
        if message.sender == "visitor" and not message.read_by_admin:
            message.read_by_admin = True
            changed = True
    if changed:
        db.session.commit()
    return render_template("admin/conversation.html", conversation=conversation)


@app.route(
    "/admin/conversa/<conversation_id>/mensagem/<int:message_id>/excluir",
    methods=["POST"],
)
@admin_required
def admin_chat_message_delete(conversation_id, message_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    message = db.get_or_404(ChatMessage, message_id)
    if message.conversation_id != conversation.id:
        abort(404)

    db.session.delete(message)
    conversation.updated_at = utc_now()
    db.session.commit()
    flash("Mensagem excluída.", "success")
    return redirect(url_for("admin_conversation", conversation_id=conversation.id))


def news_form_values_legacy():
    title = request.form.get("title", "").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    category_name = request.form.get("category", "")
    if not title or not summary or not content or category_name not in CATEGORIES:
        raise ValueError("Preencha título, resumo, texto e escolha uma categoria válida.")
    if len(title) > 180 or len(summary) > 350:
        raise ValueError("Título ou resumo ultrapassa o limite permitido.")
    return {"title": title, "summary": summary, "content": content, "category": category_name, "featured": bool(request.form.get("featured"))}


def news_form_values():
    title = request.form.get("title", "").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    source_name = request.form.get("source_name", "").strip()
    category_name = request.form.get("category", "")

    if not title or not summary or not content or category_name not in CATEGORIES:
        raise ValueError("Preencha título, resumo, texto e escolha uma categoria válida.")
    if len(title) > 180 or len(summary) > 350 or len(source_name) > 120:
        raise ValueError("Título, resumo ou nome do profissional ultrapassa o limite permitido.")

    return {
        "title": title,
        "summary": summary,
        "content": content,
        "category": category_name,
        "source_name": source_name or None,
        "featured": bool(request.form.get("featured")),
    }


def news_source_photo_values():
    photo = request.files.get("source_photo")
    if not photo or not photo.filename:
        return None
    if not request.form.get("source_name", "").strip():
        raise ValueError("Informe o nome do profissional antes de adicionar a foto.")
    saved = save_image(photo)
    return {
        "source_image_mimetype": saved["image_mimetype"],
        "source_image_data": saved["image_data"],
    }


@app.route("/admin/noticia/nova", methods=["GET", "POST"])
@admin_required
def admin_news_create():
    if request.method == "POST":
        try:
            values = news_form_values()
            values.update(save_image(request.files.get("image")) or {})
            values.update(news_source_photo_values() or {})
            db.session.add(News(**values))
            db.session.commit()
            flash("Notícia cadastrada.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/news_form.html", article=None)


@app.route("/admin/noticia/<int:news_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_news_edit(news_id):
    article = db.get_or_404(News, news_id)
    if request.method == "POST":
        try:
            values = news_form_values()
            values.update(save_image(request.files.get("image")) or {})
            source_photo_values = news_source_photo_values()
            if source_photo_values:
                values.update(source_photo_values)
            for key, value in values.items():
                setattr(article, key, value)
            if not source_photo_values and (
                request.form.get("remove_source_photo") or not values["source_name"]
            ):
                article.source_image_mimetype = None
                article.source_image_data = None
            article.updated_at = utc_now()
            db.session.commit()
            flash("Notícia atualizada.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/news_form.html", article=article)


@app.route("/admin/noticia/<int:news_id>/excluir", methods=["POST"])
@admin_required
def admin_news_delete(news_id):
    article = db.get_or_404(News, news_id)
    db.session.delete(article)
    db.session.commit()
    flash("Notícia excluída.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/uploads/noticia/<int:news_id>")
def uploaded_file(news_id):
    article = db.get_or_404(News, news_id)
    if not article.image_data:
        abort(404)
    return Response(article.image_data, mimetype=article.image_mimetype or "application/octet-stream")


@app.route("/uploads/noticia/<int:news_id>/profissional")
def news_source_photo(news_id):
    article = db.get_or_404(News, news_id)
    if not article.source_image_data:
        abort(404)
    return Response(
        article.source_image_data,
        mimetype=article.source_image_mimetype or "application/octet-stream",
    )


@app.route("/uploads/profissional/<int:professional_id>")
def professional_photo(professional_id):
    professional = db.get_or_404(Professional, professional_id)
    if not professional.image_data:
        abort(404)
    return Response(
        professional.image_data,
        mimetype=professional.image_mimetype or "application/octet-stream",
    )


@app.route("/uploads/profissional/<int:professional_id>/escritorio")
def professional_office_photo(professional_id):
    professional = db.get_or_404(Professional, professional_id)
    if not professional.office_image_data:
        abort(404)
    return Response(
        professional.office_image_data,
        mimetype=professional.office_image_mimetype or "application/octet-stream",
    )


@app.route("/midia/musica/<int:music_id>")
def music_audio(music_id):
    track = db.get_or_404(MusicTrack, music_id)
    if not track.enabled or not track.audio_data:
        abort(404)

    data = bytes(track.audio_data)
    total_size = len(data)
    range_header = request.headers.get("Range", "").strip()
    start = 0
    requested_end = total_size - 1
    try:
        if range_header:
            if not range_header.lower().startswith("bytes="):
                raise ValueError
            first_range = range_header.split("=", 1)[1].split(",", 1)[0].strip()
            start_text, end_text = first_range.split("-", 1)
            if start_text:
                start = int(start_text)
                requested_end = int(end_text) if end_text else total_size - 1
            else:
                suffix_size = int(end_text)
                if suffix_size <= 0:
                    raise ValueError
                start = max(0, total_size - suffix_size)
                requested_end = total_size - 1
        if start < 0 or start >= total_size or requested_end < start:
            raise ValueError
    except (TypeError, ValueError):
        response = Response(status=416)
        response.headers["Content-Range"] = f"bytes */{total_size}"
        response.headers["Accept-Ranges"] = "bytes"
        return response

    end = min(
        requested_end,
        total_size - 1,
        start + AUDIO_RESPONSE_CHUNK_SIZE - 1,
    )
    payload = data[start:end + 1]
    response = Response(
        payload,
        status=206,
        mimetype=track.audio_mimetype or "application/octet-stream",
    )
    response.headers["Content-Disposition"] = (
        f'inline; filename="{secure_filename(track.audio_filename or "musica")}"'
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
    response.headers["Content-Length"] = str(len(payload))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/contato/foto/<int:attachment_id>")
def chat_attachment_file(attachment_id):
    attachment = db.get_or_404(ChatAttachment, attachment_id)
    conversation_id = attachment.message.conversation_id
    authorized = session.get("admin") or session.get("chat_id") == conversation_id
    if not authorized:
        abort(404)

    response = Response(attachment.image_data, mimetype=attachment.image_mimetype)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="A página que você procura não foi encontrada."), 404


@app.errorhandler(413)
def too_large(_error):
    return render_template("error.html", code=413, message="O arquivo enviado ultrapassa o limite permitido."), 413


@app.errorhandler(500)
def server_error(error):
    app.logger.error("Erro interno: %s", error)
    db.session.rollback()
    return render_template("error.html", code=500, message="Ocorreu um erro inesperado. Tente novamente."), 500


with app.app_context():
    db.create_all()
    migrate_legacy_sqlite()
    migrate_news_source_name()
    migrate_professional_images()
    migrate_conversation_details()
    seed_database()


if __name__ == "__main__":
    app.run(debug=True)
