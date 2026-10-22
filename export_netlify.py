"""Build a static, read-only preview of the site for Netlify.

Run:  .venv\\Scripts\\python.exe export_netlify.py
Output: ..\\Amazing-Assistant-Online-Netlify\\ (drag that folder onto Netlify)

Care-only edition:
      .venv\\Scripts\\python.exe export_netlify.py ..\\Amazing-Assistant-Online-Care ..\\Amazing-Assistant-Online-Care-Netlify
"""

import json
import re
import shutil
import sys
import tempfile
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
OUT = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT.parent / "Amazing-Assistant-Online-Netlify"
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

work = Path(tempfile.mkdtemp())
db.DB_PATH = work / "data" / "hanap.sqlite"

import app as site  # noqa: E402  (must load after DB_PATH points at a fresh sample database)

PREFIX = {design: "" if i == 0 else f"/{design}" for i, design in enumerate(site.DESIGNS)}

FILE_GUARD = re.compile(r'<script>if\(location\.protocol==="file:"\).*?</script>\s*', re.S)
SWITCH = re.compile(r'href="([^"?]*)\?design=(classic|loop|care)"')
LOCAL_URL = re.compile(r'(href|action)="(/(?!static/)[^"]*)"')
LINK = re.compile(r'href="(/[^"]*)"')

PREVIEW_JS = """(function () {
  var note = "This is a preview. Accounts, job posts, applications, and reviews work in the full version of Amazing Assistant Online.";

  function toast() {
    var box = document.querySelector(".preview-toast");
    if (!box) {
      box = document.createElement("div");
      box.className = "preview-toast";
      box.setAttribute("role", "status");
      box.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:9999;max-width:min(560px,calc(100% - 32px));padding:14px 18px;border-radius:14px;background:#0c2e5c;color:#fff;font:500 15px/1.5 system-ui,sans-serif;box-shadow:0 12px 32px rgba(0,0,0,.25)";
      document.body.appendChild(box);
    }
    box.textContent = note;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { box.remove(); }, 6000);
  }

  var params = new URLSearchParams(location.search);

  document.querySelectorAll('form[method="post"]').forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      toast();
    });
  });

  var role = params.get("role");
  if (role) {
    var radio = document.querySelector('input[name="role"][value="' + role + '"]');
    if (radio) radio.checked = true;
  }

  var filters = document.querySelector("form.filters");
  var meta = window.JOB_META;
  if (!filters || !meta) return;

  var grid = document.querySelector(".job-grid");
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".job-card"));
  var empty = document.createElement("p");
  empty.className = "empty";
  empty.textContent = "No roles match that filter.";

  function apply() {
    var q = (filters.q.value || "").trim().toLowerCase();
    var category = filters.category.value;
    var type = filters.budget_type.value;
    var shown = 0;
    cards.forEach(function (card) {
      var id = (card.getAttribute("href") || "").split("/").filter(Boolean).pop();
      var info = meta[id] || {};
      var ok = (!category || info.category === category) && (!type || info.type === type) &&
        (!q || card.textContent.toLowerCase().indexOf(q) !== -1 || (info.text || "").indexOf(q) !== -1);
      card.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    if (shown) empty.remove(); else grid.appendChild(empty);
  }

  ["q", "category", "budget_type"].forEach(function (name) {
    if (params.get(name)) filters[name].value = params.get(name);
  });
  filters.addEventListener("submit", function (event) {
    event.preventDefault();
    var next = new URLSearchParams();
    ["q", "category", "budget_type"].forEach(function (name) {
      if (filters[name].value) next.set(name, filters[name].value);
    });
    history.replaceState(null, "", location.pathname + (next.toString() ? "?" + next : ""));
    apply();
  });
  apply();
})();
"""


def out_file(prefix, path):
    parts = [p for p in (prefix + path).split("/") if p]
    return OUT.joinpath(*parts, "index.html")


def job_meta():
    meta = {}
    with site.app.app_context():
        jobs = [dict(job) for job in db.list_jobs()]
    for job in jobs:
        meta[job["id"]] = {
            "category": job["category"],
            "type": job["budget_type"],
            "text": " ".join(str(job.get(k) or "") for k in ("title", "skills", "description", "client_company", "client_name")).lower(),
        }
    return meta


def convert(html, design, meta=None):
    prefix = PREFIX[design]
    html = FILE_GUARD.sub("", html)
    html = SWITCH.sub(lambda m: f'href="@@{PREFIX[m.group(2)]}{m.group(1)}"', html)
    html = LOCAL_URL.sub(lambda m: f'{m.group(1)}="{prefix}{m.group(2)}"', html)
    html = html.replace('href="@@', 'href="')
    html = html.replace("Accounts live on this computer.", "Preview version. Accounts and posting work in the full version.")
    extra = ""
    if meta is not None:
        extra = f"<script>window.JOB_META={json.dumps(meta)};</script>\n"
    head, _, tail = html.rpartition("</body>")
    return f'{head}{extra}<script src="/static/preview.js" defer></script>\n</body>{tail}'


def crawl(design):
    client = site.app.test_client()
    client.get(f"/?design={design}")
    meta = job_meta()
    seen, queue, pages = set(), deque(["/", "/jobs", "/signup", "/login"]), 0
    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        response = client.get(path)
        if response.status_code != 200 or not response.mimetype.startswith("text/html"):
            continue
        html = response.get_data(as_text=True)
        for href in LINK.findall(html):
            target = urlsplit(href).path.rstrip("/") or "/"
            if not target.startswith(("/static", "/logout")) and target not in seen:
                queue.append(target)
        target_file = out_file(PREFIX[design], path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(convert(html, design, meta if path == "/jobs" else None), encoding="utf-8")
        pages += 1
    return pages


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT / "static")
    (OUT / "static" / "preview.js").write_text(PREVIEW_JS, encoding="utf-8")
    total = sum(crawl(design) for design in PREFIX)

    client = site.app.test_client()
    missing = convert(client.get("/this-page-does-not-exist").get_data(as_text=True), site.DESIGNS[0])
    missing = missing.replace('/this-page-does-not-exist"', '/"')
    (OUT / "404.html").write_text(missing, encoding="utf-8")
    print(f"Exported {total} pages to {OUT}")


if __name__ == "__main__":
    main()
