"""Build Care pages that open by double-click (no run.bat needed).

Run after the Care Netlify export exists:
      .venv\\Scripts\\python.exe export_netlify.py ..\\Amazing-Assistant-Online-Care ..\\Amazing-Assistant-Online-Care-Netlify
      .venv\\Scripts\\python.exe export_open.py

Output: ..\\Amazing-Assistant-Online-Care-Open\\
"""

import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "Amazing-Assistant-Online-Care-Netlify"
OUT = HERE.parent / "Amazing-Assistant-Online-Care-Open"

BODY = re.compile(r"<body class=\"([^\"]*)\">(.*)</body>", re.S)
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
SCRIPT_TAG = re.compile(r"\s*<script\b[^>]*>.*?</script>", re.S)
JOB_META = re.compile(r"<script>window\.JOB_META=(\{.*?\});</script>", re.S)
LOCAL_URL = re.compile(r'(href|action)="(/(?!/)[^"?#]*)([^"]*)"')
FONT_LINKS = re.compile(r'\s*<link rel="preconnect"[^>]*>|\s*<link href="https://fonts[^>]*>')

ORDER = ["/", "/jobs", "/signup", "/login"]


def slug(path):
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "home"
    if parts[0] == "jobs" and len(parts) == 2:
        return "job-" + parts[1].removeprefix("j_").replace("_", "-")
    if parts[0] == "people" and len(parts) == 2:
        return "talent-" + parts[1].removeprefix("u_").replace("_", "-")
    return "-".join(parts)


def page_path(file):
    rel = file.relative_to(SRC).parent.as_posix()
    return "/" if rel == "." else "/" + rel


def file_map(paths):
    return {path: f"{i:02d}-{slug(path)}.html" for i, path in enumerate(paths, 1)}


def relink(html, files):
    def replace(match):
        attr, path, rest = match.groups()
        name = files.get(path)
        if name is None:
            return match.group(0)
        return f'{attr}="{name}{rest}"'

    return LOCAL_URL.sub(replace, html)


def site_css(index_html):
    fonts = "".join(m.group(0) for m in FONT_LINKS.finditer(index_html)).strip()
    css = (SRC / "static" / "styles.css").read_text(encoding="utf-8")
    css += "\n" + (SRC / "static" / "care.css").read_text(encoding="utf-8")
    return f"{fonts}\n<style>\n{css}\n</style>\n"


def site_js():
    code = "\n".join(
        (SRC / "static" / name).read_text(encoding="utf-8") for name in ("motion.js", "care.js", "preview.js")
    )
    return (
        '<script src="https://cdn.jsdelivr.net/npm/gsap@3.13.0/dist/gsap.min.js"></script>\n'
        '<script src="https://cdn.jsdelivr.net/npm/gsap@3.13.0/dist/ScrollTrigger.min.js"></script>\n'
        "<script>\n"
        "(function () {\n"
        "  if (window.__aaoStarted) return;\n"
        "  window.__aaoStarted = true;\n"
        "  var tries = 0;\n"
        "  function start() {\n"
        f"{code}\n"
        "  }\n"
        "  function whenReady() {\n"
        "    var loaded = window.gsap && window.ScrollTrigger && document.querySelector('.site-header');\n"
        "    if (loaded || tries++ > 60) start();\n"
        "    else setTimeout(whenReady, 100);\n"
        "  }\n"
        "  whenReady();\n"
        "})();\n"
        "</script>\n"
    )


def convert(file, files, css, js):
    html = file.read_text(encoding="utf-8")
    title = TITLE.search(html).group(1).strip()
    body_class, body = BODY.search(html).groups()
    meta = JOB_META.search(body)
    extra = ""
    if meta:
        jobs = {files[f"/jobs/{key}"]: value for key, value in json.loads(meta.group(1)).items() if f"/jobs/{key}" in files}
        extra = f"<script>window.JOB_META={json.dumps(jobs)};</script>\n"
    body = SCRIPT_TAG.sub("", body).strip()
    body = relink(body, files)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"{css}"
        "</head>\n"
        f'<body class="{body_class}">\n'
        f"{extra}{body}\n"
        f"{js}"
        "</body>\n"
        "</html>\n"
    )


README = """Amazing Assistant Online Care - Open these files
================================================

These pages open on their own. Double-click any .html file. You do not need
run.bat or a black window.

Folder: {folder}

START HERE
  Double-click 01-home.html

PAGES
{table}

WHAT WORKS
  Browse home, jobs, profiles, and sample content. Job filters work.
  Links between these pages work.

WHAT DOES NOT
  Sign up, log in, posting, applying, and reviews need the full app.
  Use Amazing-Assistant-Online-Care\\run.bat for that.
  Forms here show a short preview message instead.

TIPS
  Keep every .html file in this same folder. Do not move one file out alone.
  If a page looks plain, open 01-home.html first and click through the menu.
"""


def main():
    if not SRC.exists():
        raise SystemExit(f"Build the Care Netlify folder first: {SRC}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    found = {page_path(f): f for f in SRC.rglob("index.html")}
    paths = ORDER + sorted(p for p in found if p not in ORDER)
    files = file_map(paths)
    css = site_css(found["/"].read_text(encoding="utf-8"))
    js = site_js()

    rows = []
    for path in paths:
        name = files[path]
        target = OUT / name
        target.write_text(convert(found[path], files, css, js), encoding="utf-8", newline="\n")
        title = TITLE.search(found[path].read_text(encoding="utf-8")).group(1).strip()
        rows.append((name, title))

    width = max(len(r[0]) for r in rows) + 3
    table = "\n".join(f"  {name:<{width}}{title}" for name, title in rows)
    (OUT / "README.txt").write_text(
        README.format(folder=OUT, table=table),
        encoding="utf-8",
        newline="\r\n",
    )
    print(f"Wrote {len(rows)} openable pages to {OUT}")


if __name__ == "__main__":
    main()
