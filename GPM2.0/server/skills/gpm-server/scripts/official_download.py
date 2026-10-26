#!/usr/bin/env python3
"""Bounded dual-origin downloads of ONE official Server + bundled skill release.

No GitHub access is required when the official docs mirror is available. Metadata
uses docs first, then GitHub on failure. Archive fallback keeps the same identity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

import official_update as legacy

SITE = "https://riceome.hzau.edu.cn/cgat/"
TIMEOUT = 8
TOTAL_TIMEOUT = 25
HOSTS = legacy.HOSTS | {"riceome.hzau.edu.cn"}


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username
            or parsed.password or parsed.port not in (None, 443)
            or (parsed.hostname == "riceome.hzau.edu.cn" and not parsed.path.startswith("/cgat/"))):
        raise ValueError("Only official GitHub and CGAT docs HTTPS URLs are allowed")


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_url(url, limit=legacy.MAX_METADATA):
    check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "gpm-server-updater",
        "Accept": "application/vnd.github+json"})
    started = time.monotonic()
    with urllib.request.build_opener(Redirect).open(request, timeout=TIMEOUT) as response:
        check_url(response.geturl())
        chunks, size = [], 0
        while True:
            chunk = response.read(min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit or time.monotonic() - started > TOTAL_TIMEOUT:
                raise ValueError("Official download exceeds size/time limit")
    return b"".join(chunks)


def github_release():
    result = legacy.release_info(json.loads(read_url(legacy.API + "releases/latest")))
    return {**result, "origin": "GitHub Release", "download_url": result["url"]}


def docs_release():
    info = json.loads(read_url(SITE + "build-info.json"))
    if not isinstance(info, dict):
        raise ValueError("Invalid docs build-info object")
    relative = info.get("releaseAssetManifest", "")
    if not re.fullmatch(r"downloads/v\d+\.\d+\.\d+/release\.json", relative):
        raise ValueError("Docs build-info has no valid Release manifest")
    manifest = json.loads(read_url(SITE + relative))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list):
        raise ValueError("Invalid docs Release manifest")
    if any(not isinstance(asset, dict) for asset in manifest["assets"]):
        raise ValueError("Invalid docs asset record")
    tag = manifest.get("tag", "")
    if (manifest.get("repository") != legacy.REPOSITORY
            or not re.fullmatch(r"v\d+\.\d+\.\d+", tag)
            or relative != f"downloads/{tag}/release.json"):
        raise ValueError("Invalid docs Release identity")
    name = f"GPM_Server_{tag[1:]}_source.tar.gz"
    matches = [a for a in manifest["assets"] if a.get("name") == name]
    if len(matches) != 1:
        raise ValueError("Docs must contain exactly one Server source asset")
    asset = matches[0]
    upstream = f"https://github.com/{legacy.REPOSITORY}/releases/download/{tag}/{name}"
    if (asset.get("path") != f"/downloads/{tag}/{name}" or asset.get("upstream") != upstream
            or not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", ""))
            or type(asset.get("bytes")) is not int or not 0 < asset["bytes"] <= legacy.MAX_ARCHIVE):
        raise ValueError("Invalid docs source path/size/SHA-256")
    return {"tag": tag, "asset": name, "size": asset["bytes"], "sha256": asset["sha256"],
            "url": upstream, "origin": "CGAT docs", "download_url": SITE + asset["path"].lstrip("/")}


def identity(record):
    return tuple(record[key] for key in ("tag", "asset", "size", "sha256"))


def discover(log=print):
    errors = []
    for name, fetch in (("CGAT docs", docs_release), ("GitHub Release", github_release)):
        try:
            selected = fetch()
            urls = [SITE + "downloads/{tag}/{asset}".format(**selected), selected["url"]]
            log("Version source: " + name)
            return {**selected, "urls": urls}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{name}: {exc}")
            log("Source unavailable; falling back: " + errors[-1])
    raise ValueError("Both official sources failed; freshness is unknown. " + "; ".join(errors))


def download(record, log=print):
    failures = []
    # Reconstruct official URLs from validated fields rather than trusting a saved plan.
    urls = [SITE + "downloads/{tag}/{asset}".format(**record), record["url"]]
    for url in urls:
        try:
            data = read_url(url, legacy.MAX_ARCHIVE)
            if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("Archive size/SHA-256 mismatch (possibly an unsynchronized source)")
            log("Verified download: " + url)
            return data
        except (OSError, ValueError) as exc:
            failures.append(f"{url}: {exc}")
            log("Download failed; trying the other official source: " + str(exc))
    raise ValueError("Both archive downloads failed: " + "; ".join(failures))


def extract(record, output: Path, log=print):
    return legacy.unpack_server(download(record, log), output)


def verify_bundle(root, release):
    metadata = json.loads((root / "SOURCE.json").read_text())
    if not isinstance(metadata, dict):
        raise ValueError("Invalid source manifest object")
    if (metadata.get("release") != release["tag"]
            or not re.fullmatch(r"[0-9a-f]{40}", metadata.get("git_revision", ""))):
        raise ValueError("SOURCE.json release/revision mismatch")
    files = metadata.get("files")
    required = {"run.sh", "prepare.sh", "install.sh", "tools/server_run.py",
                "tools/grt_core/__init__.py", "skills/gpm-server/SKILL.md",
                "skills/gpm-server/server-tools.path"}
    if not isinstance(files, dict) or not required.issubset(files):
        raise ValueError("Source package has no complete file manifest")
    for name, record in files.items():
        legacy.safe_relative(name)
        if not isinstance(record, dict):
            raise ValueError("Invalid source file record: " + name)
        if name == "SOURCE.json" or name.startswith("skills/gpm-server/local/"):
            raise ValueError("Source manifest must not own provenance or user-local notes")
        path = root / name
        if (record.get("mode") not in (0o644, 0o755) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256")):
            raise ValueError("Source file integrity failure: " + name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(files) | {"SOURCE.json"}:
        raise ValueError("Source package has unmanifested files")
    return metadata
