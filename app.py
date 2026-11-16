import os, re, time, uuid, secrets, hashlib
from functools import wraps

import cv2
import numpy as np
from flask import (Flask, request, jsonify, render_template, redirect,
                   url_for, session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

import db
import bill
from engine import read_meter, get_pipe

UPLOAD_DIR = "uploads"
ALLOWED = {"jpg", "jpeg", "png"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FAILS = {}
RESET_TRIES = {}


def load_secret():
    if os.path.exists("secret.key"):
        return open("secret.key").read().strip()
    key = secrets.token_hex(32)
    with open("secret.key", "w") as fh:
        fh.write(key)
    return key


os.makedirs(UPLOAD_DIR, exist_ok=True)
db.init_db()
db.init_reset_table()
get_pipe()          # load models once at startup so the first upload is not slow

app = Flask(__name__)
app.secret_key = load_secret()
app.config.update(MAX_CONTENT_LENGTH=8 * 1024 * 1024,
                  SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax")


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = request.form.get("csrf") or request.headers.get("X-CSRF")
        if not token or token != session.get("csrf"):
            abort(400)


@app.context_processor
def inject_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {"csrf_token": session["csrf"]}


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrapper


def password_error(pw):
    if len(pw) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[a-z]", pw):
        return "Password must include a lowercase letter."
    if not re.search(r"[A-Z]", pw):
        return "Password must include an uppercase letter."
    if not re.search(r"\d", pw):
        return "Password must include a number."
    if not re.search(r"[^A-Za-z0-9]", pw):
        return "Password must include a special character such as @ . # ! $."
    return None


def is_locked(ip):
    return time.time() < FAILS.get(ip, (0, 0))[1]


def register_fail(ip):
    n, _ = FAILS.get(ip, (0, 0))
    n += 1
    FAILS[ip] = (0, time.time() + 300) if n >= 5 else (n, 0)


def reset_allowed(ip, limit=5, window=900):
    now = time.time()
    hits = [t for t in RESET_TRIES.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        RESET_TRIES[ip] = hits
        return False
    hits.append(now)
    RESET_TRIES[ip] = hits
    return True


def send_reset_email(to, link):
    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"\n[DEV] Password reset link for {to}:\n{link}\n")
        return
    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = "Reset your Digitronix password"
        msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER"))
        msg["To"] = to
        msg.set_content("Hello,\n\nUse the link below to reset your Digitronix password. "
                        f"It is valid for 30 minutes.\n\n{link}\n\n"
                        "If you did not request this, you can ignore this email.")
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
    except Exception as e:
        print("[EMAIL ERROR]", e)
        print(f"[DEV] Password reset link for {to}: {link}")


@app.route("/")
def home():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        err = None
        if len(name) < 2 or not EMAIL_RE.match(email):
            err = "Please enter your name and a valid email address."
        elif password_error(pw):
            err = password_error(pw)
        elif pw != confirm:
            err = "Passwords do not match."
        elif not db.create_user(name, email, generate_password_hash(pw)):
            err = "This email is already registered. Please sign in."
        if err:
            flash(err, "error")
        else:
            flash("Account created. Please sign in.", "success")
            return redirect(url_for("login"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr
        if is_locked(ip):
            flash("Too many failed attempts. Please try again in 5 minutes.", "error")
            return render_template("auth.html", mode="login")
        email = request.form.get("email", "").strip().lower()
        user = db.get_user_by_email(email)
        if not user:
            register_fail(ip)
            flash("This account does not exist. Please create an account first.", "error")
        elif not check_password_hash(user["password_hash"], request.form.get("password", "")):
            register_fail(ip)
            flash("Incorrect password. Please try again or use Forgot password.", "error")
        else:
            FAILS.pop(ip, None)
            csrf = session.get("csrf")
            session.clear()
            session["csrf"] = csrf
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login")


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        if not reset_allowed(request.remote_addr):
            flash("Too many requests. Please try again later.", "error")
            return render_template("auth.html", mode="forgot")
        email = request.form.get("email", "").strip().lower()
        user = db.get_user_by_email(email)
        if not user:
            flash("No account found with this email. Please create an account first.", "error")
            return render_template("auth.html", mode="forgot")
        token = secrets.token_urlsafe(32)
        db.create_reset(user["id"], hashlib.sha256(token.encode()).hexdigest(), time.time() + 1800)
        send_reset_email(email, url_for("reset", token=token, _external=True))
        flash("A password reset link has been sent to your email. It is valid for 30 minutes.", "success")
        return redirect(url_for("login"))
    return render_template("auth.html", mode="forgot")


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    row = db.get_reset(hashlib.sha256(token.encode()).hexdigest())
    if not row or row["used"] or row["expires_at"] < time.time():
        flash("This reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("forgot"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        if password_error(pw):
            flash(password_error(pw), "error")
        elif pw != request.form.get("confirm", ""):
            flash("Passwords do not match.", "error")
        else:
            db.finish_reset(row["id"], row["user_id"], generate_password_hash(pw))
            flash("Your password has been reset. Please sign in.", "success")
            return redirect(url_for("login"))
    return render_template("auth.html", mode="reset", token=token)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", name=session["user_name"])


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify(ok=False, message="Please choose an image."), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED:
        return jsonify(ok=False, message="Only JPG and PNG images are supported."), 400
    data = f.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jsonify(ok=False, message="This file is not a valid image."), 400

    result = read_meter(img)
    if not result["ok"]:
        return jsonify(ok=False, message=result["message"]), 422

    value = float(result["reading"])
    last = db.last_reading(session["user_id"])
    units = round(value - last["reading"], 2) if last and value >= last["reading"] else None
    prev_units = [r["units_consumed"] for r in db.list_readings(session["user_id"], 5)]
    est = bill.estimate(units, prev_units)

    name = uuid.uuid4().hex + "." + ext
    with open(os.path.join(UPLOAD_DIR, name), "wb") as out:
        out.write(data)
    db.add_reading(session["user_id"], value, units, result["confidence"], name)
    return jsonify(ok=True, reading=value, units_consumed=units, bill=est,
                   confidence=result["confidence"], first_reading=last is None)


@app.route("/history")
@login_required
def history():
    rows = db.list_readings(session["user_id"])
    for i, r in enumerate(rows):
        prev = [x["units_consumed"] for x in rows[i + 1:i + 6]]
        r["bill"] = bill.estimate(r["units_consumed"], prev)
    return jsonify(rows)

from advisor import advisor_bp
app.register_blueprint(advisor_bp)
if __name__ == "__main__":
    app.run(debug=False)