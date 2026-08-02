import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
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


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True)
    visitor_name = db.Column(db.String(80))
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
    additions = {
        "image_mimetype": "VARCHAR(80)",
        "image_data": binary_type,
        "office_image_mimetype": "VARCHAR(80)",
        "office_image_data": binary_type,
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
    if "source_name" in columns:
        return

    statement = "ALTER TABLE news ADD COLUMN source_name VARCHAR(120)"
    if db.engine.dialect.name == "postgresql":
        statement = "ALTER TABLE news ADD COLUMN IF NOT EXISTS source_name VARCHAR(120)"
    with db.engine.begin() as connection:
        connection.execute(text(statement))


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
    journalist = db.session.execute(db.select(Professional).where(Professional.category == "Jornalista").limit(1)).scalar_one_or_none()
    return render_template("index.html", featured=featured, news=news, journalist=journalist)


@app.route("/categoria/<slug>")
def category(slug):
    category_name = CATEGORY_SLUGS.get(slug.lower())
    if category_name is None and slug in CATEGORIES:
        category_name = slug
    if category_name is None:
        abort(404)
    professionals = db.session.execute(db.select(Professional).where(Professional.category == category_name)).scalars().all()
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
        content = request.form.get("content", "").strip()
        if not name or not content:
            flash("Informe seu nome e escreva uma mensagem.", "error")
        elif len(name) > 80 or len(content) > 2000:
            flash("Nome ou mensagem ultrapassa o limite permitido.", "error")
        else:
            conversation.visitor_name = name
            conversation.updated_at = utc_now()
            db.session.add(ChatMessage(conversation_id=conversation.id, sender="visitor", content=content))
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


@app.route("/admin/profissionais")
@admin_required
def admin_professionals():
    professionals = db.session.execute(db.select(Professional)).scalars().all()
    ordered_professionals = sorted(
        professionals,
        key=lambda item: (CATEGORIES.index(item.category), item.name.lower()),
    )
    return render_template(
        "admin/professionals.html", professionals=ordered_professionals
    )


def professional_form_values():
    category_name = request.form.get("category", "").strip()
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "").strip()
    address = request.form.get("address", "").strip()
    hours = request.form.get("hours", "").strip()
    age_text = request.form.get("age", "").strip()
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

    return {
        "category": category_name,
        "name": name,
        "age": age,
        "role": role,
        "address": address or None,
        "hours": hours,
        "sections": "|".join(section_lines),
    }


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
            for key, value in professional_form_values().items():
                setattr(professional, key, value)
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


@app.route("/admin/noticia/nova", methods=["GET", "POST"])
@admin_required
def admin_news_create():
    if request.method == "POST":
        try:
            values = news_form_values()
            values.update(save_image(request.files.get("image")) or {})
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
            for key, value in values.items():
                setattr(article, key, value)
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


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="A página que você procura não foi encontrada."), 404


@app.errorhandler(413)
def too_large(_error):
    return render_template("error.html", code=413, message="A imagem ultrapassa o limite de 8 MB."), 413


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
    seed_database()


if __name__ == "__main__":
    app.run(debug=True)
