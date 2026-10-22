import hashlib
import re
import secrets
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import g

DB_PATH = Path(__file__).resolve().parent / "data" / "hanap.sqlite"
PBKDF2_ROUNDS = 120_000

CATEGORIES = [
    "Design",
    "Development",
    "Writing",
    "Marketing",
    "Admin",
    "Video",
    "Customer support",
    "AI services",
    "Finance & accounting",
    "Legal",
]
BUDGET_TYPES = ("hourly", "monthly", "fixed")
CURRENCIES = ("USD", "PHP")
APPLICATION_STATUSES = ("pending", "shortlisted", "hired", "declined")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('client', 'freelancer')),
  name TEXT NOT NULL,
  company TEXT NOT NULL DEFAULT '',
  headline TEXT NOT NULL DEFAULT '',
  bio TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  skills TEXT NOT NULL DEFAULT '',
  rate INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL,
  budget_type TEXT NOT NULL CHECK(budget_type IN ('hourly', 'monthly', 'fixed')),
  budget_amount INTEGER NOT NULL,
  currency TEXT NOT NULL CHECK(currency IN ('USD', 'PHP')),
  location TEXT NOT NULL DEFAULT 'Remote',
  skills TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('open', 'closed')) DEFAULT 'open',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  freelancer_id TEXT NOT NULL REFERENCES users(id),
  cover_letter TEXT NOT NULL,
  proposed_rate INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending', 'shortlisted', 'hired', 'declined')) DEFAULT 'pending',
  created_at TEXT NOT NULL,
  UNIQUE(job_id, freelancer_id)
);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  author_id TEXT NOT NULL REFERENCES users(id),
  subject_id TEXT NOT NULL REFERENCES users(id),
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(application_id, author_id)
);

CREATE TABLE IF NOT EXISTS portfolio_items (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  position INTEGER NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS certificates (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  position INTEGER NOT NULL,
  name TEXT NOT NULL,
  issuer TEXT NOT NULL DEFAULT '',
  year INTEGER,
  url TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio_items(user_id);
CREATE INDEX IF NOT EXISTS idx_certificates_user ON certificates(user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_subject ON reviews(subject_id);
CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_apps_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_apps_freelancer ON applications(freelancer_id);
"""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$", 1)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
    )
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


PROFILE_COLUMNS = {
    "photo": "TEXT NOT NULL DEFAULT ''",
    "website": "TEXT NOT NULL DEFAULT ''",
    "linkedin": "TEXT NOT NULL DEFAULT ''",
    "languages": "TEXT NOT NULL DEFAULT ''",
    "experience_years": "INTEGER",
    "availability": "TEXT NOT NULL DEFAULT ''",
    "industry": "TEXT NOT NULL DEFAULT ''",
    "company_size": "TEXT NOT NULL DEFAULT ''",
}
SOCIAL_FIELDS = ("facebook", "instagram", "twitter", "tiktok", "youtube", "github", "behance")
PROFILE_COLUMNS.update({name: "TEXT NOT NULL DEFAULT ''" for name in SOCIAL_FIELDS})
USER_FIELDS = "id, email, role, name, company, headline, bio, location, skills, rate, created_at, " + ", ".join(PROFILE_COLUMNS)


JOB_DETAIL_FIELDS = (
    "experience_level", "duration", "hours_per_week", "start_date", "timezone",
    "responsibilities", "requirements", "nice_to_have", "how_to_apply",
)
JOB_COLUMNS = {name: "TEXT NOT NULL DEFAULT ''" for name in JOB_DETAIL_FIELDS}
APPLICATION_DETAIL_FIELDS = ("start_date", "hours_per_week", "work_link")
APPLICATION_COLUMNS = {name: "TEXT NOT NULL DEFAULT ''" for name in APPLICATION_DETAIL_FIELDS}


def _add_columns(conn, table, columns):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column, definition in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _add_profile_columns(conn):
    _add_columns(conn, "users", PROFILE_COLUMNS)
    _add_columns(conn, "jobs", JOB_COLUMNS)
    _add_columns(conn, "applications", APPLICATION_COLUMNS)


def init_db():
    conn = connect()
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    _add_profile_columns(conn)
    conn.execute("BEGIN IMMEDIATE")
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        _seed(conn)
    review_count = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    has_seed_users = conn.execute("SELECT COUNT(*) FROM users WHERE id IN ('u_maya', 'u_paolo', 'u_andre', 'u_liza', 'u_camille')").fetchone()[0] == 5
    if review_count == 0 and has_seed_users:
        _seed_history(conn)
    andre = conn.execute("SELECT experience_years FROM users WHERE id = 'u_andre'").fetchone()
    if has_seed_users and andre is not None and andre[0] is None:
        _seed_profiles(conn)
    copy_job = conn.execute("SELECT experience_level FROM jobs WHERE id = 'j_copy'").fetchone()
    if copy_job is not None and copy_job[0] == "":
        _seed_job_details(conn)
    conn.commit()
    conn.close()


def _seed(conn):
    password_hash = hash_password("hanap1234")
    users = [
        (
            "u_maya",
            "maya@hanap.test",
            "client",
            "Maya Cruz",
            "Northwind Studio",
            "We hire specialists for client sites",
            "A small studio shipping websites for clinics, cafes, and neighborhood brands.",
            "Manila",
            "",
            None,
            "2026-09-12T02:00:00+00:00",
        ),
        (
            "u_paolo",
            "paolo@hanap.test",
            "client",
            "Paolo Reyes",
            "Brightline Co.",
            "Logistics software for regional carriers",
            "We build tracking tools for freight teams across the Philippines.",
            "Cebu",
            "",
            None,
            "2026-09-18T02:00:00+00:00",
        ),
        (
            "u_andre",
            "andre@hanap.test",
            "freelancer",
            "Andre Santos",
            "",
            "Product designer for early teams",
            "I design calm product interfaces. Previously in-house at a health startup, where I rebuilt the booking flow staff actually used.",
            "Manila",
            "Figma, UX, Design systems, Web design",
            45,
            "2026-09-20T02:00:00+00:00",
        ),
        (
            "u_liza",
            "liza@hanap.test",
            "freelancer",
            "Liza Rahman",
            "",
            "Full-stack developer",
            "I ship React dashboards and the APIs behind them. I like a small slice in the first few days so you can see the work before the whole build.",
            "Remote",
            "React, TypeScript, Node.js, PostgreSQL",
            55,
            "2026-09-22T02:00:00+00:00",
        ),
        (
            "u_camille",
            "camille@hanap.test",
            "freelancer",
            "Camille Ortiz",
            "",
            "Product and brand writer",
            "I write product descriptions, launch pages, and the short lines that make a screen obvious. Clear over clever.",
            "Davao",
            "Copywriting, SEO, Product copy",
            35,
            "2026-09-25T02:00:00+00:00",
        ),
    ]
    conn.executemany(
        """INSERT INTO users
           (id, email, password_hash, role, name, company, headline, bio, location, skills, rate, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(row[0], row[1], password_hash, *row[2:]) for row in users],
    )
    jobs = [
        (
            "j_clinic",
            "u_maya",
            "Redesign a clinic booking website",
            "Northwind is rebuilding the site for a two-location dental clinic. The current booking form asks for too much, and staff retype appointments into a spreadsheet.\n\nWe need a homepage, a services page, and a booking flow in Figma. Development is a separate hire. Please show one healthcare or local-service project in your letter.",
            "Design",
            "fixed",
            1800,
            "USD",
            "Remote",
            "Figma, Web design, UX",
            "open",
            "2026-10-02T04:00:00+00:00",
        ),
        (
            "j_social",
            "u_maya",
            "Social manager for a three-cafe group",
            "Post four times a week across Instagram and Facebook, reply to comments on weekdays, and send a short monthly note on what actually got people in the door.\n\nPhotos come from the cafes. You write the lines and keep the calendar. This is a monthly retainer, not a one-off campaign.",
            "Marketing",
            "monthly",
            25000,
            "PHP",
            "Manila",
            "Instagram, Copywriting, Content",
            "open",
            "2026-10-03T04:00:00+00:00",
        ),
        (
            "j_react",
            "u_paolo",
            "React dashboard for shipment tracking",
            "Brightline needs an internal dashboard: filter shipments, see status, and open a timeline for one delivery. The API already exists.\n\nHourly, about 60 hours to a first version. We care more about tables that stay fast than about decoration.",
            "Development",
            "hourly",
            40,
            "USD",
            "Remote",
            "React, TypeScript, Dashboards",
            "open",
            "2026-10-04T04:00:00+00:00",
        ),
        (
            "j_copy",
            "u_paolo",
            "Write 40 product descriptions",
            "We are listing packing supplies on a new store. Each SKU needs a 60–90 word description and a one-line summary. We will send a sheet with specs and photos.\n\nPlain language. No fake urgency.",
            "Writing",
            "fixed",
            600,
            "USD",
            "Remote",
            "Copywriting, eCommerce",
            "open",
            "2026-10-04T08:00:00+00:00",
        ),
        (
            "j_va",
            "u_maya",
            "Inbox and calendar virtual assistant",
            "Sort a shared inbox, draft replies for approval, and keep two calendars from colliding. About 15 hours a week, weekday mornings in Philippine time.\n\nYou should be comfortable in Gmail and Google Calendar. A short writing sample in the letter is enough.",
            "Admin",
            "monthly",
            18000,
            "PHP",
            "Remote",
            "Admin, Google Workspace, Email",
            "open",
            "2026-10-05T04:00:00+00:00",
        ),
    ]
    conn.executemany(
        """INSERT INTO jobs
           (id, client_id, title, description, category, budget_type, budget_amount, currency, location, skills, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        jobs,
    )
    applications = [
        (
            "a_andre",
            "j_clinic",
            "u_andre",
            "I redesigned a booking flow for a dental clinic last year: fewer fields, clearer appointment types, and a calendar the front desk trusted. I would start with a short audit, then a Figma prototype for the homepage and the booking path. This bid is design only.",
            1600,
            "pending",
            "2026-10-05T06:30:00+00:00",
        ),
        (
            "a_liza",
            "j_react",
            "u_liza",
            "I build React dashboards that stay usable when the table gets long. I would start with filters, a status column, and a timeline for one shipment, and show you that slice in the first three days. Hourly works for me.",
            48,
            "pending",
            "2026-10-05T09:00:00+00:00",
        ),
        (
            "a_camille",
            "j_copy",
            "u_camille",
            "I can write the 40 descriptions in a consistent voice and send the first 8 for a tone check before finishing the sheet. I have done this for a hardware shop and a coffee roaster. Fixed price covers two rounds of edits.",
            550,
            "shortlisted",
            "2026-10-05T11:00:00+00:00",
        ),
    ]
    conn.executemany(
        """INSERT INTO applications
           (id, job_id, freelancer_id, cover_letter, proposed_rate, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        applications,
    )


def _seed_history(conn):
    conn.executemany(
        """INSERT OR IGNORE INTO jobs
           (id, client_id, title, description, category, budget_type, budget_amount, currency, location, skills, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?)""",
        [
            (
                "j_past_logo",
                "u_maya",
                "Refresh the Northwind Studio logo",
                "Our mark is ten years old and falls apart at small sizes. We need a cleaner logo, a favicon, and a one-page usage guide.",
                "Design",
                "fixed",
                900,
                "USD",
                "Remote",
                "Branding, Logo design, Figma",
                "2026-08-02T04:00:00+00:00",
            ),
            (
                "j_past_search",
                "u_paolo",
                "Speed up shipment search",
                "Search across 2 million shipments takes eight seconds. Find out why and fix it without changing the API contract.",
                "Development",
                "hourly",
                50,
                "USD",
                "Remote",
                "PostgreSQL, Node.js, Performance",
                "2026-08-10T04:00:00+00:00",
            ),
            (
                "j_past_help",
                "u_maya",
                "Write help articles for a clinic site",
                "Twelve short help-center articles for a dental clinic: booking, cancellations, insurance, and what to bring.",
                "Writing",
                "fixed",
                15000,
                "PHP",
                "Remote",
                "Copywriting, Healthcare",
                "2026-08-18T04:00:00+00:00",
            ),
        ],
    )
    conn.executemany(
        """INSERT OR IGNORE INTO applications
           (id, job_id, freelancer_id, cover_letter, proposed_rate, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'hired', ?)""",
        [
            ("a_past_andre", "j_past_logo", "u_andre", "I can deliver two logo directions in the first week, then refine one into a full mark, favicon, and usage page.", 850, "2026-08-03T02:00:00+00:00"),
            ("a_past_liza", "j_past_search", "u_liza", "Eight seconds usually means a missing index or a query that sorts before it filters. I would profile first and report back within a day.", 50, "2026-08-11T02:00:00+00:00"),
            ("a_past_camille", "j_past_help", "u_camille", "I have written patient-facing copy for two clinics. I would send three articles first so we can agree on tone.", 14000, "2026-08-19T02:00:00+00:00"),
        ],
    )
    conn.executemany(
        """INSERT OR IGNORE INTO reviews
           (id, application_id, author_id, subject_id, rating, body, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ("r_maya_andre", "a_past_andre", "u_maya", "u_andre", 5, "Andre turned a vague brief into two strong directions in four days. The final logo works at every size we tested, and the usage page saved us a lot of questions.", "2026-08-28T03:00:00+00:00"),
            ("r_andre_maya", "a_past_andre", "u_andre", "u_maya", 5, "Clear brief, quick feedback, and paid the same day I delivered. I would work with Northwind again.", "2026-08-28T06:00:00+00:00"),
            ("r_paolo_liza", "a_past_liza", "u_paolo", "u_liza", 5, "Liza found the slow query on day one and had search under 300 milliseconds by the end of the week. Clear daily notes, and she left the code tidier than she found it.", "2026-08-25T03:00:00+00:00"),
            ("r_liza_paolo", "a_past_liza", "u_liza", "u_paolo", 4, "Good codebase access from day one and a team that answered questions fast. Scope grew a little mid-project, but Paolo adjusted the hours without fuss.", "2026-08-25T08:00:00+00:00"),
            ("r_maya_camille", "a_past_camille", "u_maya", "u_camille", 4, "Camille's articles are clear and friendly, and patients stopped calling about insurance. One round of edits ran a few days late.", "2026-09-05T03:00:00+00:00"),
            ("r_camille_maya", "a_past_camille", "u_camille", "u_maya", 5, "Maya sent everything I needed up front and gave specific notes. Easy project.", "2026-09-05T07:00:00+00:00"),
        ],
    )


def _seed_job_details(conn):
    details = {
        "j_clinic": {
            "experience_level": "intermediate",
            "duration": "1-3 months",
            "hours_per_week": "10-20",
            "start_date": "Within 2 weeks",
            "timezone": "Any, with 2 hours overlap with Philippine time",
            "responsibilities": "Audit the current site and booking form\nDesign the homepage, services page, and booking flow in Figma\nPrototype the booking path so staff can click through it\nHand off a clean file with notes for the developer",
            "requirements": "At least one healthcare or local-service project you can show\nComfortable running a short review call with clinic staff\nStrong Figma skills, including components and auto layout",
            "nice_to_have": "Experience with appointment or scheduling products\nBasic understanding of accessibility for older patients",
            "how_to_apply": "Share one healthcare or local-service project and tell us what you changed and why.",
        },
        "j_social": {
            "experience_level": "intermediate",
            "duration": "Ongoing",
            "hours_per_week": "10-20",
            "start_date": "Immediately",
            "timezone": "Philippine time, weekdays",
            "responsibilities": "Post four times a week on Instagram and Facebook\nReply to comments and messages on weekdays\nKeep a shared content calendar two weeks ahead\nSend a short monthly report on what brought people in",
            "requirements": "Experience running social accounts for a food or retail brand\nClear, friendly writing in English and Filipino\nComfortable with Canva or similar for simple edits",
            "nice_to_have": "Lives in or near Manila and can visit the cafes now and then\nExperience with Meta Business Suite scheduling",
            "how_to_apply": "Link to an account you have managed and tell us one post that worked and why.",
        },
        "j_react": {
            "experience_level": "expert",
            "duration": "1-3 months",
            "hours_per_week": "20-30",
            "start_date": "Within 2 weeks",
            "timezone": "Overlap with 9 AM to 1 PM Philippine time",
            "responsibilities": "Build a shipment list with filters, sorting, and search\nCreate a timeline view for a single delivery\nConnect to our existing REST API\nKeep tables fast with thousands of rows",
            "requirements": "3+ years of React and TypeScript\nExperience building data-heavy tables or dashboards\nComfortable working from an existing API without a designer",
            "nice_to_have": "Experience with TanStack Table or similar\nLogistics or operations software background",
            "how_to_apply": "Share a dashboard you built and tell us how you kept it fast.",
        },
        "j_copy": {
            "experience_level": "entry",
            "duration": "Less than a month",
            "hours_per_week": "Under 10",
            "start_date": "Immediately",
            "timezone": "Any",
            "responsibilities": "Write a 60–90 word description for each of 40 products\nWrite a one-line summary for each product\nFollow the specs and photos we send in a shared sheet\nMake one round of edits after our review",
            "requirements": "Clear, plain English writing\nAble to deliver all 40 descriptions within two weeks\nComfortable working in Google Sheets",
            "nice_to_have": "eCommerce or product copywriting experience\nBasic SEO knowledge for product pages",
            "how_to_apply": "Write a sample description for a roll of packing tape (60–90 words) in your letter.",
        },
        "j_va": {
            "experience_level": "entry",
            "duration": "3-6 months",
            "hours_per_week": "10-20",
            "start_date": "Within 2 weeks",
            "timezone": "Philippine time, weekday mornings",
            "responsibilities": "Sort and label a shared inbox every morning\nDraft replies for approval\nKeep two calendars from overlapping and confirm meetings\nFlag anything urgent in our team chat",
            "requirements": "Comfortable in Gmail and Google Calendar\nClear written English\nReliable internet and a quiet place to work",
            "nice_to_have": "Experience supporting a founder or small agency\nFamiliar with Notion or Trello",
            "how_to_apply": "Include a short writing sample, like a polite reply declining a meeting.",
        },
    }
    for job_id, fields in details.items():
        assignments = ", ".join(f"{column} = ?" for column in fields)
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))


def _seed_profiles(conn):
    details = [
        ("u_maya", {"industry": "Web design studio", "company_size": "2-10", "languages": "English, Filipino"}),
        ("u_paolo", {"industry": "Logistics software", "company_size": "11-50", "languages": "English, Cebuano, Filipino"}),
        ("u_andre", {"experience_years": 6, "availability": "part-time", "languages": "English, Filipino"}),
        ("u_liza", {"experience_years": 8, "availability": "full-time", "languages": "English, Bengali"}),
        ("u_camille", {"experience_years": 4, "availability": "project", "languages": "English, Spanish, Filipino"}),
    ]
    for user_id, fields in details:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", (*fields.values(), user_id))

    portfolio = {
        "u_andre": [
            ("Clinic booking flow", "Rebuilt the appointment flow for a three-branch clinic. No-shows dropped after reminders and a shorter form."),
            ("Design system for a health startup", "Forty components with usage notes, so engineers could ship new screens without a designer in the loop."),
            ("Cafe ordering app", "Pickup ordering for a neighborhood cafe group, from first sketches to the screens they launched with."),
        ],
        "u_liza": [
            ("Shipment tracking dashboard", "React dashboard showing live truck positions and delivery windows for a regional carrier."),
            ("Inventory API", "Node.js and PostgreSQL service handling stock counts for twelve warehouses."),
        ],
        "u_camille": [
            ("Product descriptions for a home goods shop", "Rewrote 120 listings in a warm, plain voice. Return questions about sizing went down."),
            ("Clinic website copy", "Homepage, services, and FAQ pages for a dental clinic, written so patients could book without calling."),
        ],
    }
    certificates = {
        "u_andre": [("Google UX Design Professional Certificate", "Coursera", 2023)],
        "u_liza": [
            ("AWS Certified Developer - Associate", "Amazon Web Services", 2024),
            ("Meta Front-End Developer Professional Certificate", "Coursera", 2022),
        ],
        "u_camille": [("Content Marketing Certification", "HubSpot Academy", 2024)],
    }
    for user_id, items in portfolio.items():
        for position, (title, description) in enumerate(items):
            conn.execute(
                "INSERT INTO portfolio_items (id, user_id, position, title, url, description) VALUES (?, ?, ?, ?, '', ?)",
                (uuid.uuid4().hex, user_id, position, title, description),
            )
    for user_id, items in certificates.items():
        for position, (name, issuer, year) in enumerate(items):
            conn.execute(
                "INSERT INTO certificates (id, user_id, position, name, issuer, year, url) VALUES (?, ?, ?, ?, ?, ?, '')",
                (uuid.uuid4().hex, user_id, position, name, issuer, year),
            )


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_user(user_id):
    row = get_db().execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_portfolio(user_id):
    rows = get_db().execute(
        "SELECT title, url, description FROM portfolio_items WHERE user_id = ? ORDER BY position", (user_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def list_certificates(user_id):
    rows = get_db().execute(
        "SELECT name, issuer, year, url FROM certificates WHERE user_id = ? ORDER BY position", (user_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def replace_portfolio(user_id, items):
    db = get_db()
    db.execute("DELETE FROM portfolio_items WHERE user_id = ?", (user_id,))
    for position, item in enumerate(items):
        db.execute(
            "INSERT INTO portfolio_items (id, user_id, position, title, url, description) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, position, item["title"], item["url"], item["description"]),
        )


def replace_certificates(user_id, items):
    db = get_db()
    db.execute("DELETE FROM certificates WHERE user_id = ?", (user_id,))
    for position, item in enumerate(items):
        db.execute(
            "INSERT INTO certificates (id, user_id, position, name, issuer, year, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, position, item["name"], item["issuer"], item["year"], item["url"]),
        )


def authenticate(email, password):
    row = get_db().execute(
        "SELECT id, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    if row is None or not check_password(password, row["password_hash"]):
        return None
    return get_user(row["id"])


RESERVED_IDS = {"new"}


def readable_id(table, text, fallback):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].strip("-") or fallback
    candidate, number = base, 2
    while candidate in RESERVED_IDS or get_db().execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (candidate,)
    ).fetchone():
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def create_user(email, password, role, name):
    user_id = readable_id("users", name, "member")
    get_db().execute(
        """INSERT INTO users
           (id, email, password_hash, role, name, company, headline, bio, location, skills, rate, created_at)
           VALUES (?, ?, ?, ?, ?, '', '', '', '', '', NULL, ?)""",
        (user_id, email, hash_password(password), role, name, _now()),
    )
    get_db().commit()
    return get_user(user_id)


EDITABLE_FIELDS = {
    "name", "company", "headline", "bio", "location", "skills", "rate", "photo",
    "website", "linkedin", "languages", "experience_years", "availability", "industry", "company_size",
    *SOCIAL_FIELDS,
}


def update_profile(user_id, fields, portfolio=None, certificates=None):
    fields = {key: value for key, value in fields.items() if key in EDITABLE_FIELDS}
    assignments = ", ".join(f"{column} = ?" for column in fields)
    get_db().execute(f"UPDATE users SET {assignments} WHERE id = ?", (*fields.values(), user_id))
    if portfolio is not None:
        replace_portfolio(user_id, portfolio)
    if certificates is not None:
        replace_certificates(user_id, certificates)
    get_db().commit()


def counts():
    db = get_db()
    return {
        "open_count": db.execute("SELECT COUNT(*) FROM jobs WHERE status = 'open'").fetchone()[0],
        "freelancer_count": db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'freelancer'"
        ).fetchone()[0],
        "client_count": db.execute("SELECT COUNT(*) FROM users WHERE role = 'client'").fetchone()[0],
        "application_count": db.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
    }


def category_counts():
    rows = get_db().execute(
        "SELECT category, COUNT(*) AS n FROM jobs WHERE status = 'open' GROUP BY category"
    ).fetchall()
    return {row["category"]: row["n"] for row in rows}


RATING_COLUMNS = """
  (SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.subject_id = users.id) AS rating_avg,
  (SELECT COUNT(*) FROM reviews r WHERE r.subject_id = users.id) AS rating_count
"""


def list_freelancers(limit=4):
    rows = get_db().execute(
        f"""SELECT id, name, headline, skills, rate, location, photo, {RATING_COLUMNS}
           FROM users
           WHERE role = 'freelancer'
           ORDER BY (headline != '') DESC, created_at ASC
           LIMIT ?""",
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def list_jobs(q="", category="", budget_type="", client_id=None, include_closed=False, limit=None):
    clauses = []
    params = []
    if not include_closed:
        clauses.append("jobs.status = 'open'")
    if client_id:
        clauses.append("jobs.client_id = ?")
        params.append(client_id)
    if category:
        clauses.append("jobs.category = ?")
        params.append(category)
    if budget_type:
        clauses.append("jobs.budget_type = ?")
        params.append(budget_type)
    if q:
        cleaned = q.replace("%", "").replace("_", "")
        like = f"%{cleaned}%"
        clauses.append(
            """(jobs.title LIKE ? OR jobs.description LIKE ? OR jobs.skills LIKE ?
                OR users.company LIKE ? OR users.name LIKE ?)"""
        )
        params.extend([like, like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT jobs.*, users.name AS client_name, users.company AS client_company,
          (SELECT COUNT(*) FROM applications a WHERE a.job_id = jobs.id) AS applicant_count
        FROM jobs
        JOIN users ON users.id = jobs.client_id
        {where}
        ORDER BY jobs.created_at DESC
    """
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def get_job(job_id):
    row = get_db().execute(
        """SELECT jobs.*, users.name AS client_name, users.company AS client_company,
                  users.location AS client_location, users.photo AS client_photo,
                  users.industry AS client_industry, users.company_size AS client_company_size,
                  users.created_at AS client_since,
                  (SELECT COUNT(*) FROM jobs j WHERE j.client_id = jobs.client_id) AS client_job_count,
                  (SELECT COUNT(*) FROM applications a JOIN jobs j ON j.id = a.job_id
                    WHERE j.client_id = jobs.client_id AND a.status = 'hired') AS client_hire_count,
                  (SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.subject_id = jobs.client_id) AS client_rating,
                  (SELECT COUNT(*) FROM reviews r WHERE r.subject_id = jobs.client_id) AS client_review_count,
                  (SELECT COUNT(*) FROM applications a WHERE a.job_id = jobs.id) AS applicant_count
           FROM jobs
           JOIN users ON users.id = jobs.client_id
           WHERE jobs.id = ?""",
        (job_id,),
    ).fetchone()
    return dict(row) if row else None


def create_job(client_id, title, description, category, budget_type, budget_amount, currency, location, skills, details=None):
    job_id = readable_id("jobs", title, "job")
    details = {key: value for key, value in (details or {}).items() if key in JOB_DETAIL_FIELDS}
    columns = "".join(f", {key}" for key in details)
    marks = ", ?" * len(details)
    get_db().execute(
        f"""INSERT INTO jobs
           (id, client_id, title, description, category, budget_type, budget_amount, currency, location, skills, status, created_at{columns})
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?{marks})""",
        (job_id, client_id, title, description, category, budget_type, budget_amount, currency, location, skills, _now(),
         *details.values()),
    )
    get_db().commit()
    return job_id


def set_job_status(job_id, client_id, status):
    if status not in {"open", "closed"}:
        return False
    cursor = get_db().execute(
        "UPDATE jobs SET status = ? WHERE id = ? AND client_id = ?",
        (status, job_id, client_id),
    )
    get_db().commit()
    return cursor.rowcount == 1


def get_application(job_id, freelancer_id):
    row = get_db().execute(
        "SELECT * FROM applications WHERE job_id = ? AND freelancer_id = ?",
        (job_id, freelancer_id),
    ).fetchone()
    return dict(row) if row else None


def create_application(job_id, freelancer_id, cover_letter, proposed_rate, details=None):
    application_id = uuid.uuid4().hex
    details = {key: value for key, value in (details or {}).items() if key in APPLICATION_DETAIL_FIELDS}
    columns = "".join(f", {key}" for key in details)
    marks = ", ?" * len(details)
    try:
        get_db().execute(
            f"""INSERT INTO applications
               (id, job_id, freelancer_id, cover_letter, proposed_rate, status, created_at{columns})
               VALUES (?, ?, ?, ?, ?, 'pending', ?{marks})""",
            (application_id, job_id, freelancer_id, cover_letter, proposed_rate, _now(), *details.values()),
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        return None
    return application_id


def list_job_applications(job_id):
    rows = get_db().execute(
        f"""SELECT applications.*, users.name, users.headline, users.email, users.skills,
                  users.location, users.rate, users.id AS freelancer_user_id, {RATING_COLUMNS},
                  EXISTS(SELECT 1 FROM reviews r WHERE r.application_id = applications.id
                         AND r.author_id = jobs.client_id) AS reviewed
           FROM applications
           JOIN users ON users.id = applications.freelancer_id
           JOIN jobs ON jobs.id = applications.job_id
           WHERE applications.job_id = ?
           ORDER BY applications.created_at DESC""",
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_my_applications(freelancer_id):
    rows = get_db().execute(
        """SELECT applications.*, jobs.title, jobs.budget_type, jobs.budget_amount, jobs.currency,
                  jobs.status AS job_status, users.company AS client_company, users.name AS client_name,
                  users.id AS client_user_id,
                  EXISTS(SELECT 1 FROM reviews r WHERE r.application_id = applications.id
                         AND r.author_id = applications.freelancer_id) AS reviewed
           FROM applications
           JOIN jobs ON jobs.id = applications.job_id
           JOIN users ON users.id = jobs.client_id
           WHERE applications.freelancer_id = ?
           ORDER BY applications.created_at DESC""",
        (freelancer_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def rating_summary(user_id):
    row = get_db().execute(
        "SELECT ROUND(AVG(rating), 1) AS avg, COUNT(*) AS count FROM reviews WHERE subject_id = ?",
        (user_id,),
    ).fetchone()
    return {"avg": row["avg"] or 0, "count": row["count"]}


REVIEW_SELECT = """
  SELECT reviews.*, author.name AS author_name, author.company AS author_company,
         author.role AS author_role, subject.name AS subject_name, jobs.title AS job_title
  FROM reviews
  JOIN users author ON author.id = reviews.author_id
  JOIN users subject ON subject.id = reviews.subject_id
  JOIN applications ON applications.id = reviews.application_id
  JOIN jobs ON jobs.id = applications.job_id
"""


def list_reviews_for(user_id):
    rows = get_db().execute(
        REVIEW_SELECT + " WHERE reviews.subject_id = ? ORDER BY reviews.created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_recent_reviews(limit=3):
    rows = get_db().execute(
        REVIEW_SELECT + " WHERE reviews.rating >= 4 ORDER BY reviews.created_at DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def create_review(application_id, author_id, rating, body):
    row = get_db().execute(
        """SELECT applications.status, applications.freelancer_id, jobs.client_id
           FROM applications JOIN jobs ON jobs.id = applications.job_id
           WHERE applications.id = ?""",
        (application_id,),
    ).fetchone()
    if row is None:
        return "That job wasn't found."
    if author_id == row["client_id"]:
        subject_id = row["freelancer_id"]
    elif author_id == row["freelancer_id"]:
        subject_id = row["client_id"]
    else:
        return "You can only review people you worked with."
    if row["status"] != "hired":
        return "Reviews open once someone is hired for the job."
    try:
        get_db().execute(
            """INSERT INTO reviews (id, application_id, author_id, subject_id, rating, body, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, application_id, author_id, subject_id, rating, body, _now()),
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        get_db().rollback()
        return "You already reviewed this job."
    return None


def set_application_status(application_id, client_id, status):
    if status not in APPLICATION_STATUSES:
        return False
    cursor = get_db().execute(
        """UPDATE applications SET status = ?
           WHERE id = ? AND job_id IN (SELECT id FROM jobs WHERE client_id = ?)""",
        (status, application_id, client_id),
    )
    get_db().commit()
    return cursor.rowcount == 1
