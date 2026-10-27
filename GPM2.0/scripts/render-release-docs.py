#!/usr/bin/env python3
"""Render localized docs from tracked bilingual release notes; never edit GitHub.

Frontmatter values are JSON strings (a strict subset of YAML), so no dependency is
needed. Dates are ISO calendar dates; published dates follow GitHub's UTC date.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = ("en", "zh")


def read_release(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{path}: expected release frontmatter")
    header, body = text[4:].split("\n---\n", 1)
    metadata = {}
    for line in header.splitlines():
        key, value = line.split(":", 1)
        if key in metadata:
            raise ValueError(f"{path}: duplicate field {key}")
        metadata[key] = json.loads(value.strip())
    required = {"version", "published", "updated", "summary_en", "summary_zh"}
    if set(metadata) != required or any(not isinstance(v, str) or not v.strip() for v in metadata.values()):
        raise ValueError(f"{path}: expected non-empty metadata fields {sorted(required)}")
    version = metadata["version"]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version) or path.stem != version:
        raise ValueError(f"{path}: invalid version or filename")
    if date.fromisoformat(metadata["updated"]) < date.fromisoformat(metadata["published"]):
        raise ValueError(f"{path}: updated date precedes publication")
    if body.count("\n## English\n") != 1 or body.count("\n## 中文\n") != 1:
        raise ValueError(f"{path}: expected one English section, followed by one Chinese section")
    if body.index("\n## English\n") > body.index("\n## 中文\n"):
        raise ValueError(f"{path}: English must precede Chinese")
    en, zh = body.split("\n## English\n", 1)[1].split("\n## 中文\n", 1)
    for locale, content in (("en", en), ("zh", zh)):
        for heading in ("### Server", "### App", "### macOS first launch" if locale == "en" else "### macOS 首次启动"):
            if heading not in content:
                raise ValueError(f"{path}: missing {locale} heading {heading}")
        if content.index("### Server") > content.index("### App"):
            raise ValueError(f"{path}: Server must precede App")
        for notice in ("ARM64", "Apple Silicon", "ad-hoc", "xattr -dr com.apple.quarantine /Applications/GPM.app"):
            if notice not in content:
                raise ValueError(f"{path}: missing {locale} macOS notice {notice}")
    return {**metadata, "en": en.strip(), "zh": zh.strip(),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def release_body(release):
    """Export the same source for an authorized GitHub notes update, without metadata."""
    return release["en"] + "\n\n---\n\n" + release["zh"] + "\n"


def collect_releases(source):
    releases = [read_release(p) for p in source.glob("v*.md")]
    if not releases:
        raise ValueError(f"No release notes found in {source}")
    return sorted(releases, key=lambda r: tuple(map(int, r["version"][1:].split("."))), reverse=True)


def frontmatter(title, source_hash=None):
    lines = ["---", "title: " + json.dumps(title, ensure_ascii=False)]
    if source_hash:
        lines.append("release_source_sha256: " + json.dumps(source_hash))
        lines.append("pageClass: release-notes")
    return "\n".join(lines + ["---", "", "<!-- Generated from GPM2.0/releases; edit the tracked source, not this page. -->", ""])


def render_pages(releases):
    output = {}
    for locale in LANGUAGES:
        zh = locale == "zh"
        prefix = "/zh" if zh else ""
        title = "更新日志" if zh else "Changelog"
        index = [frontmatter(title), f"# {title}", "",
                 "按版本查阅已发布的 Server 与 App 更新。" if zh else "Released Server and App updates, grouped by version.", "",
                 "| 版本 | 发布日期（UTC） | 更新摘要 |" if zh else "| Version | Released (UTC) | Highlights |",
                 "| --- | --- | --- |"]
        for release in releases:
            version = release["version"]
            summary = release["summary_" + locale].replace("|", "\\|")
            index.append(f'| [{version}]({prefix}/changelog/{version}) | {release["published"]} | {summary} |')
            text = [frontmatter("GPM " + version, release["sha256"]), f"# GPM {version}", "",
                    (f'发布：{release["published"]}（UTC） · 更新至：{release["updated"]}' if zh else
                     f'Released: {release["published"]} (UTC) · Updated through: {release["updated"]}'), "",
                    release[locale], "",
                    (f"[更新日志](/{locale}/changelog/) · [下载](/{locale}/downloads)" if zh else
                     f"[Changelog]({prefix}/changelog/) · [Downloads]({prefix}/downloads)"), "",
                    f'[GitHub Release](https://github.com/Jianwei-Zhang/CGAT/releases/tag/{version})', ""]
            output[f"{locale}/changelog/{version}.md"] = "\n".join(text)
        index += ["", (f"[下载]({prefix}/downloads) · " if zh else f"[Downloads]({prefix}/downloads) · ") +
                  ("[更早版本](https://github.com/Jianwei-Zhang/CGAT/releases)" if zh else
                   "[Earlier releases](https://github.com/Jianwei-Zhang/CGAT/releases)"), ""]
        output[f"{locale}/changelog/index.md"] = "\n".join(index)
    return output


def page_entries(releases):
    entries = []
    for locale in LANGUAGES:
        prefix = "en-" if locale == "en" else ""
        route_prefix = "" if locale == "en" else "/zh"
        entries.append({"id": prefix + "changelog", "group": "reference", "title": "Changelog" if locale == "en" else "更新日志",
                        "route": f"{route_prefix}/changelog/", "source": f"{locale}/changelog/index.md", "sidebar": True, "locale": locale})
        for release in releases:
            version = release["version"]
            entries.append({"id": prefix + "changelog-" + version, "group": "reference", "title": "GPM " + version,
                            "route": f"{route_prefix}/changelog/{version}", "source": f"{locale}/changelog/{version}.md", "sidebar": False, "locale": locale})
    return entries


def update_registry(path, releases, check=False):
    if not path.exists():
        return
    pages = json.loads(path.read_text(encoding="utf-8"))
    expected = page_entries(releases)
    ids = {p["id"] for p in expected}
    current = [p for p in pages if p["id"] in ids]
    if check:
        if current != expected:
            raise ValueError("Stale or missing changelog page registry: " + str(path))
        return
    pages = [p for p in pages if p["id"] not in ids] + expected
    path.write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate(source, docs, check=False):
    releases = collect_releases(source)
    output = render_pages(releases)
    for name, content in output.items():
        path = docs / name
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ValueError("Stale or missing generated changelog: " + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    update_registry(docs / ".vitepress/data/pages.json", releases, check)
    return len(releases), len(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "GPM2.0/releases")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--release-body", metavar="VERSION", help="Print bilingual GitHub notes from the same source; does not publish.")
    args = parser.parse_args()
    try:
        if args.release_body:
            release = next((r for r in collect_releases(args.source) if r["version"] == args.release_body), None)
            if release is None:
                raise ValueError("Unknown archived release: " + args.release_body)
            print(release_body(release), end="")
            return
        releases, pages = generate(args.source, args.docs, args.check)
    except (ValueError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
    print(f'{"Checked" if args.check else "Rendered"} {releases} releases / {pages} localized changelog pages.')


if __name__ == "__main__":
    main()
