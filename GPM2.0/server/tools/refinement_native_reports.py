"""Managed, bounded offline display copies of the pinned native DEGAP reports.

Original HTML remains an inert hashed attachment. This module is presentation
only: no native command/checkpoint, scientific acceptance or source path changes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

SCHEMA = "cgat.native-report-view"
HOME = "native_visualization"
GLOBAL = "Global.report.html"
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; "
       "base-uri 'none'; form-action 'none'")
WRAPPER_CSP = ("default-src 'none'; style-src 'unsafe-inline'; frame-src 'self' file:; "
               "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
CSS = """
:root{
  color-scheme:light;
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
  font-size:14px;
  --font-mono:ui-monospace,"Cascadia Code",Consolas,monospace;
  --card-radius:6px;--control-radius:5px;
  --surface-app:#f1f5f9;--surface-panel:#ffffff;--surface-subtle:#f8fafc;--surface-muted:#eef2f6;
  --border-subtle:#dbe3ec;--border-default:#cbd5e1;--border-strong:#94a3b8;
  --text-primary:#1e293b;--text-secondary:#334155;--text-muted:#64748b;
  --accent:#2563eb;--action-primary-bg:#234b76;--focus-ring:#4f82b5;
  --shadow-xs:0 1px 2px rgba(15,23,42,.04);
  --tone-ok-ink:#166534;--tone-ok-bg:#ecfdf5;--tone-ok-line:#86efac;
  --tone-warn-ink:#92400e;--tone-warn-bg:#fffbeb;--tone-warn-line:#f59e0b;
  --tone-err-ink:#991b1b;--tone-err-bg:#fef2f2;--tone-err-line:#fca5a5;
  --tone-info-ink:#1e40af;--tone-info-bg:#eff6ff;--tone-info-line:#93c5fd;
  --tone-neutral-ink:#334155;--tone-neutral-bg:#eef2f6;--tone-neutral-line:#cbd5e1;
}
@media (prefers-color-scheme:dark){
  :root{
    color-scheme:dark;
    --surface-app:#101720;--surface-panel:#17212e;--surface-subtle:#1d2938;--surface-muted:#243244;
    --border-subtle:#344458;--border-default:#42546a;--border-strong:#748ba5;
    --text-primary:#e5edf7;--text-secondary:#c7d5e6;--text-muted:#9bacc1;
    --accent:#8abaff;--action-primary-bg:#2f5f92;--focus-ring:#91bfff;
    --shadow-xs:0 1px 2px #0003;
    --tone-ok-ink:#a2dfb3;--tone-ok-bg:#20382d;--tone-ok-line:#77b38b;
    --tone-warn-ink:#f4d098;--tone-warn-bg:#3a3022;--tone-warn-line:#b79966;
    --tone-err-ink:#ffb4ae;--tone-err-bg:#422b31;--tone-err-line:#c68989;
    --tone-info-ink:#a6ccff;--tone-info-bg:#253d57;--tone-info-line:#7fa4d1;
    --tone-neutral-ink:#c7d5e6;--tone-neutral-bg:#243244;--tone-neutral-line:#42546a;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-app);color:var(--text-primary);line-height:1.5}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:3px}
code{font-family:var(--font-mono);font-size:.88em;background:var(--surface-muted);padding:.1em .35em;border-radius:4px;overflow-wrap:anywhere}
h1,p{margin:0}h1{font-size:1.35rem;line-height:1.25}p{margin:.35rem 0}
.cgat-header{background:var(--surface-panel);border-top:3px solid var(--action-primary-bg);border-bottom:1px solid var(--border-default);box-shadow:var(--shadow-xs)}
.cgat-header-inner,.cgat-main{max-width:1240px;margin:0 auto;padding:.85rem 1.2rem}
.is-wrapper .cgat-header-inner,.is-wrapper .cgat-main{max-width:1440px}
.cgat-eyebrow{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.3rem}
.scope-pill{display:inline-flex;align-items:center;padding:.12rem .5rem;border-radius:4px;font-size:.75rem;font-weight:600;letter-spacing:.03em;text-transform:uppercase;background:var(--surface-muted);color:var(--text-secondary);border:1px solid var(--border-default)}
.cgat-title-row{display:flex;align-items:center;justify-content:space-between;gap:.65rem;flex-wrap:wrap}
.cgat-nav{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:.65rem;padding-top:.6rem;border-top:1px solid var(--border-subtle);align-items:center}
.cgat-nav a{display:inline-flex;align-items:center;padding:.24rem .6rem;border-radius:var(--control-radius);border:1px solid var(--border-default);background:var(--surface-subtle);color:var(--text-primary);font-size:.86rem;font-weight:500}
.cgat-nav a:hover{border-color:var(--border-strong);background:var(--surface-muted);text-decoration:none}
.cgat-main{padding-top:1rem;padding-bottom:1.5rem;display:flex;flex-direction:column;gap:.8rem}
.panel{background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--card-radius);padding:.9rem 1.05rem;box-shadow:var(--shadow-xs)}
.note{border-left:3px solid var(--tone-info-line);background:var(--tone-info-bg);color:var(--text-primary);padding:.6rem .85rem;border-radius:0 var(--card-radius) var(--card-radius) 0;font-size:.9rem}
.note.is-warn{border-left-color:var(--tone-warn-line);background:var(--tone-warn-bg)}
.badge{display:inline-flex;align-items:center;padding:.14rem .5rem;border-radius:999px;font-size:.78rem;font-weight:600;border:1px solid transparent;white-space:nowrap}
.tone-ok{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border-color:var(--tone-ok-line)}
.tone-warn{color:var(--tone-warn-ink);background:var(--tone-warn-bg);border-color:var(--tone-warn-line)}
.tone-err{color:var(--tone-err-ink);background:var(--tone-err-bg);border-color:var(--tone-err-line)}
.tone-info{color:var(--tone-info-ink);background:var(--tone-info-bg);border-color:var(--tone-info-line)}
.tone-neutral{color:var(--tone-neutral-ink);background:var(--tone-neutral-bg);border-color:var(--tone-neutral-line)}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-panel)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.55rem .7rem;border-bottom:1px solid var(--border-subtle);text-align:left;vertical-align:top}
th{background:var(--surface-subtle);color:var(--text-secondary);font-weight:600;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}tbody tr:hover{background:var(--surface-subtle)}
td{overflow-wrap:anywhere}
iframe{display:block;width:100%;height:82vh;min-height:480px;border:1px solid var(--border-default);border-radius:var(--card-radius);background:#fff}
.pager{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center;margin-top:.25rem}
.pager a,.pager span.is-current{padding:.22rem .55rem;border:1px solid var(--border-default);border-radius:4px;background:var(--surface-subtle);font-size:.85rem;font-variant-numeric:tabular-nums}
.pager span.is-current{background:var(--action-primary-bg);color:#fff;border-color:var(--action-primary-bg);font-weight:600}
.muted{color:var(--text-muted);font-size:.85rem}
@media (max-width:760px){.cgat-header-inner,.cgat-main{padding-left:.8rem;padding-right:.8rem}iframe{height:76vh;min-height:360px}}
"""

COMPACT_CSS = (
    ":root{color-scheme:light dark;font:14px/1.5 system-ui,-apple-system,sans-serif}"
    "body{margin:0;padding:1rem 1.25rem;background:#f1f5f9;color:#1e293b}"
    "@media(prefers-color-scheme:dark){body{background:#101720;color:#e5edf7}.card{background:#17212e;border-color:#42546a}}"
    ".card{max-width:720px;background:#fff;border:1px solid #cbd5e1;border-top:3px solid #234b76;border-radius:6px;padding:1rem 1.15rem}"
    "h1{font-size:1.15rem;margin:0 0 .5rem}p{margin:.35rem 0}code{font-family:ui-monospace,monospace;font-size:.9em}"
)

AVAILABILITY_TONES = {
    "offline_interactive": ("Offline interactive / 离线交互视图", "ok"),
    "native_report_not_generated": ("Not generated / 未生成原生报告", "neutral"),
    "server_only_display_size_limit": ("Server-only (display size limit) / 仅服务器（超展示体积）", "warn"),
    "server_only_size_limit": ("Server-only (size limit) / 仅服务器（超体积限制）", "warn"),
    "unsupported_native_display": ("Unsupported display / 不支持离线展示", "err"),
    "conflicting_native_report_copies": ("Conflicting copies / 存在冲突副本", "err"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def availability_badge(value):
    label, tone = AVAILABILITY_TONES.get(value, (str(value), "neutral"))
    return (
        '<span class="badge tone-' + escape(tone, quote=True) + '">'
        + escape(label) + '</span>'
    )


def page(title, body, *, wrapper=False, scope=None, subtitle=None, nav=None, badge=None, compact=False):
    csp = WRAPPER_CSP if wrapper else CSP.replace("script-src 'unsafe-inline'", "script-src 'none'")
    if compact:
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
            '<title>' + escape(title) + '</title><style>' + COMPACT_CSS + '</style></head>'
            '<body><div class="card"><h1>' + escape(title) + '</h1>' + body + '</div></body></html>'
        ).encode()
    eyebrow = '<div class="cgat-eyebrow"><span class="scope-pill">' + escape(scope) + '</span></div>' if scope else ""
    sub_html = '<p class="muted">' + subtitle + '</p>' if subtitle else ""
    nav_html = '<nav class="cgat-nav" aria-label="Native view navigation">' + nav + '</nav>' if nav else ""
    body_cls = ' class="is-wrapper"' if wrapper else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
        '<title>' + escape(title) + '</title><style>' + CSS + '</style></head>'
        '<body' + body_cls + '><header class="cgat-header"><div class="cgat-header-inner">'
        + eyebrow
        + '<div class="cgat-title-row"><h1>' + escape(title) + '</h1>' + (badge or "") + '</div>'
        + sub_html + nav_html
        + '</div></header><main class="cgat-main">' + body + '</main></body></html>'
    ).encode()


def source_labels(row):
    labels = {"observed_diagnostic": "Observed when reporting / 报告时观察",
              "sealed_native_artifact": "Native completion-bound / 原生完成回执绑定"}
    return " / ".join(labels[value] for value in sorted({source["binding"] for source in row["sources"]}))


def nearby_pages(index, count):
    # Constant-size navigation, not an all-pages link list on every page.
    return sorted(value for value in {0, count - 1, index - 1, index, index + 1} if 0 <= value < count)


class UnsupportedView(ValueError):
    pass


def check_css(text, inline_images):
    if re.search(r"@import", text, re.I):
        raise UnsupportedView("native stylesheet imports another resource")
    for match in re.finditer(r"url\(\s*(?:'([^']*)'|\"([^\"]*)\"|([^)]*))\s*\)", text, re.I):
        value = next(value for value in match.groups() if value is not None).strip()
        if not value.startswith("#") and value not in inline_images:
            raise UnsupportedView("native stylesheet requires an unapproved resource")


class Inspector(HTMLParser):
    """Validate native resources and remove only the known unused CDN tag."""
    def __init__(self, text, unused_scripts, local_pages, inline_images=()):
        super().__init__(convert_charrefs=False)
        self.text, self.unused, self.local_pages = text, set(unused_scripts), set(local_pages)
        self.inline_images = set(inline_images)
        self.offsets, offset = [], 0
        for line in text.splitlines(keepends=True):
            self.offsets.append(offset)
            offset += len(line)
        self.patches, self.script, self.scripts = [], None, []
        self.head_end, self.body_end, self.title = None, None, False

    def position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        attrs = {key.lower(): value for key, value in attrs}
        if tag in {"iframe", "object", "embed", "base", "form", "frameset"}:
            raise UnsupportedView("unsupported embedded document or form: " + tag)
        if tag == "meta" and attrs.get("http-equiv", "").lower() not in {"", "content-type"}:
            raise UnsupportedView("unsupported native HTTP-equivalent directive")
        if tag == "head":
            self.head_end = self.position() + len(self.get_starttag_text())
        if tag == "body":
            self.body_end = self.position() + len(self.get_starttag_text())
        if tag == "title":
            self.title = True
        if tag == "script":
            if self.script is not None:
                raise UnsupportedView("nested script element")
            source = attrs.get("src")
            if source is not None and source not in self.unused:
                raise UnsupportedView("unapproved external script: " + str(source))
            if attrs.get("type", "").lower() not in {"", "text/javascript", "application/javascript"}:
                raise UnsupportedView("unsupported script mode")
            self.script = {"start": self.position(), "source": source, "body": []}
        for name in ("src", "href", "xlink:href", "poster", "data", "action", "formaction"):
            value = attrs.get(name)
            if value is None or (tag == "script" and name == "src"):
                continue
            if value.startswith("#") or value == "":
                continue
            if tag == "a" and name == "href":
                parsed = urlsplit(value)
                if not parsed.scheme and not parsed.netloc and parsed.path in self.local_pages:
                    continue
            if tag == "img" and name == "src" and value.startswith(("data:image/png;", "data:image/jpeg;")):
                continue
            raise UnsupportedView("unclosed or external native resource: " + name + "=" + value)
        style = attrs.get("style", "")
        check_css(style, self.inline_images)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "script":
            self.handle_endtag(tag)

    def handle_data(self, value):
        if self.script is not None:
            self.script["body"].append(value)

    def handle_endtag(self, tag):
        if tag != "script" or self.script is None:
            return
        current, self.script = self.script, None
        body = "".join(current["body"])
        if current["source"] is not None:
            if body.strip():
                raise UnsupportedView("external script also contains inline code")
            end = self.text.find(">", self.position())
            if end < 0:
                raise UnsupportedView("unterminated external script")
            self.patches.append((current["start"], end + 1, ""))
        else:
            self.scripts.append(body)


def transform(raw, unused_scripts, local_pages, inline_images=()):
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise UnsupportedView("native report is not UTF-8") from error
    inspect = Inspector(text, unused_scripts, local_pages, inline_images)
    inspect.feed(text)
    inspect.close()
    if inspect.script is not None or inspect.head_end is None or inspect.body_end is None or not inspect.title:
        raise UnsupportedView("native HTML document is incomplete")
    scripts = "\n".join(inspect.scripts)
    if re.search(r"\b(?:new\s+)?Chart\s*[.(]", scripts):
        raise UnsupportedView("Chart.js is no longer unused; requires another reviewed policy")
    if re.search(r"\b(?:fetch|importScripts|XMLHttpRequest|WebSocket|EventSource|Worker|SharedWorker)\s*\(|"
                 r"(?:window\s*\.\s*open|(?:window|document)\s*\.\s*location|navigator\s*\.\s*sendBeacon)|"
                 r"\b(?:localStorage|sessionStorage)\s*[.\[]", scripts):
        raise UnsupportedView("native JavaScript requires unsupported browser/network capabilities")
    check_css("\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I)), set(inline_images))
    insert = '<meta http-equiv="Content-Security-Policy" content="' + escape(CSP, quote=True) + '">'
    note = ('<div style="padding:.7em;background:#eef5ff;color:#17212b;font:14px system-ui">'
            'Native tool visualization, not CGAT accepted/final sequence. Use the CGAT navigation above this frame. '
            '/ 原生工具可视化，不是 CGAT 接纳或最终序列；请使用框架上方的 CGAT 导航。</div>')
    patches = [*inspect.patches, (inspect.head_end, inspect.head_end, insert),
               (inspect.body_end, inspect.body_end, note)]
    for start, end, replacement in sorted(patches, reverse=True):
        text = text[:start] + replacement + text[end:]
    # Upstream creates its detail links inside a JS template string. Stay in
    # the existing sandbox instead of asking it for prohibited popup windows.
    text = re.sub(r'target\s*=\s*([\'"])_blank\1', 'target="_self"', text, flags=re.I)
    return text.encode(), {"removed_unused_external_scripts": len(inspect.patches),
                           "csp": CSP, "popup_links": "same-frame", "scripts": len(inspect.scripts)}


def component(value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in {".", ".."}:
        raise UnsupportedView("unsupported native visualization filename component")
    return value


def detail_name(chromosome, gap_id, direction):
    if chromosome is None or gap_id is None or direction not in {"left", "right"}:
        raise UnsupportedView("unknown native direction")
    return component(chromosome) + "." + component(gap_id) + "." + direction + ".html"


def global_details(raw, source_gaps):
    """Close links against the HTML's own embedded data, not a guessed tree."""
    text = raw.decode("utf-8", errors="strict")
    match = re.search(r"\bconst\s+gapsByChrom\s*=\s*", text)
    if match is None:
        raise UnsupportedView("native overview has no pinned embedded gap-data declaration")
    try:
        value, _end = json.JSONDecoder().raw_decode(text[match.end():])
        embedded = []
        for chrom, group in value.items():
            for gap in group["gaps"]:
                if gap.get("chromosome") != chrom:
                    raise UnsupportedView("native overview chromosome/group disagrees")
                embedded.append(gap)
        def identities(rows):
            return sorted(json.dumps(row, sort_keys=True) for row in rows)
        if source_gaps and identities(embedded) != identities(source_gaps):
            raise UnsupportedView("native overview data differs from current native gap diagnostics")
        return {detail_name(row["chromosome"], row["gap_id"], row.get("fill_direction")
                            if row.get("filled") and row.get("fill_direction") else "left") for row in embedded}
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise UnsupportedView("unusable native overview gap data: " + str(error)) from error


def policy():
    server = Path(__file__).resolve().parents[1]
    path = server / "contracts/refinement-native-reports.lock.json"
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("schema") != "cgat.native-report-policy" or value.get("schema_version") != 1:
        raise ValueError("invalid native report policy")
    for name, expected in value["visualizer_files_sha256"].items():
        if Path(name).name != name or sha((server / "tools/degap_core/bin" / name).read_bytes()) != expected:
            raise ValueError("native visualizer source changed; review report policy: " + name)
    return value, sha(raw)


@dataclass
class ViewPlan:
    binding: dict
    files: dict[str, bytes]

    def write(self, directory):
        for name, content in self.files.items():
            target = directory / HOME / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def prepare(tool, native, jobs, gaps, assets, read, *, remaining_budget, page_size=200, sealed=(), diagnostics_page="native.html"):
    """Plan a closed local display tree, consuming only selected bound HTML."""
    if diagnostics_page not in {"native.html", "report.html"}:
        raise ValueError("invalid CGAT report navigation target")
    lock, lock_sha = policy()
    sources = {row["workspace_path"]: row for row in assets}
    candidates, required = {}, set()
    def add(name, relative):
        if relative in sources:
            candidates.setdefault(name, []).append(sources[relative])
    reason = "not_generated_by_pinned_tool" if tool != "degap" else "native_report_not_generated"
    if tool == "degap":
        add(GLOBAL, native + "/05.visualization/" + GLOBAL)
        try:
            for gap in gaps:
                direction = gap.get("fill_direction") if gap.get("filled") and gap.get("fill_direction") else "left"
                name = detail_name(gap.get("chromosome"), gap.get("gap_id"), direction)
                add(name, native + "/05.visualization/" + name)
            for job in jobs:
                if job.get("visualization_html"):
                    name = detail_name(job["chromosome"], job["native_gap_id"], str(job["direction"]).lower())
                    add(name, job["visualization_html"])
        except UnsupportedView as error:
            # The original remains inert and accessible; do not rewrite source
            # identifiers to pretend a different report closure is equivalent.
            reason = str(error)
            candidates = {}
            required = set()
    global_raw, global_error = None, None
    if GLOBAL in candidates:
        first = candidates[GLOBAL][0]
        if "report_path" in first:
            try:
                global_raw = read(first["workspace_path"], first["sha256"])
                required.update(global_details(global_raw, gaps))
            except (UnsupportedView, UnicodeError) as error:
                global_error = str(error)
    names = {GLOBAL, *candidates, *required}
    entries, pages = [], {}
    for name in sorted({*candidates, *required}, key=lambda item: (item != GLOBAL, item)):
        choices = {row["workspace_path"]: row for row in candidates.get(name, [])}
        row = {"name": name, "sources": [{"workspace_path": r["workspace_path"], "sha256": r["sha256"],
                                          "binding": "sealed_native_artifact" if r["workspace_path"] in sealed else "observed_diagnostic",
                                          "raw_report_path": "../" + r["report_path"] if "report_path" in r else None}
                                         for r in choices.values()], "availability": "native_report_not_generated"}
        if name == GLOBAL:
            row["embedded_data_binding"] = "native_gap_diagnostics" if gaps else "native_html_only"
        if len({r["sha256"] for r in choices.values()}) > 1:
            row["availability"] = "conflicting_native_report_copies"
        elif choices:
            source = next(iter(choices.values()))
            if "report_path" not in source:
                row["availability"] = source["availability"]
            else:
                try:
                    if name == GLOBAL and global_error:
                        raise UnsupportedView(global_error)
                    raw = global_raw if name == GLOBAL else read(source["workspace_path"], source["sha256"])
                    content, changes = transform(raw, lock["unused_external_scripts"], names, lock["inline_data_images"])
                    row.update(availability="offline_interactive", transformations=changes)
                    pages[name] = content
                except UnsupportedView as error:
                    row.update(availability="unsupported_native_display", reason=str(error))
        entries.append(row)
    by_name = {row["name"]: row for row in entries}
    # Reserve a closed overview first. Each required detail has either its
    # actual native display or a truthful small placeholder. Large job bodies
    # may not evict the overview or strand its dynamically generated links.
    def placeholder(name):
        row = by_name[name]
        availability = "server_only_display_size_limit" if name in pages else row["availability"]
        return page("Native detail unavailable / 原生详情不可用",
                    '<p><code>' + escape(name) + '</code></p><p>Availability / 可用性: <code>' + escape(availability) +
                    '</code></p><p>No native result is invented. See the CGAT job/raw diagnostics navigation. '
                    '/ 未伪造原生结果；请查看 CGAT 的任务与原始诊断入口。</p>',
                    compact=True)
    budget, chosen, placeholders = max(0, remaining_budget), {}, {}
    if GLOBAL in pages:
        placeholders = {name: placeholder(name) for name in required}
        mandatory = len(pages[GLOBAL]) + sum(map(len, placeholders.values()))
        if mandatory <= budget:
            chosen[GLOBAL] = pages[GLOBAL]
            budget -= mandatory
        else:
            by_name[GLOBAL]["availability"] = "server_only_display_size_limit"
            placeholders = {}
    for name, content in pages.items():
        if name == GLOBAL:
            continue
        credit = len(placeholders.get(name, b""))
        if len(content) - credit <= budget:
            chosen[name] = content
            budget -= len(content) - credit
            placeholders.pop(name, None)
        else:
            by_name[name]["availability"] = "server_only_display_size_limit"
    pages = chosen
    if pages and reason == "native_report_not_generated":
        reason = "pinned_native_reports_observed"
    files = {"pages/" + name: content for name, content in {**pages, **placeholders}.items()}
    for row in entries:
        name = row["name"]
        if name not in pages:
            if name in placeholders:
                row["placeholder_path"] = HOME + "/pages/" + name
            continue
        wrapper = "view-" + sha(name.encode())[:20] + ".html"
        row.update(display_path=HOME + "/pages/" + name, wrapper_path=HOME + "/" + wrapper,
                   display_sha256=sha(pages[name]))
        source_kinds = source_labels(row)
        wrapper_nav = (
            '<a href="index.html">Native visualization index / 原生可视化目录</a>'
            '<a href="../' + escape(diagnostics_page, quote=True) + '">CGAT job diagnostics / CGAT 任务诊断</a>'
        )
        body = (
            '<p class="note is-warn">Native visualization is not accepted/final sequence or biological validation. '
            '/ 原生可视化不等于接纳、最终序列或生物学验证。</p>'
            '<iframe title="' + escape(name, quote=True) + '" sandbox="allow-scripts" referrerpolicy="no-referrer" src="pages/'
            + quote(name) + '"></iframe>'
        )
        files[wrapper] = page(
            name,
            body,
            wrapper=True,
            scope="CGAT Managed Native View / 离线原生视图封装",
            subtitle='Source binding / 来源绑定: ' + escape(source_kinds),
            nav=wrapper_nav,
            badge='<span class="badge tone-info">Sandboxed Offline / 离线沙盒</span>',
        )
    groups = [entries[i:i + page_size] for i in range(0, len(entries), page_size)] or [[]]
    for index, group in enumerate(groups):
        idx_nav = '<a href="../' + escape(diagnostics_page, quote=True) + '">CGAT native jobs and raw diagnostics / 原生任务与原始诊断</a>'
        body = (
            '<section class="panel">'
            '<p class="note">Status reason / 状态原因: <code>' + escape(reason) + '</code> — '
            'Native tool reports and CGAT acceptance are separate. / 原生工具报告与 CGAT 接纳相互独立。</p>'
            '<div class="table-wrap"><table><thead><tr>'
            '<th>Native report / 原生报告</th><th>Availability / 可用性</th>'
            '<th>Source binding / 来源绑定</th><th>Original source / 原始文件</th>'
            '</tr></thead><tbody>'
        )
        if not group:
            body += '<tr><td colspan="4" class="muted">No native visualization entries recorded. / 未记录原生可视化条目。</td></tr>'
        for row in group:
            name = (
                '<a href="' + escape(row["wrapper_path"].removeprefix(HOME + "/"), quote=True) + '"><strong>' + escape(row["name"]) + '</strong></a>'
                if "wrapper_path" in row else '<code>' + escape(row["name"]) + '</code>'
            )
            links = ' · '.join(
                '<a href="' + escape(source["raw_report_path"], quote=True) + '">HTML source / HTML 原文</a> <code>' + escape(source["sha256"]) + '</code>'
                for source in row["sources"] if source["raw_report_path"]
            ) or '<span class="muted">Not embedded / 未嵌入</span>'
            avail_html = availability_badge(row["availability"]) + (
                '<br><small class="muted">' + escape(row["reason"]) + '</small>' if row.get("reason") else ""
            )
            body += '<tr><td>' + name + '</td><td>' + avail_html + '</td><td>' + escape(source_labels(row)) + '</td><td>' + links + '</td></tr>'
        pager_items = []
        for i in nearby_pages(index, len(groups)):
            if i == index:
                pager_items.append('<span class="is-current">' + str(i + 1) + '</span>')
            else:
                href = "index.html" if i == 0 else "index-" + str(i + 1) + ".html"
                pager_items.append('<a href="' + href + '">' + str(i + 1) + '</a>')
        body += '</tbody></table></div><div class="pager">' + "".join(pager_items) + '</div></section>'
        files["index.html" if index == 0 else "index-" + str(index + 1) + ".html"] = page(
            "Native visualizations / 原生可视化",
            body,
            scope="CGAT Native Visualization Index / 原生可视化目录",
            subtitle=f'Tool: <code>{escape(str(tool))}</code> · Page {index + 1} / {len(groups)}',
            nav=idx_nav,
            badge='<span class="badge tone-' + ("ok" if pages else "neutral") + '">' + ("Available / 可用" if pages else "Not available / 不可用") + '</span>',
        )
    binding = {"schema": SCHEMA, "schema_version": 1, "tool": tool, "policy": lock["policy"],
               "policy_sha256": lock_sha, "helper_sha256": sha(Path(__file__).read_bytes()),
               "visualizer_files_sha256": lock["visualizer_files_sha256"], "reason": reason,
               "status": "available" if pages else "not_available", "views": entries,
               "files": {HOME + "/" + name: sha(content) for name, content in sorted(files.items())}}
    files["manifest.json"] = encoded(binding)
    return ViewPlan(binding, files)
