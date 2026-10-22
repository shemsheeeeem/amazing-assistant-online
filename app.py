import os
import re
import secrets
import socket
import sqlite3
import threading
import time
import webbrowser
from functools import wraps
from urllib.parse import urlsplit

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DESIGNS = ("classic", "loop", "care")
HOME_TEMPLATES = {"classic": "home.html", "loop": "home_loop.html", "care": "home_care.html"}
BUDGET_LABELS = {"hourly": "Hourly", "monthly": "Monthly", "fixed": "Fixed project"}
STATUS_LABELS = {
    "pending": "Pending",
    "shortlisted": "Shortlisted",
    "hired": "Hired",
    "declined": "Declined",
    "open": "Open",
    "closed": "Closed",
}
AVAILABILITY_LABELS = {
    "full-time": "Available full-time",
    "part-time": "Available part-time",
    "project": "Open to projects",
    "unavailable": "Not taking work right now",
}
COMPANY_SIZES = ("Just me", "2-10", "11-50", "51-200", "200+")
EXPERIENCE_LEVELS = {
    "entry": ("Entry level", "New to this kind of work, or a few projects in"),
    "intermediate": ("Intermediate", "Solid experience and a portfolio to show"),
    "expert": ("Expert", "Deep experience, works with little direction"),
}
DURATIONS = ("Less than a month", "1-3 months", "3-6 months", "6+ months", "Ongoing")
HOURS_OPTIONS = {
    "Under 10": "Under 10 hrs/week",
    "10-20": "10–20 hrs/week",
    "20-30": "20–30 hrs/week",
    "30-40": "30–40 hrs/week",
    "40+": "Full-time, 40 hrs/week",
}
START_OPTIONS = ("Immediately", "Within 2 weeks", "Within a month", "Flexible")
JOB_LIST_FIELDS = ("responsibilities", "requirements", "nice_to_have")
SOCIAL_LINKS = (
    ("facebook", "Facebook", "https://facebook.com/"),
    ("instagram", "Instagram", "https://instagram.com/"),
    ("twitter", "X (Twitter)", "https://x.com/"),
    ("tiktok", "TikTok", "https://tiktok.com/@"),
    ("youtube", "YouTube", "https://youtube.com/@"),
    ("github", "GitHub", "https://github.com/"),
    ("behance", "Behance", "https://behance.net/"),
)
MAX_PORTFOLIO = 12
MAX_CERTIFICATES = 12
PHOTO_LIMIT = 4 * 1024 * 1024
PHOTO_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"RIFF": "webp"}

def load_secret():
    from_env = os.environ.get("HANAP_SECRET")
    if from_env:
        return from_env
    import secrets

    key_file = db.DB_PATH.parent / "secret.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


app = Flask(__name__)
app.secret_key = load_secret()
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.permanent_session_lifetime = 60 * 60 * 24 * 14
app.config["MAX_CONTENT_LENGTH"] = PHOTO_LIMIT + 512 * 1024
UPLOADS = db.DB_PATH.parent / "uploads"


def money(amount, budget_type, currency="USD"):
    symbol = "₱" if currency == "PHP" else "$"
    formatted = f"{symbol}{int(amount):,}"
    if budget_type == "hourly":
        return f"{formatted}/hr"
    if budget_type == "monthly":
        return f"{formatted}/mo"
    return f"{formatted} fixed"


def skills_list(value):
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def link_label(url):
    parts = urlsplit(url)
    return (parts.netloc.removeprefix("www.") + parts.path.rstrip("/")) or url


def clean_url(raw):
    raw = raw.strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or "." not in parts.netloc or len(raw) > 300:
        return None
    return raw


def clean_social(raw, base):
    raw = raw.strip()
    handle = raw.lstrip("@")
    if handle and (raw.startswith("@") or not re.search(r"[./]", handle)):
        return clean_url(base + handle) if re.fullmatch(r"[\w.-]{1,60}", handle) else None
    return clean_url(raw)


def profile_links(person):
    links = [(link_label(person["website"]), person["website"]), ("LinkedIn", person["linkedin"])]
    links += [(label, person[key]) for key, label, _ in SOCIAL_LINKS]
    return [(label, url) for label, url in links if url]


def text_lines(text):
    return [line.strip().lstrip("-•*").strip() for line in (text or "").splitlines() if line.strip().lstrip("-•*").strip()]


def month_year(iso):
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso).strftime("%B %Y")
    except (TypeError, ValueError):
        return ""


def photo_url(person):
    if person and person.get("photo"):
        return url_for("media", name=person["photo"])
    return None


def posted(iso):
    from datetime import datetime, timezone

    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - then
    if delta.days <= 0:
        hours = delta.seconds // 3600
        if hours <= 0:
            return "Just now"
        return f"{hours}h ago"
    if delta.days == 1:
        return "Yesterday"
    return f"{delta.days}d ago"


def safe_next(value):
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return None


def csrf_token():
    token = session.get("_csrf")
    if not token:
        import secrets

        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def current_user():
    if "current_user" in g:
        return g.current_user
    user_id = session.get("user_id")
    g.current_user = db.get_user(user_id) if user_id else None
    if user_id and g.current_user is None:
        session.clear()
    return g.current_user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def guard_csrf():
    if request.method != "POST":
        return None
    token = session.get("_csrf")
    sent = request.form.get("_csrf", "")
    import secrets

    if not token or not secrets.compare_digest(token, sent):
        flash("That form expired. Try again.", "error")
        return redirect(request.referrer or url_for("home"))
    return None


def current_design():
    chosen = request.args.get("design")
    if chosen in DESIGNS:
        return chosen
    saved = request.cookies.get("design")
    return saved if saved in DESIGNS else "classic"


@app.after_request
def remember_design(response):
    chosen = request.args.get("design")
    if chosen in DESIGNS and request.cookies.get("design") != chosen:
        response.set_cookie("design", chosen, max_age=60 * 60 * 24 * 365, samesite="Lax", httponly=True)
    return response


@app.teardown_appcontext
def close_db(_exc):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@app.context_processor
def inject_globals():
    return {
        "user": current_user(),
        "categories": db.CATEGORIES,
        "budget_types": db.BUDGET_TYPES,
        "currencies": db.CURRENCIES,
        "budget_labels": BUDGET_LABELS,
        "status_labels": STATUS_LABELS,
        "money": money,
        "skills_list": skills_list,
        "posted": posted,
        "csrf_token": csrf_token,
        "design": current_design(),
        "availability_labels": AVAILABILITY_LABELS,
        "company_sizes": COMPANY_SIZES,
        "social_links": SOCIAL_LINKS,
        "profile_links": profile_links,
        "text_lines": text_lines,
        "experience_levels": EXPERIENCE_LEVELS,
        "durations": DURATIONS,
        "hours_options": HOURS_OPTIONS,
        "start_options": START_OPTIONS,
        "link_label": link_label,
        "photo_url": photo_url,
        "month_year": month_year,
    }


def _clean_int(raw, minimum, maximum):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < minimum or value > maximum:
        return None
    return value


@app.get("/")
def home():
    return render_template(
        HOME_TEMPLATES[current_design()],
        jobs=db.list_jobs(limit=6),
        freelancers=db.list_freelancers(limit=4),
        reviews=db.list_recent_reviews(limit=5),
        category_counts=db.category_counts(),
        **db.counts(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(safe_next(request.args.get("next")) or url_for("dashboard"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.authenticate(email, password)
        if user is None:
            error = "That email and password don't match."
        else:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            csrf_token()
            flash(f"Welcome back, {user['name'].split()[0]}.", "ok")
            return redirect(safe_next(request.form.get("next")) or url_for("dashboard"))
    return render_template("login.html", error=error), (400 if error else 200)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user():
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if len(name) < 2 or len(name) > 80:
            error = "Enter the name clients or freelancers should see."
        elif not EMAIL_RE.match(email) or len(email) > 120:
            error = "Enter a valid email."
        elif not 8 <= len(password) <= 200:
            error = "Use a password of at least 8 characters."
        elif role not in {"client", "freelancer"}:
            error = "Choose whether you are hiring or looking for work."
        else:
            try:
                user = db.create_user(email, password, role, name)
            except sqlite3.IntegrityError:
                db.get_db().rollback()
                user = None
                error = "That email already has an account. Log in instead."
            if user:
                session.clear()
                session.permanent = True
                session["user_id"] = user["id"]
                csrf_token()
                flash("Account created. Finish your profile when you are ready.", "ok")
                destination = safe_next(request.form.get("next"))
                if destination:
                    return redirect(destination)
                if role == "client":
                    return redirect(url_for("new_job"))
                return redirect(url_for("profile"))
    return render_template("signup.html", error=error), (400 if error else 200)


@app.post("/logout")
def logout():
    session.clear()
    flash("You are logged out.", "ok")
    return redirect(url_for("home"))


@app.get("/jobs")
def jobs():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    budget_type = request.args.get("budget_type", "").strip()
    if category not in db.CATEGORIES:
        category = ""
    if budget_type not in db.BUDGET_TYPES:
        budget_type = ""
    found = db.list_jobs(q=q, category=category, budget_type=budget_type)
    return render_template(
        "jobs.html",
        jobs=found,
        q=q,
        category=category,
        budget_type=budget_type,
    )


@app.get("/jobs/<job_id>")
def job_detail(job_id):
    job = db.get_job(job_id)
    if job is None:
        abort(404)
    user = current_user()
    existing = None
    if user and user["role"] == "freelancer":
        existing = db.get_application(job_id, user["id"])
    return render_template("job.html", job=job, existing=existing, error=None)


@app.post("/jobs/<job_id>/apply")
def apply(job_id):
    job = db.get_job(job_id)
    if job is None:
        abort(404)
    user = current_user()
    if user is None:
        flash("Log in to continue.", "error")
        return redirect(url_for("login", next=url_for("job_detail", job_id=job_id)))
    if user["role"] != "freelancer":
        flash("Freelancer accounts can apply. Client accounts post jobs.", "error")
        return redirect(url_for("job_detail", job_id=job_id))
    if job["status"] != "open":
        flash("This role is closed.", "error")
        return redirect(url_for("job_detail", job_id=job_id))
    if db.get_application(job_id, user["id"]):
        flash("You already applied to this job.", "error")
        return redirect(url_for("job_detail", job_id=job_id))
    cover_letter = request.form.get("cover_letter", "").strip()
    proposed = _clean_int(request.form.get("proposed_rate"), 1, 10_000_000)
    work_link = clean_url(request.form.get("work_link", ""))
    details = {
        "start_date": request.form.get("start_date", "") if request.form.get("start_date") in START_OPTIONS else "",
        "hours_per_week": request.form.get("hours_per_week", "") if request.form.get("hours_per_week") in HOURS_OPTIONS else "",
        "work_link": work_link or "",
    }
    error = None
    if len(cover_letter) < 20:
        error = "Write at least a few sentences so the client knows why you fit."
    elif len(cover_letter) > 5000:
        error = "Keep the letter under 5,000 characters."
    elif proposed is None:
        error = "Enter a proposed rate as a whole number."
    elif work_link is None:
        error = "Check the work sample link. It should look like example.com/project."
    if error:
        return render_template("job.html", job=job, existing=None, error=error), 400
    created = db.create_application(job_id, user["id"], cover_letter, proposed, details)
    if not created:
        flash("You already applied to this job.", "error")
    else:
        flash("Application sent. The client can shortlist or hire you from their dashboard.", "ok")
    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/jobs/new", methods=["GET", "POST"])
@login_required
def new_job():
    user = current_user()
    if user["role"] != "client":
        flash("Only client accounts can post jobs.", "error")
        return redirect(url_for("jobs"))
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "")
        budget_type = request.form.get("budget_type", "")
        currency = request.form.get("currency", "")
        location = request.form.get("location", "").strip() or "Remote"
        skills = request.form.get("skills", "").strip()
        amount = _clean_int(request.form.get("budget_amount"), 1, 10_000_000)
        details = {
            "experience_level": request.form.get("experience_level", "") if request.form.get("experience_level") in EXPERIENCE_LEVELS else "",
            "duration": request.form.get("duration", "") if request.form.get("duration") in DURATIONS else "",
            "hours_per_week": request.form.get("hours_per_week", "") if request.form.get("hours_per_week") in HOURS_OPTIONS else "",
            "start_date": request.form.get("start_date", "") if request.form.get("start_date") in START_OPTIONS else "",
            "timezone": request.form.get("timezone", "").strip(),
            "how_to_apply": request.form.get("how_to_apply", "").strip(),
        }
        for key in JOB_LIST_FIELDS:
            details[key] = "\n".join(text_lines(request.form.get(key, "")))
        if not 6 <= len(title) <= 120:
            error = "Give the job a clear title."
        elif len(description) < 40:
            error = "Describe the work in enough detail that someone can decide to apply."
        elif category not in db.CATEGORIES:
            error = "Choose a category."
        elif budget_type not in db.BUDGET_TYPES:
            error = "Choose how you want to pay."
        elif currency not in db.CURRENCIES:
            error = "Choose USD or PHP."
        elif amount is None:
            error = "Enter a budget as a whole number."
        elif len(location) > 80 or len(skills) > 200:
            error = "Shorten the location or skills."
        elif len(details["timezone"]) > 80:
            error = "Shorten the time zone note."
        elif len(details["how_to_apply"]) > 500:
            error = "Keep the application instructions under 500 characters."
        elif any(len(details[key]) > 2000 or len(text_lines(details[key])) > 12 for key in JOB_LIST_FIELDS):
            error = "Keep each list to 12 points or fewer."
        else:
            job_id = db.create_job(
                user["id"], title, description, category, budget_type, amount, currency, location, skills, details
            )
            flash("Job posted. It is live on the board.", "ok")
            return redirect(url_for("job_detail", job_id=job_id))
    return render_template("post_job.html", error=error), (400 if error else 200)


@app.post("/jobs/<job_id>/status")
@login_required
def set_job_status(job_id):
    status = request.form.get("status", "")
    if not db.set_job_status(job_id, current_user()["id"], status):
        abort(403)
    flash("Job updated.", "ok")
    return redirect(request.referrer or url_for("dashboard"))


@app.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user["role"] == "client":
        jobs = db.list_jobs(client_id=user["id"], include_closed=True)
        return render_template("dashboard.html", jobs=jobs, applications=[])
    applications = db.list_my_applications(user["id"])
    return render_template("dashboard.html", jobs=[], applications=applications)


@app.get("/dashboard/jobs/<job_id>")
@login_required
def review(job_id):
    job = db.get_job(job_id)
    if job is None:
        abort(404)
    if job["client_id"] != current_user()["id"]:
        abort(403)
    applications = db.list_job_applications(job_id)
    return render_template("review.html", job=job, applications=applications)


@app.post("/applications/<application_id>/status")
@login_required
def set_application_status(application_id):
    status = request.form.get("status", "")
    job_id = request.form.get("job_id", "")
    if not db.set_application_status(application_id, current_user()["id"], status):
        abort(403)
    flash(f"Marked as {STATUS_LABELS.get(status, status)}.", "ok")
    return redirect(url_for("review", job_id=job_id))


@app.post("/applications/<application_id>/review")
@login_required
def leave_review(application_id):
    rating = _clean_int(request.form.get("rating"), 1, 5)
    body = request.form.get("body", "").strip()
    back = request.form.get("back", "")
    destination = safe_next(back) or url_for("dashboard")
    if rating is None:
        flash("Pick a star rating from 1 to 5.", "error")
        return redirect(destination)
    if not 10 <= len(body) <= 1000:
        flash("Write a short review between 10 and 1,000 characters.", "error")
        return redirect(destination)
    error = db.create_review(application_id, current_user()["id"], rating, body)
    if error:
        flash(error, "error")
    else:
        flash("Thanks. Your review is on their profile now.", "ok")
    return redirect(destination)


def _form_rows(prefix, columns, limit):
    lists = [request.form.getlist(f"{prefix}_{column}") for column in columns]
    rows = []
    for values in zip(*lists):
        row = {column: value.strip() for column, value in zip(columns, values)}
        if any(row.values()):
            rows.append(row)
    return rows[:limit]


def _read_photo(upload):
    data = upload.read(PHOTO_LIMIT + 1)
    if len(data) > PHOTO_LIMIT:
        return None, "Choose a photo smaller than 4 MB."
    for magic, extension in PHOTO_TYPES.items():
        if data.startswith(magic) and (extension != "webp" or data[8:12] == b"WEBP"):
            return (data, extension), None
    return None, "Upload the photo as a JPG, PNG, or WebP image."


def _save_photo(user, data, extension):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = f"{user['id']}-{secrets.token_hex(4)}.{extension}"
    (UPLOADS / name).write_bytes(data)
    _delete_photo(user)
    return name


def _delete_photo(user):
    if user.get("photo"):
        (UPLOADS / user["photo"]).unlink(missing_ok=True)


def profile_checks(person, portfolio, certificates):
    checks = [
        ("Add a photo or logo", bool(person.get("photo"))),
        ("Write a one-line headline", bool(person.get("headline"))),
        ("Tell people about yourself", len(person.get("bio") or "") >= 80),
    ]
    if person["role"] == "freelancer":
        checks += [
            ("List your skills", bool(person.get("skills"))),
            ("Set your hourly rate", bool(person.get("rate"))),
            ("Show at least one portfolio project", bool(portfolio)),
            ("Add a certificate or training", bool(certificates)),
        ]
    else:
        checks += [
            ("Name your company", bool(person.get("company"))),
            ("Add your industry", bool(person.get("industry"))),
        ]
    link_keys = ("website", "linkedin", *db.SOCIAL_FIELDS)
    checks.append(("Link a website or social profile", any(person.get(key) for key in link_keys)))
    return checks


def _profile_form(user):
    form = request.form
    error = None
    is_freelancer = user["role"] == "freelancer"
    fields = {
        "name": form.get("name", "").strip(),
        "location": form.get("location", "").strip(),
        "headline": form.get("headline", "").strip(),
        "bio": form.get("bio", "").strip(),
        "languages": form.get("languages", "").strip(),
        "company": form.get("company", "").strip() if not is_freelancer else "",
        "industry": form.get("industry", "").strip() if not is_freelancer else "",
        "company_size": form.get("company_size", "") if form.get("company_size") in COMPANY_SIZES else "",
        "skills": form.get("skills", "").strip() if is_freelancer else "",
        "availability": form.get("availability", "") if form.get("availability") in AVAILABILITY_LABELS else "",
        "rate": None,
        "experience_years": None,
    }
    portfolio = _form_rows("portfolio", ("title", "url", "description"), MAX_PORTFOLIO) if is_freelancer else []
    certificates = _form_rows("cert", ("name", "issuer", "year", "url"), MAX_CERTIFICATES) if is_freelancer else []

    website = clean_url(form.get("website", ""))
    linkedin = clean_url(form.get("linkedin", ""))
    socials = {key: clean_social(form.get(key, ""), base) for key, _, base in SOCIAL_LINKS}
    bad_social = next((label for key, label, _ in SOCIAL_LINKS if socials[key] is None), None)
    rate_raw = form.get("rate", "").strip()
    years_raw = form.get("experience_years", "").strip()

    if len(fields["name"]) < 2 or len(fields["name"]) > 80:
        error = "Enter your name."
    elif any(len(fields[key]) > 120 for key in ("headline", "company", "location", "industry", "languages")):
        error = "Shorten one of the profile fields."
    elif len(fields["skills"]) > 200:
        error = "Keep your skills under 200 characters."
    elif len(fields["bio"]) > 2000:
        error = "Keep the About section under 2,000 characters."
    elif website is None or linkedin is None:
        error = "Check the website and LinkedIn links. They should look like example.com."
    elif bad_social:
        error = f"Check your {bad_social} link. Paste the full link or just your @username."
    elif is_freelancer and rate_raw and _clean_int(rate_raw, 1, 100_000) is None:
        error = "Enter an hourly rate as a whole number, or leave it blank."
    elif is_freelancer and years_raw and _clean_int(years_raw, 0, 60) is None:
        error = "Enter your years of experience as a number from 0 to 60."

    for item in portfolio:
        if error:
            break
        item["url"] = clean_url(item["url"])
        if not item["title"]:
            error = "Give every portfolio project a title, or clear the row."
        elif item["url"] is None:
            error = f"Check the link for “{item['title']}”. It should look like example.com/project."
        elif len(item["title"]) > 120 or len(item["description"]) > 600:
            error = f"Shorten the portfolio project “{item['title'][:40]}”."
    for item in certificates:
        if error:
            break
        item["url"] = clean_url(item["url"])
        year = _clean_int(item["year"], 1950, 2100) if item["year"] else None
        if not item["name"]:
            error = "Give every certificate a name, or clear the row."
        elif item["year"] and year is None:
            error = f"Enter the year for “{item['name']}” as four digits, like 2024."
        elif item["url"] is None:
            error = f"Check the link for “{item['name']}”. It should look like example.com/certificate."
        elif len(item["name"]) > 120 or len(item["issuer"]) > 120:
            error = f"Shorten the certificate “{item['name'][:40]}”."
        else:
            item["year"] = year

    if error is None:
        fields["website"] = website
        fields["linkedin"] = linkedin
        fields.update(socials)
        if is_freelancer:
            fields["rate"] = _clean_int(rate_raw, 1, 100_000) if rate_raw else None
            fields["experience_years"] = _clean_int(years_raw, 0, 60) if years_raw else None
        upload = request.files.get("photo")
        if upload and upload.filename:
            photo, error = _read_photo(upload)
            if photo:
                fields["photo"] = _save_photo(user, *photo)
        elif form.get("remove_photo") == "1":
            _delete_photo(user)
            fields["photo"] = ""
    return fields, portfolio, certificates, error


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    error = None
    if request.method == "POST":
        fields, portfolio, certificates, error = _profile_form(user)
        if error is None:
            is_freelancer = user["role"] == "freelancer"
            db.update_profile(
                user["id"],
                fields,
                portfolio if is_freelancer else None,
                certificates if is_freelancer else None,
            )
            flash("Profile saved. This is how others see you now.", "ok")
            return redirect(url_for("person", user_id=user["id"]))
    else:
        portfolio = db.list_portfolio(user["id"])
        certificates = db.list_certificates(user["id"])
    return render_template(
        "profile.html",
        error=error,
        portfolio=portfolio,
        certificates=certificates,
        checks=profile_checks(user, db.list_portfolio(user["id"]), db.list_certificates(user["id"])),
    ), (400 if error else 200)


@app.get("/media/<name>")
def media(name):
    return send_from_directory(UPLOADS, name, max_age=60 * 60 * 24 * 30)


@app.errorhandler(413)
def too_large(_exc):
    flash("That photo is too large. Choose one smaller than 4 MB.", "error")
    return redirect(url_for("profile"))


@app.get("/people/<user_id>")
def person(user_id):
    person_row = db.get_user(user_id)
    if person_row is None:
        abort(404)
    their_jobs = []
    if person_row["role"] == "client":
        their_jobs = db.list_jobs(client_id=user_id, include_closed=False)
    return render_template(
        "person.html",
        person=person_row,
        portfolio=db.list_portfolio(user_id),
        certificates=db.list_certificates(user_id),
        jobs=their_jobs,
        reviews=db.list_reviews_for(user_id),
        rating=db.rating_summary(user_id),
    )


@app.errorhandler(404)
def not_found(_exc):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(_exc):
    flash("That page belongs to another account.", "error")
    return redirect(url_for("dashboard"))


db.init_db()


def site_url(port):
    host = os.environ.get("HANAP_DOMAIN") or "127.0.0.1"
    return f"http://{host}" if port == 80 else f"http://{host}:{port}"


def open_browser_when_ready(port):
    def wait_then_open():
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        webbrowser.open(site_url(port) + "/")

    threading.Thread(target=wait_then_open, daemon=True).start()


BROWSER_BLOCKED_PORTS = {5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697}


def first_free_port(preferred):
    for port in range(preferred, preferred + 20):
        if port in BROWSER_BLOCKED_PORTS:
            continue
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                continue
        except OSError:
            return port
    return preferred


if __name__ == "__main__":
    port = int(os.environ.get("HANAP_PORT", "5050"))
    if os.environ.get("WERKZEUG_RUN_MAIN") is None:
        port = first_free_port(port)
        os.environ["HANAP_PORT"] = str(port)
    debug = os.environ.get("HANAP_DEBUG") == "1"
    print(f"\n  Amazing Assistant Online is running at {site_url(port)}\n  Keep this window open. Press Ctrl+C to stop.\n")
    if os.environ.get("HANAP_OPEN_BROWSER") == "1" and os.environ.get("WERKZEUG_RUN_MAIN") is None:
        open_browser_when_ready(port)
    app.run(host="127.0.0.1", port=port, debug=debug)
