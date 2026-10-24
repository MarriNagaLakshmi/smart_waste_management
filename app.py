import os
import sqlite3
import uuid

from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
    send_from_directory
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# --------------------------------------------------
# APPLICATION CONFIGURATION
# --------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))

DB = os.path.join(BASE, "waste_prod.db")
UPLOAD = os.path.join(BASE, "uploads")

os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)

# AUTOMATED DATABASE INITIALIZATION TRIGGER FOR RENDER
@app.before_request
def auto_initialize_database():
    try:
        init_db()
    except Exception as e:
        app.logger.error(f"Auto-init database error: {e}")

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-for-deployment"
)

app.config["UPLOAD_FOLDER"] = UPLOAD
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED = {"png", "jpg", "jpeg", "webp"}


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    with db() as connection:

        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'resident',
                created TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY,
                complaint_no TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT NOT NULL,
                latitude TEXT,
                longitude TEXT,
                image TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                priority TEXT NOT NULL DEFAULT 'Normal',
                assigned_worker TEXT,
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS updates (
                id INTEGER PRIMARY KEY,
                complaint_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created TEXT NOT NULL,
                FOREIGN KEY(complaint_id) REFERENCES complaints(id)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY,
                complaint_id INTEGER,
                user_id INTEGER,
                rating INTEGER,
                message TEXT,
                created TEXT
            );
        """)

        admin = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            ("admin@waste.local",)
        ).fetchone()

        if not admin:
            connection.execute(
                """
                INSERT INTO users
                (name, email, password, role, created)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Administrator",
                    "admin@waste.local",
                    generate_password_hash("Admin123!"),
                    "admin",
                    now()
                )
            )


# --------------------------------------------------
# LOGIN REQUIRED DECORATOR
# --------------------------------------------------

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("uid"):
            return redirect(
                url_for("login", next=request.path)
            )

        return function(*args, **kwargs)

    return wrapper


# --------------------------------------------------
# ADMIN REQUIRED DECORATOR
# --------------------------------------------------

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if session.get("role") != "admin":
            abort(403)

        return function(*args, **kwargs)

    return wrapper


# --------------------------------------------------
# COMPLAINT HELPERS
# --------------------------------------------------

def complaint_no():
    return (
        "SWM-"
        + datetime.now().strftime("%y%m%d")
        + "-"
        + uuid.uuid4().hex[:6].upper()
    )


def add_update(complaint_id, status, message):

    with db() as connection:

        connection.execute(
            """
            INSERT INTO updates
            (complaint_id, status, message, created)
            VALUES (?, ?, ?, ?)
            """,
            (
                complaint_id,
                status,
                message,
                now()
            )
        )

        connection.execute(
            """
            UPDATE complaints
            SET status = ?, updated = ?
            WHERE id = ?
            """,
            (
                status,
                now(),
                complaint_id
            )
        )


def allowed(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED
    )


# --------------------------------------------------
# COMMON TEMPLATE DATA
# --------------------------------------------------

@app.context_processor
def common():

    return {
        "current_user": session.get("name"),
        "role": session.get("role")
    }


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():

    with db() as connection:

        total = connection.execute(
            "SELECT COUNT(*) AS n FROM complaints"
        ).fetchone()["n"]

        pending = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM complaints
            WHERE status IN ('Pending', 'Assigned', 'In Progress')
            """
        ).fetchone()["n"]

        done = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM complaints
            WHERE status IN ('Completed', 'Recycled')
            """
        ).fetchone()["n"]

        recent = connection.execute(
            """
            SELECT complaints.*, users.name AS reporter
            FROM complaints
            JOIN users ON users.id = complaints.user_id
            ORDER BY complaints.created DESC
            LIMIT 6
            """
        ).fetchall()

    return render_template(
        "home.html",
        total=total,
        pending=pending,
        done=done,
        recent=recent
    )


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:

            flash(
                "Enter name, valid email and password (6+ characters).",
                "error"
            )

        else:

            try:

                with db() as connection:

                    connection.execute(
                        """
                        INSERT INTO users
                        (name, email, password, role, created)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            name,
                            email,
                            generate_password_hash(password),
                            "resident",
                            now()
                        )
                    )

                flash(
                    "Account created. Please sign in.",
                    "success"
                )

                return redirect(url_for("login"))

            except sqlite3.IntegrityError:

                flash("Email already registered.", "error")

    return render_template("register.html")


# --------------------------------------------------
# LOGIN / LOGOUT
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with db() as connection:

            user = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):

            session["uid"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            nxt = request.args.get("next")

            if nxt and nxt.startswith("/"):
                return redirect(nxt)

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("resident_dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))


# --------------------------------------------------
# RUN SERVER CONFIGURATION FOR DEPLOYMENT
# --------------------------------------------------
