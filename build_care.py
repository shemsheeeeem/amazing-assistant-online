"""Build the Care-only edition of the site in its own folder.

Run:  .venv\\Scripts\\python.exe build_care.py
Output: ..\\Amazing-Assistant-Online-Care\\ and ..\\Amazing-Assistant-Online-Care.zip

Uses this project as the source and borrows run.bat, run.command and the
bundled python/ folder from ..\\Amazing-Assistant-Online\\.
"""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT.parent / "Amazing-Assistant-Online"
OUT = ROOT.parent / "Amazing-Assistant-Online-Care"
ZIP = OUT.with_suffix(".zip")
PORT = 5080


def edit(path, *pairs, regex=False):
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        updated = re.sub(old, new, text, flags=re.S) if regex else text.replace(old, new)
        if updated == text:
            raise SystemExit(f"Could not find the expected text in {path.name}: {old[:60]!r}")
        text = updated
    path.write_text(text, encoding="utf-8", newline="")


def build_folder():
    saved_data = None
    if (OUT / "data").exists():
        saved_data = Path(tempfile.mkdtemp()) / "data"
        shutil.move(str(OUT / "data"), saved_data)
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(exist_ok=True)
    if any(OUT.iterdir()):
        if saved_data:
            shutil.move(str(saved_data), OUT / "data")
        raise SystemExit(f"Close any window or program using {OUT} and run this again.")
    if saved_data:
        shutil.move(str(saved_data), OUT / "data")
    for name in ("app.py", "db.py", "requirements.txt"):
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copytree(ROOT / "templates", OUT / "templates")
    shutil.copytree(ROOT / "static", OUT / "static")
    for name in ("run.bat", "run.command", "README.txt"):
        shutil.copy2(PKG / name, OUT / name)
    shutil.copytree(PKG / "python", OUT / "python", ignore=shutil.ignore_patterns("__pycache__"))
    for script in (ROOT / "demo").glob("*.bat"):
        lines = script.read_text(encoding="utf-8").splitlines()
        (OUT / script.name).write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))

    for name in ("templates/home.html", "templates/home_loop.html", "static/loop.css"):
        (OUT / name).unlink()

    edit(
        OUT / "app.py",
        ('DESIGNS = ("classic", "loop", "care")', 'DESIGNS = ("care",)'),
        ('HOME_TEMPLATES = {"classic": "home.html", "loop": "home_loop.html", "care": "home_care.html"}',
         'HOME_TEMPLATES = {"care": "home_care.html"}'),
        ('return saved if saved in DESIGNS else "classic"', 'return saved if saved in DESIGNS else "care"'),
        ('os.environ.get("HANAP_PORT", "5050")', f'os.environ.get("HANAP_PORT", "{PORT}")'),
    )

    edit(
        OUT / "static" / "motion.js",
        (r"\.section-intro, \.lp-intro,", ".section-intro,"),
        (r'      "\.lp-card[^\n]*\n', ""),
        (r", \.lp-cta-inner > :not\(svg\)", ""),
        (r"    const steps = gsap\.utils\.toArray\(\"\.lp-steps li\"\);.*?(?=    const notes)", ""),
        (r"    gsap\.utils\.toArray\(\"\.lp-hero \.lp-doodle\"\).*?(?=    document\.fonts)", ""),
        regex=True,
    )

    edit(
        OUT / "templates" / "base.html",
        (r"  \{% if design == 'loop' %\}\n  <link href=\"https://fonts.googleapis.com/css2\?family=Space.*?\{% endif %\}\n",
         '  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">\n'),
        (r"  \{% if design == 'loop' %\}\n  <link rel=\"stylesheet\" href=\"\{\{ url_for\('static', filename='loop.css'\).*?\{% endif %\}\n",
         lambda m: re.search(r"  <link rel=\"stylesheet\" href=\"\{\{ url_for\('static', filename='care.css'\) \}\}\?v=\d+\">\n", m.group(0)).group(0)),
        (r"  <div class=\"design-switch\".*?</div>\n", ""),
        regex=True,
    )

    for page in (OUT / "templates").glob("*.html"):
        text = page.read_text(encoding="utf-8")
        updated = text.replace("<b>Amazing-Assistant-Online</b>", f"<b>{OUT.name}</b>").replace("127.0.0.1:5050", f"127.0.0.1:{PORT}")
        if updated != text:
            page.write_text(updated, encoding="utf-8", newline="")

    edit(
        OUT / "README.txt",
        ("127.0.0.1:5050", f"127.0.0.1:{PORT}"),
        ("1. Three designs: use the \"Design: Classic | Loop | Care\" switch in the bottom-right\n   corner of any page.\n", ""),
        ("2. As a client", "1. As a client"),
        ("3. As a freelancer", "2. As a freelancer"),
        ("4. Reviews:", "3. Reviews:"),
        ("5. Browse by category", "4. Browse by category"),
    )
    readme = OUT / "README.txt"
    readme.write_bytes(readme.read_bytes().rstrip() + DEMO_README.replace("\n", "\r\n").encode("ascii"))


DEMO_README = """


DEMO AT amazingassistantonline.com (Windows, this computer only)
-----------------------------------------------------------------
1-set-up-demo-domain.bat   Run once. Click "Yes" when Windows asks for permission.
                           Makes amazingassistantonline.com open this site on
                           this computer.
2-run-demo.bat             Starts the site and opens http://amazingassistantonline.com
3-reset-demo.bat           Deletes demo accounts and jobs and brings back the
                           sample data. Close the site's black window first.
4-remove-demo-domain.bat   Undo step 1 when you no longer need the demo address.

New accounts and jobs get readable addresses, for example
http://amazingassistantonline.com/people/juan-dela-cruz
The browser shows "Not secure" next to the address because the demo has no
HTTPS certificate. Everything else looks and works like a live site.
"""


def build_zip():
    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(OUT.rglob("*")):
            rel = path.relative_to(OUT)
            if "__pycache__" in rel.parts or rel.parts[0] == "data":
                continue
            name = f"{OUT.name}/{rel.as_posix()}"
            if path.is_dir():
                info = zipfile.ZipInfo(name + "/")
                info.external_attr = (0o40755 << 16) | 0x10
            else:
                info = zipfile.ZipInfo.from_file(path, name)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if path.name == "run.command" else 0o644
                info.external_attr = (0o100000 | mode) << 16
            info.create_system = 3
            z.writestr(info, b"" if path.is_dir() else path.read_bytes())
    with zipfile.ZipFile(ZIP) as z:
        bad = z.testzip()
        print(f"{ZIP} - {len(z.namelist())} entries, {ZIP.stat().st_size / 1048576:.1f} MB, {'OK' if bad is None else 'BAD: ' + bad}")


if __name__ == "__main__":
    build_folder()
    build_zip()
