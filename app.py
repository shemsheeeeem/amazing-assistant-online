import json
import os
import re
import secrets
import sqlite3
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, session

import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ID_RE = re.compile(r"^[a-z0-9-]{1,60}$")
ROOT = Path(__file__).resolve().parent
PAGE = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
if "AAO_BOOT_JSON_TOKEN" not in PAGE:
    raise RuntimeError("The page template is missing its data marker.")


def load_secret():
    from_env = os.environ.get("AAO_SECRET")
    if from_env:
        return from_env
    key_file = db.DB_PATH.parent / "secret.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    return key_file.read_text(encoding="utf-8").strip()


app = Flask(__name__)
app.secret_key = load_secret()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RENDER"))
app.config["MAX_CONTENT_LENGTH"] = 200_000
app.permanent_session_lifetime = 60 * 60 * 24 * 14
db.init_db()


@app.teardown_appcontext
def close_db(_exc):
    db.close_db()


def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def csrf_ok():
    token = session.get("_csrf")
    sent = request.headers.get("X-CSRF", "")
    return bool(token and sent and secrets.compare_digest(token, sent))


def boot():
    return {
        "csrf": csrf_token(),
        "user": db.session_payload(session.get("user_id")),
        **db.board(),
    }


def page():
    payload = json_for_script(boot())
    html = PAGE.replace("AAO_BOOT_JSON_TOKEN", payload)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


def json_for_script(payload):
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


def fail(message, status=400):
    return jsonify(ok=False, error=message), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def clean_line(value, limit):
    return " ".join(str(value or "").split())[:limit]


def clean_block(value, limit):
    text = str(value or "").replace("\r\n", "\n").strip()
    return text[:limit]


def lines_of(value, limit=12, item_limit=240):
    items = []
    for raw in str(value or "").replace("\r\n", "\n").split("\n"):
        line = " ".join(raw.split())
        if not line:
            continue
        items.append(line[:item_limit])
        if len(items) >= limit:
            break
    return items


def skill_list(value):
    items = []
    for part in str(value or "").split(","):
        skill = " ".join(part.split())
        if skill:
            items.append(skill[:40])
        if len(items) >= 12:
            break
    return items


def current():
    return db.get_user(session.get("user_id"))


@app.get("/")
def home():
    return page()


@app.post("/signup")
def signup():
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    data = body()
    name = clean_line(data.get("name"), 80)
    email = clean_line(data.get("email"), 120).lower()
    password = str(data.get("password") or "")
    role = data.get("role")
    org = clean_line(data.get("org"), 80)
    if role not in {"employer", "assistant"}:
        return fail("Choose whether you are hiring or looking for work.")
    if len(name) < 2:
        return fail("Enter the name people should see.")
    if not EMAIL_RE.match(email):
        return fail("Enter a valid email.")
    if not 8 <= len(password) <= 200:
        return fail("Use a password of at least 8 characters.")
    if role == "employer" and len(org) < 2:
        return fail("Enter the business name.")
    headline = org if role == "assistant" else ""
    company = org if role == "employer" else ""
    if db.get_user_by_email(email):
        return fail("That email already has an account. Log in instead.")
    user_id = db.create_user(email, password, role, name, company, headline)
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["_csrf"] = secrets.token_urlsafe(32)
    return jsonify(ok=True, next="post" if role == "employer" else "account")


@app.post("/login")
def login():
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    data = body()
    email = clean_line(data.get("email"), 120).lower()
    password = str(data.get("password") or "")
    user = db.get_user_by_email(email) if EMAIL_RE.match(email) else None
    if user is None or not db.check_password(password, user["password_hash"]):
        return fail("That email and password do not match.")
    if email.endswith(".example"):
        return fail("That email and password do not match.")
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["_csrf"] = secrets.token_urlsafe(32)
    return jsonify(ok=True, next="account")


@app.post("/logout")
def logout():
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    session.clear()
    return jsonify(ok=True)


@app.post("/profile")
def save_profile():
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    user = current()
    if user is None:
        return fail("Log in to continue.", 401)
    data = body()
    if user["role"] == "employer":
        org = clean_line(data.get("org"), 80)
        if len(org) < 2:
            return fail("Enter the business name.")
        size = data.get("size") if data.get("size") in db.SIZES else ""
        db.update_user(user["id"], {
            "org": org,
            "about": clean_block(data.get("about"), 2000),
            "industry": clean_line(data.get("industry"), 80),
            "company_size": size,
            "location": clean_line(data.get("location"), 80),
            "languages": clean_line(data.get("languages"), 80),
        })
    else:
        category = data.get("category") if data.get("category") in db.CATEGORIES else ""
        availability = data.get("availability") if data.get("availability") in db.AVAILABILITY else ""
        portfolio = []
        title = clean_line(data.get("port_title"), 80)
        description = clean_line(data.get("port_description"), 240)
        if title and description:
            portfolio = [{"t": title, "d": description}]
        certificates = []
        cert_title = clean_line(data.get("cert_title"), 80)
        cert_source = clean_line(data.get("cert_source"), 80)
        if cert_title:
            certificates = [{"t": cert_title, "s": cert_source}]
        db.update_user(user["id"], {
            "headline": clean_line(data.get("headline"), 120),
            "about": clean_block(data.get("about"), 2000),
            "category": category,
            "location": clean_line(data.get("location"), 80),
            "availability": availability,
            "experience": clean_line(data.get("experience"), 40),
            "languages": clean_line(data.get("languages"), 80),
            "skills": json.dumps(skill_list(data.get("skills"))),
            "portfolio": json.dumps(portfolio),
            "certificates": json.dumps(certificates),
        })
    return jsonify(ok=True, next="account")


@app.post("/jobs")
def post_job():
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    user = current()
    if user is None or user["role"] != "employer":
        return fail("Log in with an employer account to post a job.", 403)
    data = body()
    title = clean_line(data.get("title"), 120)
    category = data.get("category")
    pay_type = data.get("pay_type")
    experience = data.get("experience")
    length = data.get("length")
    hours = data.get("hours")
    start = data.get("start")
    currency = data.get("currency")
    try:
        amount = int(str(data.get("amount") or "").replace(",", "").strip())
    except ValueError:
        amount = 0
    about = lines_of(data.get("about"), limit=6, item_limit=500)
    responsibilities = lines_of(data.get("responsibilities"))
    requirements = lines_of(data.get("requirements"))
    nice = lines_of(data.get("nice"))
    skills = skill_list(data.get("skills"))
    if len(title) < 4:
        return fail("Enter a job title.")
    if category not in db.CATEGORIES:
        return fail("Choose a field.")
    if pay_type not in db.PAY_TYPES or currency not in {"PHP", "USD"} or not 1 <= amount <= 10_000_000:
        return fail("Enter the pay, the currency, and the pay type.")
    if experience not in db.EXPERIENCE or length not in db.LENGTHS or hours not in db.HOURS or start not in db.STARTS:
        return fail("Choose the schedule for this role.")
    if not about or not responsibilities or not requirements or not skills:
        return fail("Add a description, the work, what you need, and at least one skill.")
    symbol = "₱" if currency == "PHP" else "$"
    per = {"Monthly": "per month", "Hourly": "per hour", "Fixed project": "fixed project"}[pay_type]
    job_id = db.create_job(user["id"], {
        "title": title,
        "category": category,
        "pay": f"{symbol}{amount:,}",
        "per": per,
        "pay_type": pay_type,
        "location": clean_line(data.get("location"), 80) or "Remote",
        "timezone": clean_line(data.get("timezone"), 80) or "Any",
        "experience": experience,
        "experience_note": db.EXPERIENCE[experience],
        "length": length,
        "hours": hours,
        "start_when": start,
        "about": about,
        "responsibilities": responsibilities,
        "requirements": requirements,
        "nice": nice,
        "skills": skills,
        "standout": clean_block(data.get("standout"), 400) or "Tell the employer why you are a fit for this work.",
    })
    return jsonify(ok=True, next=f"job-{job_id}")


@app.post("/jobs/<job_id>/apply")
def apply(job_id):
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    if not ID_RE.match(job_id) or not db.job_exists(job_id):
        return fail("That job is no longer listed.", 404)
    user = current()
    if user is None or user["role"] != "assistant":
        return fail("Log in with a virtual assistant account to apply.", 403)
    letter = clean_block(body().get("letter"), 4000)
    if len(letter) < 20:
        return fail("Write at least 20 characters so the employer can learn about you.")
    try:
        db.create_application(job_id, user["id"], letter)
    except sqlite3.IntegrityError:
        db.get_db().rollback()
        return fail("You have already applied for this role.")
    return jsonify(ok=True)


@app.post("/talent/<talent_id>/contact")
def contact(talent_id):
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    if not ID_RE.match(talent_id) or not db.talent_exists(talent_id):
        return fail("That profile is no longer listed.", 404)
    user = current()
    if user is None or user["role"] != "employer":
        return fail("Log in with an employer account to contact this assistant.", 403)
    message = clean_block(body().get("message"), 2000)
    if len(message) < 10:
        return fail("Write a short message, at least 10 characters.")
    db.create_inquiry(user["id"], talent_id, message)
    return jsonify(ok=True)


@app.post("/support")
def support():
    if not csrf_ok():
        return fail("The form expired. Reload the page and try again.")
    data = body()
    name = clean_line(data.get("name"), 80)
    email = clean_line(data.get("email"), 120).lower()
    message = clean_block(data.get("message"), 4000)
    if len(name) < 2 or not EMAIL_RE.match(email) or len(message) < 10:
        return fail("Enter your name, a valid email, and a message.")
    db.create_support(name, email, message)
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("AAO_PORT") or "5070")
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    if os.environ.get("AAO_OPEN_BROWSER") == "1":
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    print(f"\n  Amazing Assistants Online is running at http://127.0.0.1:{port}\n  Keep this window open.\n")
    app.run(host=host, port=port, debug=False)
