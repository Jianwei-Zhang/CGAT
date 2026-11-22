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
CSS = "body{font:16px system-ui;margin:1.5em;color:#17212b}table{border-collapse:collapse;width:100%}td,th{padding:.5em;border:1px solid #ccd3db;text-align:left}a{color:#175ba0}code{overflow-wrap:anywhere}iframe{width:100%;height:85vh;border:1px solid #ccd3db}.note{padding:1em;background:#eef5ff}"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def page(title, body, *, wrapper=False):
    csp = WRAPPER_CSP if wrapper else CSP.replace("script-src 'unsafe-inline'", "script-src 'none'")
    return ("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            + '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
            + "<title>" + escape(title) + "</title><style>" + CSS + "</style></head><body><h1>"
            + escape(title) + "</h1>" + body + "</body></html>").encode()


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
                    '<p>' + escape(name) + '</p><p>' + escape(availability) +
                    '</p><p>No native result is invented. See the CGAT job/raw diagnostics navigation. '
                    '/ 未伪造原生结果；请查看 CGAT 的任务与原始诊断入口。</p>')
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
        body = ('<p><a href="index.html">Native visualization index / 原生可视化目录</a> · '
                '<a href="../' + diagnostics_page + '">CGAT job diagnostics / CGAT 任务诊断</a></p>'
                '<p>Source binding / 来源绑定: ' + escape(source_kinds) + '</p>'
                '<p class="note">Native visualization is not accepted/final sequence or biological validation. '
                '/ 原生可视化不等于接纳、最终序列或生物学验证。</p>'
                '<iframe title="' + escape(name, quote=True) + '" sandbox="allow-scripts" referrerpolicy="no-referrer" src="pages/'
                + quote(name) + '"></iframe>')
        files[wrapper] = page(name, body, wrapper=True)
    groups = [entries[i:i + page_size] for i in range(0, len(entries), page_size)] or [[]]
    for index, group in enumerate(groups):
        body = '<p><a href="../' + diagnostics_page + '">CGAT native jobs and raw diagnostics / 原生任务与原始诊断</a></p>'
        body += '<p class="note">' + escape(reason) + ' / Native tool reports and CGAT acceptance are separate.</p>'
        body += '<table><thead><tr><th>Native report</th><th>Availability</th><th>Source binding</th><th>Original source</th></tr></thead><tbody>'
        for row in group:
            name = '<a href="' + row["wrapper_path"].removeprefix(HOME + "/") + '">' + escape(row["name"]) + '</a>' if "wrapper_path" in row else escape(row["name"])
            links = ' · '.join('<a href="' + source["raw_report_path"] + '">HTML source / HTML 原文</a> <code>' + source["sha256"] + '</code>' for source in row["sources"] if source["raw_report_path"])
            body += '<tr><td>' + name + '</td><td>' + escape(row["availability"]) + ('<br>' + escape(row['reason']) if row.get('reason') else '') + '</td><td>' + escape(source_labels(row)) + '</td><td>' + links + '</td></tr>'
        body += '</tbody></table><p>' + ' · '.join('<a href="' + ("index.html" if i == 0 else "index-" + str(i + 1) + ".html") + '">' + str(i + 1) + '</a>' for i in nearby_pages(index, len(groups))) + '</p>'
        files["index.html" if index == 0 else "index-" + str(index + 1) + ".html"] = page("Native visualizations / 原生可视化", body)
    binding = {"schema": SCHEMA, "schema_version": 1, "tool": tool, "policy": lock["policy"],
               "policy_sha256": lock_sha, "helper_sha256": sha(Path(__file__).read_bytes()),
               "visualizer_files_sha256": lock["visualizer_files_sha256"], "reason": reason,
               "status": "available" if pages else "not_available", "views": entries,
               "files": {HOME + "/" + name: sha(content) for name, content in sorted(files.items())}}
    files["manifest.json"] = encoded(binding)
    return ViewPlan(binding, files)
