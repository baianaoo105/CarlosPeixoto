import os
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "jornal.db"
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
CATEGORIES = ["Polícia", "Médicos", "Bombeiros", "Juiz", "Advogado", "Jornalista"]

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao"),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
)
UPLOAD_DIR.mkdir(exist_ok=True)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
    count = db.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    if count == 0:
        db.executescript((BASE_DIR / "seed.sql").read_text(encoding="utf-8"))
    db.commit()


def save_image(file):
    if not file or not file.filename:
        return None
    original = secure_filename(file.filename)
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato inválido. Use PNG, JPG, JPEG, WEBP ou GIF.")
    filename = f"{uuid4().hex}.{extension}"
    file.save(UPLOAD_DIR / filename)
    return filename


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            flash("Entre no painel para continuar.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def globals_for_templates():
    return {"categories": CATEGORIES, "current_year": datetime.now().year}


@app.template_filter("datetime_br")
def datetime_br(value):
    """Exibe as datas do SQLite no formato brasileiro."""
    if not value:
        return "Sem atualização"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y às %H:%M")
    except (TypeError, ValueError):
        return str(value)


@app.route("/")
def index():
    db = get_db()
    featured = db.execute("SELECT * FROM news ORDER BY featured DESC, created_at DESC LIMIT 1").fetchone()
    news = db.execute("SELECT * FROM news ORDER BY created_at DESC LIMIT 9").fetchall()
    journalist = db.execute("SELECT * FROM professionals WHERE category = 'Jornalista' LIMIT 1").fetchone()
    return render_template("index.html", featured=featured, news=news, journalist=journalist)


@app.route("/categoria/<category>")
def category(category):
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    professionals = db.execute("SELECT * FROM professionals WHERE category = ?", (category,)).fetchall()
    news = db.execute("SELECT * FROM news WHERE category = ? ORDER BY created_at DESC", (category,)).fetchall()
    return render_template("category.html", category=category, professionals=professionals, news=news)


@app.route("/noticia/<int:news_id>", methods=["GET", "POST"])
def news_detail(news_id):
    db = get_db()
    article = db.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if article is None:
        abort(404)
    if request.method == "POST":
        author = request.form.get("author", "").strip()
        content = request.form.get("content", "").strip()
        if not author or not content:
            flash("Informe seu nome e escreva um comentário.", "error")
        elif len(author) > 80 or len(content) > 1000:
            flash("Comentário muito longo.", "error")
        else:
            db.execute("INSERT INTO comments (news_id, author, content) VALUES (?, ?, ?)", (news_id, author, content))
            db.commit()
            flash("Comentário publicado.", "success")
            return redirect(url_for("news_detail", news_id=news_id) + "#comentarios")
    comments = db.execute("SELECT * FROM comments WHERE news_id = ? ORDER BY created_at DESC", (news_id,)).fetchall()
    return render_template("news_detail.html", article=article, comments=comments)


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
            flash("Acesso liberado.", "success")
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Senha incorreta.", "error")
    return render_template("admin/login.html")


@app.route("/admin/sair")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    category_sections = []
    for category_name in CATEGORIES:
        items = db.execute(
            "SELECT * FROM news WHERE category = ? ORDER BY updated_at DESC, created_at DESC",
            (category_name,),
        ).fetchall()
        category_sections.append(
            {
                "name": category_name,
                "news_items": items,
                "last_updated": items[0]["updated_at"] if items else None,
            }
        )
    return render_template("admin/dashboard.html", category_sections=category_sections)


def news_form_values():
    title = request.form.get("title", "").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    category_name = request.form.get("category", "")
    if not title or not summary or not content or category_name not in CATEGORIES:
        raise ValueError("Preencha título, resumo, texto e escolha uma categoria válida.")
    if len(title) > 180 or len(summary) > 350:
        raise ValueError("Título ou resumo ultrapassa o limite permitido.")
    return title, summary, content, category_name, 1 if request.form.get("featured") else 0


@app.route("/admin/noticia/nova", methods=["GET", "POST"])
@admin_required
def admin_news_create():
    if request.method == "POST":
        try:
            values = news_form_values()
            image = save_image(request.files.get("image"))
            get_db().execute("INSERT INTO news (title, summary, content, category, featured, image) VALUES (?, ?, ?, ?, ?, ?)", (*values, image))
            get_db().commit()
            flash("Notícia cadastrada.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/news_form.html", article=None)


@app.route("/admin/noticia/<int:news_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_news_edit(news_id):
    db = get_db()
    article = db.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if article is None:
        abort(404)
    if request.method == "POST":
        try:
            values = news_form_values()
            image = save_image(request.files.get("image")) or article["image"]
            db.execute("UPDATE news SET title=?, summary=?, content=?, category=?, featured=?, image=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*values, image, news_id))
            db.commit()
            flash("Notícia atualizada.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("admin/news_form.html", article=article)


@app.route("/admin/noticia/<int:news_id>/excluir", methods=["POST"])
@admin_required
def admin_news_delete(news_id):
    db = get_db()
    article = db.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if article is None:
        abort(404)
    db.execute("DELETE FROM news WHERE id = ?", (news_id,))
    db.commit()
    flash("Notícia excluída.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="A página que você procura não foi encontrada."), 404


@app.errorhandler(413)
def too_large(_error):
    return render_template("error.html", code=413, message="A imagem ultrapassa o limite de 8 MB."), 413


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", code=500, message="Ocorreu um erro inesperado. Tente novamente."), 500


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
