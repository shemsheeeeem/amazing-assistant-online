import hashlib
import json
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from flask import g

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "aao.sqlite"
SEED_PATH = ROOT / "seed.json"
PBKDF2_ROUNDS = 120_000

CATEGORIES = {
    "Admin": "Administrative support",
    "Customer support": "Customer support",
    "Marketing": "Marketing and social media",
    "Writing": "Writing and content",
    "Design": "Design",
    "Development": "Web and technical",
    "Video": "Video",
    "AI services": "AI-assisted services",
    "Finance & accounting": "Finance and bookkeeping",
    "Legal": "Legal support",
}
PAY_TYPES = ("Monthly", "Hourly", "Fixed project")
EXPERIENCE = {
    "Entry level": "New to this kind of work, or a few projects in",
    "Intermediate": "Solid experience and a portfolio to show",
    "Expert": "Deep experience, works with little direction",
}
LENGTHS = ("Less than a month", "1–3 months", "3–6 months", "6+ months", "Ongoing")
HOURS = (
    "Under 10 hrs/week",
    "10–20 hrs/week",
    "20–30 hrs/week",
    "30–40 hrs/week",
    "Full-time, 40 hrs/week",
)
STARTS = ("Immediately", "Within 2 weeks", "Within a month", "Flexible")
AVAILABILITY = (
    "Available full-time",
    "Available part-time",
    "Open to projects",
    "Not taking work right now",
)
SIZES = ("Just me", "2–10 people", "11–50 people", "51–200 people", "200+ people")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  name TEXT NOT NULL,
  org TEXT NOT NULL DEFAULT '',
  headline TEXT NOT NULL DEFAULT '',
  about TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  industry TEXT NOT NULL DEFAULT '',
  company_size TEXT NOT NULL DEFAULT '',
  availability TEXT NOT NULL DEFAULT '',
  experience TEXT NOT NULL DEFAULT '',
  languages TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  skills TEXT NOT NULL DEFAULT '[]',
  portfolio TEXT NOT NULL DEFAULT '[]',
  certificates TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  employer_id TEXT NOT NULL,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  pay TEXT NOT NULL,
  per TEXT NOT NULL,
  pay_type TEXT NOT NULL,
  location TEXT NOT NULL,
  timezone TEXT NOT NULL,
  experience TEXT NOT NULL,
  experience_note TEXT NOT NULL,
  length TEXT NOT NULL,
  hours TEXT NOT NULL,
  start_when TEXT NOT NULL,
  about TEXT NOT NULL,
  responsibilities TEXT NOT NULL,
  requirements TEXT NOT NULL,
  nice TEXT NOT NULL,
  skills TEXT NOT NULL,
  standout TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  letter TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(job_id, user_id)
);
CREATE TABLE IF NOT EXISTS inquiries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employer_id TEXT NOT NULL,
  talent_id TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS support_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ROUNDS)
    return secrets.compare_digest(digest.hex(), digest_hex)


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db():
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def loads(value, fallback):
    try:
        parsed = json.loads(value or "")
    except json.JSONDecodeError:
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def slug(conn, table, text, fallback):
    if table not in {"users", "jobs"}:
        raise ValueError(table)
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:50].strip("-") or fallback
    candidate, number = base, 2
    while conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def _seed(conn):
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    stamp = "2026-01-01T00:00:00+00:00"
    for employer in seed["employers"].values():
        conn.execute(
            """INSERT INTO users
               (id, email, password_hash, role, name, org, about, location, industry, company_size, languages, skills, portfolio, certificates, created_at)
               VALUES (?, ?, ?, 'employer', ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', ?)""",
            (
                employer["id"],
                f"{employer['id']}@companies.example",
                hash_password(secrets.token_urlsafe(24)),
                employer["contact"],
                employer["name"],
                employer["about"],
                employer["loc"],
                employer["industry"],
                employer["size"],
                employer["langs"],
                stamp,
            ),
        )
    for person in seed["talent"]:
        conn.execute(
            """INSERT INTO users
               (id, email, password_hash, role, name, headline, about, location, availability, experience, languages, category, skills, portfolio, certificates, created_at)
               VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                person["id"],
                f"{person['id']}@profiles.example",
                hash_password(secrets.token_urlsafe(24)),
                person["name"],
                person["headline"],
                person["about"],
                person["loc"],
                person["avail"],
                person["exp"],
                person["langs"],
                person["cat"],
                json.dumps(person["skills"]),
                json.dumps(person["port"]),
                json.dumps(person["certs"]),
                stamp,
            ),
        )
    for job in seed["jobs"]:
        conn.execute(
            """INSERT INTO jobs
               (id, employer_id, title, category, pay, per, pay_type, location, timezone, experience, experience_note,
                length, hours, start_when, about, responsibilities, requirements, nice, skills, standout, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job["id"],
                job["emp"],
                job["title"],
                job["cat"],
                job["pay"],
                job["per"],
                job["type"],
                job["loc"],
                job["tz"],
                job["exp"],
                job["expn"],
                job["len"],
                job["hours"],
                job["start"],
                json.dumps(job["about"]),
                json.dumps(job["doo"]),
                json.dumps(job["look"]),
                json.dumps(job["nice"]),
                json.dumps(job["skills"]),
                job["stand"],
                stamp,
            ),
        )


def init_db():
    conn = connect()
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        _seed(conn)
    conn.commit()
    conn.close()


def row_user(row):
    if row is None:
        return None
    return dict(row)


def get_user(user_id):
    if not user_id:
        return None
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return row_user(row)


def get_user_by_email(email):
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return row_user(row)


def public_employer(user):
    return {
        "id": user["id"],
        "name": user["org"] or user["name"],
        "contact": user["name"],
        "industry": user["industry"],
        "size": user["company_size"],
        "loc": user["location"],
        "langs": user["languages"],
        "about": user["about"],
    }


def public_talent(user):
    return {
        "id": user["id"],
        "name": user["name"],
        "headline": user["headline"] or "Virtual assistant",
        "cat": user["category"],
        "loc": user["location"],
        "avail": user["availability"] or "Open to projects",
        "exp": user["experience"],
        "langs": user["languages"],
        "skills": loads(user["skills"], []),
        "about": user["about"],
        "port": loads(user["portfolio"], []),
        "certs": loads(user["certificates"], []),
    }


def public_job(row):
    job = dict(row)
    return {
        "id": job["id"],
        "title": job["title"],
        "emp": job["employer_id"],
        "cat": job["category"],
        "pay": job["pay"],
        "per": job["per"],
        "type": job["pay_type"],
        "loc": job["location"],
        "tz": job["timezone"],
        "exp": job["experience"],
        "expn": job["experience_note"],
        "len": job["length"],
        "hours": job["hours"],
        "start": job["start_when"],
        "about": loads(job["about"], []),
        "doo": loads(job["responsibilities"], []),
        "look": loads(job["requirements"], []),
        "nice": loads(job["nice"], []),
        "skills": loads(job["skills"], []),
        "stand": job["standout"],
    }


def board():
    conn = get_db()
    employers = {}
    for row in conn.execute("SELECT * FROM users WHERE role = 'employer' ORDER BY rowid"):
        item = public_employer(row_user(row))
        employers[item["id"]] = item
    talent = [public_talent(row_user(row)) for row in conn.execute("SELECT * FROM users WHERE role = 'assistant' ORDER BY rowid")]
    jobs = [public_job(row) for row in conn.execute("SELECT * FROM jobs ORDER BY rowid")]
    return {"employers": employers, "talent": talent, "jobs": jobs}


def session_payload(user_id):
    user = get_user(user_id)
    if user is None:
        return None
    conn = get_db()
    payload = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "org": user["org"],
        "headline": user["headline"],
        "about": user["about"],
        "location": user["location"],
        "industry": user["industry"],
        "size": user["company_size"],
        "availability": user["availability"],
        "experience": user["experience"],
        "languages": user["languages"],
        "category": user["category"],
        "skills": loads(user["skills"], []),
        "portfolio": loads(user["portfolio"], []),
        "certificates": loads(user["certificates"], []),
    }
    if user["role"] == "assistant":
        rows = conn.execute(
            """SELECT a.job_id, j.title FROM applications a
               JOIN jobs j ON j.id = a.job_id
               WHERE a.user_id = ? ORDER BY a.id DESC""",
            (user["id"],),
        ).fetchall()
        payload["applied"] = [row["job_id"] for row in rows]
        payload["applications"] = [{"job_id": row["job_id"], "title": row["title"]} for row in rows]
    else:
        contacted = conn.execute("SELECT talent_id FROM inquiries WHERE employer_id = ?", (user["id"],)).fetchall()
        payload["contacted"] = [row["talent_id"] for row in contacted]
        owned = []
        for job in conn.execute("SELECT id, title FROM jobs WHERE employer_id = ? ORDER BY rowid DESC", (user["id"],)):
            applicants = conn.execute(
                """SELECT u.name, a.letter FROM applications a
                   JOIN users u ON u.id = a.user_id
                   WHERE a.job_id = ? ORDER BY a.id""",
                (job["id"],),
            ).fetchall()
            owned.append({
                "id": job["id"],
                "title": job["title"],
                "applicants": [{"name": row["name"], "letter": row["letter"]} for row in applicants],
            })
        payload["jobs"] = owned
    return payload


def create_user(email, password, role, name, org, headline):
    conn = get_db()
    user_id = slug(conn, "users", name, "member")
    conn.execute(
        """INSERT INTO users
           (id, email, password_hash, role, name, org, headline, skills, portfolio, certificates, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', ?)""",
        (user_id, email, hash_password(password), role, name, org, headline, now()),
    )
    conn.commit()
    return user_id


def update_user(user_id, fields):
    allowed = {
        "name", "org", "headline", "about", "location", "industry", "company_size",
        "availability", "experience", "languages", "category", "skills", "portfolio", "certificates",
    }
    chosen = {key: value for key, value in fields.items() if key in allowed}
    if not chosen:
        return
    assignments = ", ".join(f"{column} = ?" for column in chosen)
    get_db().execute(f"UPDATE users SET {assignments} WHERE id = ?", (*chosen.values(), user_id))
    get_db().commit()


def create_job(employer_id, job):
    conn = get_db()
    job_id = slug(conn, "jobs", job["title"], "job")
    conn.execute(
        """INSERT INTO jobs
           (id, employer_id, title, category, pay, per, pay_type, location, timezone, experience, experience_note,
            length, hours, start_when, about, responsibilities, requirements, nice, skills, standout, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            job_id, employer_id, job["title"], job["category"], job["pay"], job["per"], job["pay_type"],
            job["location"], job["timezone"], job["experience"], job["experience_note"], job["length"],
            job["hours"], job["start_when"], json.dumps(job["about"]), json.dumps(job["responsibilities"]),
            json.dumps(job["requirements"]), json.dumps(job["nice"]), json.dumps(job["skills"]), job["standout"], now(),
        ),
    )
    conn.commit()
    return job_id


def job_exists(job_id):
    return get_db().execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone() is not None


def create_application(job_id, user_id, letter):
    conn = get_db()
    conn.execute(
        "INSERT INTO applications (job_id, user_id, letter, created_at) VALUES (?, ?, ?, ?)",
        (job_id, user_id, letter, now()),
    )
    conn.commit()


def create_inquiry(employer_id, talent_id, message):
    conn = get_db()
    conn.execute(
        "INSERT INTO inquiries (employer_id, talent_id, message, created_at) VALUES (?, ?, ?, ?)",
        (employer_id, talent_id, message, now()),
    )
    conn.commit()


def talent_exists(talent_id):
    row = get_db().execute("SELECT 1 FROM users WHERE id = ? AND role = 'assistant'", (talent_id,)).fetchone()
    return row is not None


def create_support(name, email, message):
    conn = get_db()
    conn.execute(
        "INSERT INTO support_requests (name, email, message, created_at) VALUES (?, ?, ?, ?)",
        (name, email, message, now()),
    )
    conn.commit()
