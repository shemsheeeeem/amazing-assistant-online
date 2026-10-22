"""Turn the Care Netlify export into paste-ready code for GoHighLevel (GHL).

Run after export_netlify.py has built the Care Netlify folder:
      .venv\\Scripts\\python.exe export_ghl.py
Output: ..\\Amazing-Assistant-Online-GHL\\
"""

import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "Amazing-Assistant-Online-Care-Netlify"
OUT = HERE.parent / "Amazing-Assistant-Online-GHL"

BODY = re.compile(r'<body class="([^"]*)">(.*)</body>', re.S)
SCRIPT_TAG = re.compile(r"\s*<script\b[^>]*>.*?</script>", re.S)
JOB_META = re.compile(r"<script>window\.JOB_META=(\{.*?\});</script>", re.S)
LOCAL_URL = re.compile(r'(href|action)="(/(?!/)[^"?#]*)([^"]*)"')
FONT_LINKS = re.compile(r'\s*<link rel="preconnect"[^>]*>|\s*<link href="https://fonts[^>]*>')


def slug(path):
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    if parts[0] == "jobs" and len(parts) == 2:
        return "job-" + parts[1].removeprefix("j_").replace("_", "-")
    if parts[0] == "people" and len(parts) == 2:
        return "talent-" + parts[1].removeprefix("u_").replace("_", "-")
    return "-".join(parts)


def page_path(file):
    rel = file.relative_to(SRC).parent.as_posix()
    return "/" if rel == "." else "/" + rel


def relink(html):
    return LOCAL_URL.sub(lambda m: f'{m.group(1)}="/{slug(m.group(2))}{m.group(3)}"', html)


def convert(file, header, footer):
    html = file.read_text(encoding="utf-8")
    body_class, body = BODY.search(html).groups()

    meta = JOB_META.search(body)
    extra = ""
    if meta:
        jobs = {slug(f"/jobs/{key}"): value for key, value in json.loads(meta.group(1)).items()}
        extra = f"<script>window.JOB_META={json.dumps(jobs)};</script>\n"

    body = SCRIPT_TAG.sub("", body).strip()
    body = relink(body)
    classes = json.dumps(body_class.split())
    return (
        f"{header}"
        f"<script>document.body.classList.add.apply(document.body.classList, {classes});</script>\n"
        f"{extra}{body}\n"
        f"{footer}"
    )


def site_header(index_html):
    fonts = "".join(m.group(0) for m in FONT_LINKS.finditer(index_html)).strip()
    css = (SRC / "static" / "styles.css").read_text(encoding="utf-8")
    css += "\n" + (SRC / "static" / "care.css").read_text(encoding="utf-8")
    return f"{fonts}\n<style>\n{css}\n</style>\n"


def site_footer():
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


ORDER = ["/", "/jobs", "/signup", "/login"]


def main():
    if not SRC.exists():
        raise SystemExit(f"Build the Care Netlify folder first: {SRC}")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "pages").mkdir(parents=True)

    files = {page_path(f): f for f in SRC.rglob("index.html")}
    paths = ORDER + sorted(p for p in files if p not in ORDER)
    header = site_header(files["/"].read_text(encoding="utf-8"))
    footer = site_footer()

    rows = []
    for number, path in enumerate(paths, 1):
        name = slug(path) or "home"
        target = OUT / "pages" / f"{number:02d}-{name}.html"
        target.write_text(convert(files[path], header, footer), encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", files[path].read_text(encoding="utf-8"), re.S).group(1).strip()
        rows.append((target.name, "(set as Home page)" if path == "/" else "/" + slug(path), title))

    width = max(len(r[0]) for r in rows) + 3
    table = "\n".join(f"  {file:<{width}}{path:<22}{title}" for file, path, title in rows)
    (OUT / "README.txt").write_text(README.format(table=table, count=len(rows)), encoding="utf-8", newline="\r\n")
    print(f"Wrote {len(rows)} GHL pages to {OUT}")


README = """Amazing Assistant Online - GoHighLevel (GHL) files
====================================================

GHL does not take uploaded files. You paste code into it. Every file in the
pages folder is complete on its own: styling, page content, and animations are
all inside it. One file = one GHL page = one paste.


STEP 1 - Create the website
  In GHL go to Sites > Websites (or Funnels) and create a new, blank website.
  If you pasted code into the website's "Head tracking code" or "Body tracking
  code" earlier, remove it. It is no longer needed.

STEP 2 - Create the {count} pages
  For each file in the table below:
  a. Add a new page with the name shown, and set its URL path exactly as
     shown. The links between pages depend on these paths.
  b. Open the page in the builder and delete any sample sections.
  c. Add one Section, set it to Full width, and set its top, bottom, left,
     and right padding to 0. Do the same for the Row and Column inside it.
  d. Drag in a "Custom JS/HTML" (Code) element. Open the page file in Notepad,
     press Ctrl+A then Ctrl+C to copy ALL of it, paste it into the element,
     and save. The file is long; make sure nothing at the top or bottom is
     left out.
  e. In the page settings, use the title shown as the page title (SEO).

  File                         URL path              Page title
{table}

  Set 01-home as the website's Home page so it opens at your domain.

STEP 3 - Publish and check
  Publish, open the live site, and click through the menu, a job, and a
  freelancer profile. Animations only run on the published page, not inside
  the editor.


WHAT WORKS ON GHL
  All pages, links, animations, the reviews carousel, and the job search and
  filters on the Jobs page.

WHAT DOES NOT
  Signing up, logging in, posting jobs, applying, and leaving reviews need the
  full app (run.bat), because GHL pages cannot store accounts. On GHL these
  forms show a short "This is a preview" message instead. To collect real
  sign-ups on GHL, replace the forms on the signup and login pages with a
  GHL Form element.
"""


if __name__ == "__main__":
    main()
