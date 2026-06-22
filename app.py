"""
Protocolo de Devoluções — controle de devoluções indevidas de alvarás
=====================================================================
Aplicação Flask + SQLite, com área pública de registro/estatísticas e
área de administração protegida por senha (sessão de login).

Como executar:
    pip install -r requirements.txt
    python app.py
A primeira execução cria o banco de dados (instance/protocolo.db) e
um usuário administrador padrão — veja as credenciais impressas no
terminal na primeira inicialização. TROQUE A SENHA assim que entrar.
"""
import os
import re
import csv
import io
import json
import sqlite3
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, g, render_template, request, redirect, url_for,
    session, flash, abort, send_file, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH = os.path.join(INSTANCE_DIR, "protocolo.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
SECRET_KEY_PATH = os.path.join(INSTANCE_DIR, "secret.key")

RE_NUMERO = re.compile(r"^\d{4}/\d{9}$")
RE_PREFIXO = re.compile(r"^\d{4}$")

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "altere-esta-senha"  # trocada no primeiro acesso, ver README


def get_secret_key():
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    if os.environ.get("FLASK_SECRET_KEY"):
        return os.environ["FLASK_SECRET_KEY"]
    if not os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "w") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_KEY_PATH) as f:
        return f.read().strip()


app = Flask(__name__)
app.config["SECRET_KEY"] = get_secret_key()


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    first_run = not os.path.exists(DB_PATH)
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        db.executescript(f.read())
    db.commit()

    cur = db.execute("SELECT COUNT(*) AS c FROM admin_users")
    if cur.fetchone()["c"] == 0:
        db.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            (DEFAULT_ADMIN_USER, generate_password_hash(DEFAULT_ADMIN_PASS)),
        )
        db.commit()
        if first_run:
            print("=" * 64)
            print(" Usuário administrador padrão criado:")
            print(f"   usuário: {DEFAULT_ADMIN_USER}")
            print(f"   senha:   {DEFAULT_ADMIN_PASS}")
            print(" Entre em /admin/login e troque a senha imediatamente.")
            print("=" * 64)
    db.close()


# ---------------------------------------------------------------------------
# Autenticação (área de administração)
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_user"):
            flash("Entre com a senha de administração para continuar.", "error")
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"is_admin": bool(session.get("admin_user")), "current_year": datetime.now().year}


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        row = db.execute(
            "SELECT * FROM admin_users WHERE username = ?", (username,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["admin_user"] = username
            flash("Login realizado.", "success")
            dest = request.args.get("next") or url_for("admin_prefixos")
            return redirect(dest)
        flash("Usuário ou senha inválidos.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_user", None)
    flash("Sessão de administração encerrada.", "success")
    return redirect(url_for("registrar"))


# ---------------------------------------------------------------------------
# Helpers de domínio
# ---------------------------------------------------------------------------
def list_prefixos(db):
    return db.execute("SELECT * FROM prefixos ORDER BY prefixo").fetchall()


def list_motivos(db):
    return db.execute("SELECT * FROM motivos ORDER BY descricao").fetchall()


def today_iso():
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Página inicial
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("registrar"))


# ---------------------------------------------------------------------------
# Registrar devoluções (área pública — não exige login)
# ---------------------------------------------------------------------------
@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    db = get_db()

    if request.method == "POST":
        numero = request.form.get("numero", "").strip()
        prefixo_id = request.form.get("prefixo_id", "").strip()
        motivo_id = request.form.get("motivo_id", "").strip()
        data = request.form.get("data", "").strip() or today_iso()
        observacao = request.form.get("observacao", "").strip()

        errors = []
        if not RE_NUMERO.match(numero):
            errors.append("Número do alvará inválido. Use o formato AAAA/SSSSSSSSS.")
        if not prefixo_id:
            errors.append("Selecione o prefixo (PSO/CENOP) responsável pela devolução.")
        if not motivo_id:
            errors.append("Selecione o motivo da devolução.")

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.execute(
                """INSERT INTO registros (numero, prefixo_id, motivo_id, data, observacao, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (numero, prefixo_id, motivo_id, data, observacao, datetime.now().isoformat()),
            )
            db.commit()
            flash("Devolução registrada com sucesso.", "success")
            return redirect(url_for("registrar"))

    busca = request.args.get("busca", "").strip()
    query = """
        SELECT r.*, p.prefixo AS prefixo_codigo, m.descricao AS motivo_descricao
        FROM registros r
        LEFT JOIN prefixos p ON p.id = r.prefixo_id
        LEFT JOIN motivos m ON m.id = r.motivo_id
    """
    params = []
    if busca:
        query += " WHERE r.numero LIKE ?"
        params.append(f"%{busca}%")
    query += " ORDER BY r.criado_em DESC LIMIT 200"
    registros = db.execute(query, params).fetchall()

    return render_template(
        "registrar.html",
        prefixos=list_prefixos(db),
        motivos=list_motivos(db),
        registros=registros,
        busca=busca,
        today=today_iso(),
    )


@app.route("/registrar/<int:registro_id>/excluir", methods=["POST"])
def excluir_registro(registro_id):
    db = get_db()
    db.execute("DELETE FROM registros WHERE id = ?", (registro_id,))
    db.commit()
    flash("Registro excluído.", "success")
    return redirect(url_for("registrar"))


# ---------------------------------------------------------------------------
# Estatísticas (área pública)
# ---------------------------------------------------------------------------
@app.route("/estatisticas")
def estatisticas():
    db = get_db()
    inicio = request.args.get("inicio", "").strip()
    fim = request.args.get("fim", "").strip()

    where = []
    params = []
    if inicio:
        where.append("r.data >= ?")
        params.append(inicio)
    if fim:
        where.append("r.data <= ?")
        params.append(fim)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM registros r {where_sql}", params
    ).fetchone()["c"]

    por_motivo = db.execute(
        f"""SELECT COALESCE(m.descricao, '(motivo removido)') AS label, COUNT(*) AS count
            FROM registros r LEFT JOIN motivos m ON m.id = r.motivo_id
            {where_sql}
            GROUP BY r.motivo_id ORDER BY count DESC""",
        params,
    ).fetchall()

    por_prefixo = db.execute(
        f"""SELECT COALESCE(p.prefixo, '????') AS label, COUNT(*) AS count
            FROM registros r LEFT JOIN prefixos p ON p.id = r.prefixo_id
            {where_sql}
            GROUP BY r.prefixo_id ORDER BY count DESC""",
        params,
    ).fetchall()

    por_periodo = db.execute(
        f"""SELECT substr(r.data, 1, 7) AS mes, COUNT(*) AS count
            FROM registros r
            {where_sql}
            GROUP BY mes ORDER BY mes""",
        params,
    ).fetchall()

    total_geral = db.execute("SELECT COUNT(*) AS c FROM registros").fetchone()["c"]

    return render_template(
        "estatisticas.html",
        inicio=inicio,
        fim=fim,
        total=total,
        total_geral=total_geral,
        por_motivo=[dict(r) for r in por_motivo],
        por_prefixo=[dict(r) for r in por_prefixo],
        por_periodo=[dict(r) for r in por_periodo],
    )


# ---------------------------------------------------------------------------
# Administração — Prefixos (PSO/CENOP)
# ---------------------------------------------------------------------------
@app.route("/admin/prefixos", methods=["GET", "POST"])
@login_required
def admin_prefixos():
    db = get_db()
    if request.method == "POST":
        prefixo = request.form.get("prefixo", "").strip()
        nome = request.form.get("nome", "").strip()
        if not RE_PREFIXO.match(prefixo):
            flash("O prefixo deve ter exatamente 4 dígitos numéricos.", "error")
        else:
            try:
                db.execute("INSERT INTO prefixos (prefixo, nome) VALUES (?, ?)", (prefixo, nome))
                db.commit()
                flash("Prefixo adicionado.", "success")
            except sqlite3.IntegrityError:
                flash("Esse prefixo já está cadastrado.", "error")
        return redirect(url_for("admin_prefixos"))

    prefixos = list_prefixos(db)
    return render_template("admin/prefixos.html", prefixos=prefixos)


@app.route("/admin/prefixos/<int:prefixo_id>/excluir", methods=["POST"])
@login_required
def admin_excluir_prefixo(prefixo_id):
    db = get_db()
    db.execute("DELETE FROM prefixos WHERE id = ?", (prefixo_id,))
    db.commit()
    flash("Prefixo removido. Registros existentes foram mantidos.", "success")
    return redirect(url_for("admin_prefixos"))


# ---------------------------------------------------------------------------
# Administração — Motivos de devolução
# ---------------------------------------------------------------------------
@app.route("/admin/motivos", methods=["GET", "POST"])
@login_required
def admin_motivos():
    db = get_db()
    if request.method == "POST":
        descricao = request.form.get("descricao", "").strip()
        if not descricao:
            flash("Informe a descrição do motivo.", "error")
        else:
            db.execute("INSERT INTO motivos (descricao) VALUES (?)", (descricao,))
            db.commit()
            flash("Motivo adicionado.", "success")
        return redirect(url_for("admin_motivos"))

    motivos = list_motivos(db)
    return render_template("admin/motivos.html", motivos=motivos)


@app.route("/admin/motivos/<int:motivo_id>/excluir", methods=["POST"])
@login_required
def admin_excluir_motivo(motivo_id):
    db = get_db()
    db.execute("DELETE FROM motivos WHERE id = ?", (motivo_id,))
    db.commit()
    flash("Motivo removido. Registros existentes foram mantidos.", "success")
    return redirect(url_for("admin_motivos"))


# ---------------------------------------------------------------------------
# Administração — senha e backup
# ---------------------------------------------------------------------------
@app.route("/admin/senha", methods=["GET", "POST"])
@login_required
def admin_senha():
    db = get_db()
    if request.method == "POST":
        atual = request.form.get("senha_atual", "")
        nova = request.form.get("senha_nova", "")
        confirmar = request.form.get("senha_confirmar", "")
        row = db.execute(
            "SELECT * FROM admin_users WHERE username = ?", (session["admin_user"],)
        ).fetchone()
        if not row or not check_password_hash(row["password_hash"], atual):
            flash("Senha atual incorreta.", "error")
        elif len(nova) < 8:
            flash("A nova senha deve ter ao menos 8 caracteres.", "error")
        elif nova != confirmar:
            flash("A confirmação de senha não corresponde.", "error")
        else:
            db.execute(
                "UPDATE admin_users SET password_hash = ? WHERE username = ?",
                (generate_password_hash(nova), session["admin_user"]),
            )
            db.commit()
            flash("Senha atualizada com sucesso.", "success")
            return redirect(url_for("admin_senha"))
    return render_template("admin/senha.html")


@app.route("/admin/backup")
@login_required
def admin_backup():
    return render_template("admin/backup.html")


@app.route("/admin/backup/export/json")
@login_required
def admin_export_json():
    db = get_db()
    data = {
        "prefixos": [dict(r) for r in db.execute("SELECT prefixo, nome FROM prefixos").fetchall()],
        "motivos": [dict(r) for r in db.execute("SELECT descricao FROM motivos").fetchall()],
        "registros": [
            dict(r)
            for r in db.execute(
                """SELECT r.numero, p.prefixo AS prefixo, m.descricao AS motivo, r.data, r.observacao, r.criado_em
                   FROM registros r
                   LEFT JOIN prefixos p ON p.id = r.prefixo_id
                   LEFT JOIN motivos m ON m.id = r.motivo_id"""
            ).fetchall()
        ],
    }
    buf = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    filename = f"backup-devolucoes-{today_iso()}.json"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/json")


@app.route("/admin/backup/export/csv")
@login_required
def admin_export_csv():
    db = get_db()
    rows = db.execute(
        """SELECT r.numero, COALESCE(p.prefixo,'') AS prefixo, COALESCE(p.nome,'') AS nome_prefixo,
                  COALESCE(m.descricao,'(motivo removido)') AS motivo, r.data, COALESCE(r.observacao,'') AS observacao
           FROM registros r
           LEFT JOIN prefixos p ON p.id = r.prefixo_id
           LEFT JOIN motivos m ON m.id = r.motivo_id
           ORDER BY r.data DESC"""
    ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["numero", "prefixo", "nome_prefixo", "motivo", "data", "observacao"])
    for r in rows:
        writer.writerow([r["numero"], r["prefixo"], r["nome_prefixo"], r["motivo"], r["data"], r["observacao"]])

    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    filename = f"registros-devolucoes-{today_iso()}.csv"
    return send_file(mem, as_attachment=True, download_name=filename, mimetype="text/csv")


@app.route("/admin/backup/import", methods=["POST"])
@login_required
def admin_import_json():
    file = request.files.get("arquivo")
    if not file or not file.filename:
        flash("Selecione um arquivo .json para importar.", "error")
        return redirect(url_for("admin_backup"))
    try:
        data = json.load(file.stream)
    except Exception:
        flash("Arquivo inválido. Verifique se é um backup exportado por este sistema.", "error")
        return redirect(url_for("admin_backup"))

    db = get_db()
    try:
        db.execute("DELETE FROM registros")
        db.execute("DELETE FROM motivos")
        db.execute("DELETE FROM prefixos")

        prefixo_map = {}
        for p in data.get("prefixos", []):
            cur = db.execute("INSERT INTO prefixos (prefixo, nome) VALUES (?, ?)", (p["prefixo"], p.get("nome", "")))
            prefixo_map[p["prefixo"]] = cur.lastrowid

        motivo_map = {}
        for m in data.get("motivos", []):
            cur = db.execute("INSERT INTO motivos (descricao) VALUES (?)", (m["descricao"],))
            motivo_map[m["descricao"]] = cur.lastrowid

        for r in data.get("registros", []):
            db.execute(
                """INSERT INTO registros (numero, prefixo_id, motivo_id, data, observacao, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    r["numero"],
                    prefixo_map.get(r.get("prefixo")),
                    motivo_map.get(r.get("motivo")),
                    r["data"],
                    r.get("observacao", ""),
                    r.get("criado_em", datetime.now().isoformat()),
                ),
            )
        db.commit()
        flash("Backup importado com sucesso. Todos os dados anteriores foram substituídos.", "success")
    except Exception as exc:
        db.rollback()
        flash(f"Falha ao importar backup: {exc}", "error")

    return redirect(url_for("admin_backup"))


@app.route("/admin/backup/limpar", methods=["POST"])
@login_required
def admin_clear_all():
    senha = request.form.get("senha_confirmacao", "")
    db = get_db()
    row = db.execute(
        "SELECT * FROM admin_users WHERE username = ?", (session["admin_user"],)
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], senha):
        flash("Senha incorreta. Os dados NÃO foram apagados.", "error")
        return redirect(url_for("admin_backup"))

    db.execute("DELETE FROM registros")
    db.execute("DELETE FROM motivos")
    db.execute("DELETE FROM prefixos")
    db.commit()
    flash("Todos os dados (registros, prefixos e motivos) foram apagados.", "success")
    return redirect(url_for("admin_backup"))


# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
