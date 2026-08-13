import json
import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
CATEGORIES = ["Polícia", "Médicos", "Bombeiros", "Juiz", "Advogado", "Jornalista"]
REGIONS = ["Carlos Peixoto", "Osso Seco"]
MAX_IMAGE = 8 * 1024 * 1024
MAX_VIDEO = 20 * 1024 * 1024
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}


def database_url():
    # Prefira a conexão agrupada nas funções serverless da Vercel.
    value = next((os.getenv(key, "").strip() for key in ("DATABASE_URL", "POSTGRES_URL", "DATABASE_URL_UNPOOLED") if os.getenv(key, "").strip()), "")
    if not value:
        path = Path("/tmp/jornal_novo.db") if os.getenv("VERCEL") else BASE_DIR / "jornal_novo.db"
        return f"sqlite:///{path.as_posix()}"
    if value.startswith("postgres://"):
        value = "postgresql://" + value[11:]
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[13:]
    return value


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "desenvolvimento-local-troque-na-vercel"),
    SQLALCHEMY_DATABASE_URI=database_url(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
    MAX_CONTENT_LENGTH=21 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("VERCEL")),
)
db = SQLAlchemy(app)


def now():
    return datetime.now(timezone.utc)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(350), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    region = db.Column(db.String(40), nullable=False, index=True)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    image_name = db.Column(db.String(255))
    image_type = db.Column(db.String(80))
    image_data = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    region = db.Column(db.String(40), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class Professional(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(600), nullable=False)
    photo_type = db.Column(db.String(80))
    photo_data = db.Column(db.LargeBinary)


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    minecraft_name = db.Column(db.String(80), nullable=False)
    discord_name = db.Column(db.String(100), nullable=False)
    platform = db.Column(db.String(60), nullable=False)
    days = db.Column(db.String(200), nullable=False)
    times = db.Column(db.String(200), nullable=False)
    area = db.Column(db.String(60), nullable=False, index=True)
    answers = db.Column(db.Text, nullable=False)
    integrity = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Pendente", index=True)
    admin_notes = db.Column(db.String(800))
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


def save_upload(file, allowed, limit):
    if not file or not file.filename:
        return None
    name = secure_filename(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed:
        raise ValueError("Formato de arquivo não permitido.")
    data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"O arquivo ultrapassa {limit // 1024 // 1024} MB.")
    return name, file.mimetype or "application/octet-stream", data


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def seed():
    if db.session.scalar(db.select(func.count(News.id))):
        return
    db.session.add_all([
        News(title="Novo portal aproxima informação e comunidade", summary="O Jornal Carlos Peixoto inicia uma nova fase com cobertura regional.", content="O novo portal reúne notícias, vídeos, serviços e informações profissionais em um só lugar. A cobertura será dividida entre Carlos Peixoto e Osso Seco.", category="Jornalista", region="Carlos Peixoto", featured=True),
        News(title="Osso Seco recebe nova agenda de serviços", summary="Atendimentos e ações comunitárias ganham calendário regional.", content="A região de Osso Seco terá uma agenda própria de serviços e notícias de interesse público.", category="Jornalista", region="Osso Seco", featured=True),
    ])
    db.session.add_all([
        Professional(category=c, name=f"Equipe de {c}", role="Atendimento à comunidade", description="Informações, serviços e atualizações desta área.") for c in CATEGORIES
    ])
    db.session.commit()


@app.before_request
def initialize():
    if request.endpoint in {"static", "favicon", "health"}:
        return
    # Em cada nova sessão, a primeira tela é a entrada administrativa.
    # Visitantes podem continuar sem criar conta ou informar senha.
    if not session.get("admin") and not session.get("entry_seen") and request.endpoint not in {"login", "continue_as_visitor"}:
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    try:
        db.create_all()
        seed()
    except Exception:
        db.session.rollback()
        app.logger.exception("Erro ao preparar banco")


@app.context_processor
def shared():
    return {"categories": CATEGORIES, "regions": REGIONS, "year": datetime.now().year}


@app.route("/")
def home():
    featured = db.session.execute(db.select(News).where(News.featured.is_(True)).order_by(News.updated_at.desc()).limit(4)).scalars().all()
    latest = db.session.execute(db.select(News).order_by(News.created_at.desc()).limit(9)).scalars().all()
    videos = db.session.execute(db.select(Video).order_by(Video.created_at.desc()).limit(3)).scalars().all()
    return render_template("home.html", featured=featured, latest=latest, videos=videos)


@app.route("/favicon.ico")
def favicon():
    """Responde à solicitação automática do navegador sem acessar o banco."""
    return Response(status=204)


@app.route("/regiao/<name>")
def region(name):
    if name not in REGIONS: abort(404)
    featured = db.session.execute(db.select(News).where(News.region == name, News.featured.is_(True)).order_by(News.updated_at.desc())).scalars().all()
    latest = db.session.execute(db.select(News).where(News.region == name).order_by(News.created_at.desc())).scalars().all()
    return render_template("listing.html", heading=name, eyebrow="Região", featured=featured, items=latest)


@app.route("/profissao/<category>")
def profession(category):
    if category not in CATEGORIES: abort(404)
    people = db.session.execute(db.select(Professional).where(Professional.category == category)).scalars().all()
    items = db.session.execute(db.select(News).where(News.category == category).order_by(News.created_at.desc())).scalars().all()
    return render_template("profession.html", category=category, people=people, items=items)


@app.route("/noticia/<int:item_id>")
def news_detail(item_id):
    return render_template("news.html", item=db.get_or_404(News, item_id))


@app.route("/imagem/noticia/<int:item_id>")
def news_image(item_id):
    item = db.get_or_404(News, item_id)
    if not item.image_data: abort(404)
    return Response(item.image_data, mimetype=item.image_type)


@app.route("/imagem/profissional/<int:item_id>")
def professional_image(item_id):
    item = db.get_or_404(Professional, item_id)
    if not item.photo_data: abort(404)
    return Response(item.photo_data, mimetype=item.photo_type)


@app.route("/videos")
def videos():
    items = db.session.execute(db.select(Video).order_by(Video.created_at.desc())).scalars().all()
    return render_template("videos.html", items=items)


@app.route("/video/<int:item_id>")
def video_file(item_id):
    item = db.get_or_404(Video, item_id)
    return Response(item.data, mimetype=item.mimetype, headers={"Content-Disposition": f'inline; filename="{item.filename}"'})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        expected_user = os.getenv("ADMIN_USERNAME", "admin")
        expected_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
        expected_password = os.getenv("ADMIN_PASSWORD", "")
        valid_password = check_password_hash(expected_hash, password) if expected_hash else bool(expected_password) and password == expected_password
        if username == expected_user and valid_password:
            session.clear(); session["admin"] = True; session["entry_seen"] = True; session.permanent = False
            destination = request.args.get("next", "")
            if not destination.startswith("/") or destination.startswith("//"):
                destination = url_for("admin")
            return redirect(destination)
        flash("Usuário ou senha incorretos.", "error")
    return render_template("login.html")


@app.route("/continuar")
def continue_as_visitor():
    session["entry_seen"] = True
    session.permanent = False
    destination = request.args.get("next", "")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = url_for("home")
    return redirect(destination)


@app.route("/sair")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin():
    counts = {"noticias": db.session.scalar(db.select(func.count(News.id))), "videos": db.session.scalar(db.select(func.count(Video.id))), "profissionais": db.session.scalar(db.select(func.count(Professional.id))), "candidaturas": db.session.scalar(db.select(func.count(Application.id)))}
    applications = db.session.execute(db.select(Application).order_by(Application.created_at.desc()).limit(10)).scalars().all()
    return render_template("admin.html", counts=counts, applications=applications)


@app.route("/admin/noticia", methods=["GET", "POST"])
@admin_required
def admin_news():
    if request.method == "POST":
        try:
            upload = save_upload(request.files.get("image"), IMAGE_EXTENSIONS, MAX_IMAGE)
            item = News(title=request.form["title"].strip(), summary=request.form["summary"].strip(), content=request.form["content"].strip(), category=request.form["category"], region=request.form["region"], featured=bool(request.form.get("featured")))
            if upload: item.image_name, item.image_type, item.image_data = upload
            db.session.add(item); db.session.commit(); flash("Notícia publicada.", "success")
            return redirect(url_for("admin"))
        except (KeyError, ValueError) as error: flash(str(error), "error")
    return render_template("admin_form.html", kind="notícia")


@app.route("/admin/video", methods=["GET", "POST"])
@admin_required
def admin_video():
    if request.method == "POST":
        try:
            upload = save_upload(request.files.get("video"), VIDEO_EXTENSIONS, MAX_VIDEO)
            if not upload: raise ValueError("Escolha um vídeo.")
            name, mimetype, data = upload
            db.session.add(Video(title=request.form["title"].strip(), description=request.form["description"].strip(), region=request.form["region"], filename=name, mimetype=mimetype, data=data))
            db.session.commit(); flash("Vídeo publicado.", "success"); return redirect(url_for("admin"))
        except (KeyError, ValueError) as error: flash(str(error), "error")
    return render_template("admin_form.html", kind="vídeo")


@app.route("/admin/profissional", methods=["GET", "POST"])
@admin_required
def admin_professional():
    if request.method == "POST":
        try:
            upload = save_upload(request.files.get("photo"), IMAGE_EXTENSIONS, MAX_IMAGE)
            item = Professional(category=request.form["category"], name=request.form["name"].strip(), role=request.form["role"].strip(), description=request.form["description"].strip())
            if upload: _, item.photo_type, item.photo_data = upload
            db.session.add(item); db.session.commit(); flash("Profissional adicionado.", "success"); return redirect(url_for("admin"))
        except (KeyError, ValueError) as error: flash(str(error), "error")
    return render_template("admin_form.html", kind="profissional")


@app.route("/candidatura", methods=["GET", "POST"])
def application():
    if request.method == "POST":
        required = ["minecraft_name", "discord_name", "platform", "area", "integrity", "aware"]
        if any(not request.form.get(field) for field in required) or not request.form.getlist("days") or not request.form.getlist("times"):
            flash("Preencha todos os campos obrigatórios.", "error")
        else:
            answers = {key: value for key, value in request.form.items() if key.startswith("q")}
            db.session.add(Application(minecraft_name=request.form["minecraft_name"].strip(), discord_name=request.form["discord_name"].strip(), platform=request.form["platform"], days="|".join(request.form.getlist("days")), times="|".join(request.form.getlist("times")), area=request.form["area"], answers=json.dumps(answers, ensure_ascii=False), integrity=request.form["integrity"].strip()))
            db.session.commit(); return render_template("application_done.html")
    return render_template("application.html")


@app.route("/admin/candidatura/<int:item_id>", methods=["GET", "POST"])
@admin_required
def admin_application(item_id):
    item = db.get_or_404(Application, item_id)
    if request.method == "POST":
        item.status = request.form.get("status", "Pendente")
        item.admin_notes = request.form.get("admin_notes", "").strip()
        db.session.commit(); flash("Candidatura atualizada.", "success")
    return render_template("application_review.html", item=item, answers=json.loads(item.answers))


@app.route("/saude")
def health(): return {"status": "ok"}


@app.errorhandler(413)
def too_large(_): return "Arquivo acima do limite permitido.", 413


if __name__ == "__main__":
    app.run(debug=True)
