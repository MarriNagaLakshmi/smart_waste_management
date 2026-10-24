
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

DB = os.path.join(BASE, "waste.db")
UPLOAD = os.path.join(BASE, "uploads")

os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)

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

                flash(
                    "This email is already registered.",
                    "error"
                )

    return render_template(
        "auth.html",
        mode="register"
    )


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get("password", "")

        with db() as connection:

            user = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session.update(
                uid=user["id"],
                name=user["name"],
                role=user["role"]
            )

            next_page = request.args.get("next")

            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)

            return redirect(url_for("dashboard"))

        flash(
            "Email or password is incorrect.",
            "error"
        )

    return render_template(
        "auth.html",
        mode="login"
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# --------------------------------------------------
# RESIDENT DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():

    # Corrected status filter
    status = request.args.get("status", "")

    with db() as connection:

        query = """
            SELECT *
            FROM complaints
            WHERE user_id = ?
        """

        arguments = [session["uid"]]

        if status:

            query += " AND status = ?"
            arguments.append(status)

        query += " ORDER BY created DESC"

        complaints = connection.execute(
            query,
            arguments
        ).fetchall()

        updates = connection.execute(
            """
            SELECT updates.*, complaints.complaint_no
            FROM updates
            JOIN complaints
            ON complaints.id = updates.complaint_id
            WHERE complaints.user_id = ?
            ORDER BY updates.created DESC
            LIMIT 12
            """,
            (session["uid"],)
        ).fetchall()

    return render_template(
        "dashboard.html",
        complaints=complaints,
        updates=updates,
        status=status
    )


# --------------------------------------------------
# CREATE COMPLAINT
# --------------------------------------------------

@app.route("/complaint/new", methods=["GET", "POST"])
@login_required
def new_complaint():

    if request.method == "POST":

        category = request.form.get(
            "category", ""
        ).strip()

        description = request.form.get(
            "description", ""
        ).strip()

        location = request.form.get(
            "location", ""
        ).strip()

        latitude = request.form.get("latitude", "")
        longitude = request.form.get("longitude", "")

        image_name = None

        uploaded = request.files.get("image")

        if not category or not description or not location:

            flash(
                "Category, description and location are required.",
                "error"
            )

        else:

            if (
                uploaded
                and uploaded.filename
                and allowed(uploaded.filename)
            ):

                safe_name = secure_filename(uploaded.filename)

                image_name = (
                    uuid.uuid4().hex
                    + "_"
                    + safe_name
                )

                uploaded.save(
                    os.path.join(UPLOAD, image_name)
                )

            priority = (
                "High"
                if any(
                    word in description.lower()
                    for word in [
                        "overflow",
                        "hazard",
                        "medical",
                        "blocked drain"
                    ]
                )
                else "Normal"
            )

            reference = complaint_no()

            with db() as connection:

                cursor = connection.execute(
                    """
                    INSERT INTO complaints
                    (
                        complaint_no,
                        user_id,
                        category,
                        description,
                        location,
                        latitude,
                        longitude,
                        image,
                        status,
                        priority,
                        created,
                        updated
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reference,
                        session["uid"],
                        category,
                        description,
                        location,
                        latitude,
                        longitude,
                        image_name,
                        "Pending",
                        priority,
                        now(),
                        now()
                    )
                )

                complaint_id = cursor.lastrowid

            add_update(
                complaint_id,
                "Pending",
                "Complaint received. The municipal team will review it."
            )

            flash(
                "Complaint submitted. Reference: " + reference,
                "success"
            )

            return redirect(
                url_for("track", no=reference)
            )

    return render_template("new_complaint.html")


# --------------------------------------------------
# TRACK COMPLAINT
# --------------------------------------------------

@app.route("/track/<no>")
@login_required
def track(no):

    with db() as connection:

        complaint = connection.execute(
            """
            SELECT complaints.*, users.name AS reporter
            FROM complaints
            JOIN users ON users.id = complaints.user_id
            WHERE complaint_no = ?
            """,
            (no,)
        ).fetchone()

        if not complaint:
            abort(404)

        if (
            complaint["user_id"] != session["uid"]
            and session.get("role") != "admin"
        ):
            abort(403)

        updates = connection.execute(
            """
            SELECT *
            FROM updates
            WHERE complaint_id = ?
            ORDER BY created DESC
            """,
            (complaint["id"],)
        ).fetchall()

    return render_template(
        "track.html",
        complaint=complaint,
        updates=updates
    )


# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@app.route("/admin")
@login_required
@admin_required
def admin():

    status = request.args.get("status", "")

    query = """
        SELECT complaints.*, users.name AS reporter, users.email
        FROM complaints
        JOIN users ON users.id = complaints.user_id
    """

    arguments = []

    if status:

        query += " WHERE complaints.status = ?"
        arguments.append(status)

    query += " ORDER BY complaints.created DESC"

    with db() as connection:

        complaints = connection.execute(
            query,
            arguments
        ).fetchall()

    return render_template(
        "admin.html",
        complaints=complaints,
        status=status
    )


# --------------------------------------------------
# ADMIN UPDATE COMPLAINT
# --------------------------------------------------

@app.route("/admin/update/<int:cid>", methods=["POST"])
@login_required
@admin_required
def update_complaint(cid):

    status = request.form.get("status")

    worker = request.form.get(
        "worker", ""
    ).strip()

    message = request.form.get(
        "message", ""
    ).strip()

    valid_statuses = {
        "Pending",
        "Assigned",
        "In Progress",
        "Completed",
        "Recycled"
    }

    if status not in valid_statuses:
        abort(400)

    with db() as connection:

        complaint = connection.execute(
            "SELECT * FROM complaints WHERE id = ?",
            (cid,)
        ).fetchone()

        if not complaint:
            abort(404)

        connection.execute(
            """
            UPDATE complaints
            SET assigned_worker = ?, updated = ?
            WHERE id = ?
            """,
            (
                worker,
                now(),
                cid
            )
        )

    if not message:

        if status == "Completed":

            message = "Collection completed successfully."

        elif status == "Recycled":

            message = "Material marked as recycled."

        else:

            message = f"Complaint status changed to {status}."

            if worker:
                message += f" Assigned worker: {worker}."

    add_update(
        cid,
        status,
        message
    )

    flash(
        "Complaint updated. Resident can see this update in their dashboard.",
        "success"
    )

    return redirect(url_for("admin"))


# --------------------------------------------------
# ADMIN REPORTS
# --------------------------------------------------

@app.route("/reports")
@login_required
@admin_required
def reports():

    with db() as connection:

        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM complaints
            GROUP BY status
            """
        ).fetchall()

        areas = connection.execute(
            """
            SELECT location, COUNT(*) AS count
            FROM complaints
            GROUP BY location
            ORDER BY count DESC
            """
        ).fetchall()

    return render_template(
        "reports.html",
        rows=rows,
        areas=areas
    )


# --------------------------------------------------
# RESIDENT FEEDBACK
# --------------------------------------------------

@app.route("/feedback/<no>", methods=["POST"])
@login_required
def feedback(no):

    try:

        rating = int(
            request.form.get("rating", 5)
        )

    except ValueError:

        rating = 5

    rating = max(1, min(5, rating))

    message = request.form.get(
        "message", ""
    ).strip()

    with db() as connection:

        complaint = connection.execute(
            """
            SELECT *
            FROM complaints
            WHERE complaint_no = ?
            AND user_id = ?
            """,
            (
                no,
                session["uid"]
            )
        ).fetchone()

        if not complaint:
            abort(404)

        if complaint["status"] not in (
            "Completed",
            "Recycled"
        ):

            flash(
                "Feedback is available after resolution.",
                "error"
            )

        else:

            connection.execute(
                """
                INSERT INTO feedback
                (complaint_id, user_id, rating, message, created)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    complaint["id"],
                    session["uid"],
                    rating,
                    message,
                    now()
                )
            )

            flash(
                "Thank you for your feedback.",
                "success"
            )

    return redirect(
        url_for("track", no=no)
    )


# --------------------------------------------------
# UPLOADED COMPLAINT IMAGE
# --------------------------------------------------

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# --------------------------------------------------
# ERROR HANDLERS
# --------------------------------------------------

@app.errorhandler(403)
def forbidden(error):

    return render_template(
        "error.html",
        code=403,
        message="You do not have permission to view this page."
    ), 403


@app.errorhandler(404)
def not_found(error):

    return render_template(
        "error.html",
        code=404,
        message="Page or complaint not found."
    ), 404


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

