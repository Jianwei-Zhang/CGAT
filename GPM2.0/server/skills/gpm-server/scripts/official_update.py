#!/usr/bin/env python3
"""Check official versions and stage a pinned update; never activate or install."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import urllib.parse
import urllib.request

REPOSITORY = "Jianwei-Zhang/CGAT"
SITE = "https://riceome.hzau.edu.cn/cgat/"
API = f"https://api.github.com/repos/{REPOSITORY}/"
SKILL_PATH = "GPM2.0/server/skills/gpm-server"
SCHEMA = "gpm-server-official-update.v1"
MAX_METADATA = 8 * 1024 * 1024
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_UNPACKED = 100 * 1024 * 1024
MAX_FILES = 5000
HOSTS = {"api.github.com", "github.com", "raw.githubusercontent.com",
         "release-assets.githubusercontent.com", "objects.githubusercontent.com"}

spec = importlib.util.spec_from_file_location(
    "gpm_skill_stager", Path(__file__).with_name("stage_skill_update.py"))
stager = importlib.util.module_from_spec(spec)
# A read-only check must not create bytecode inside the installed skill.
previous_bytecode_setting = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    spec.loader.exec_module(stager)
finally:
    sys.dont_write_bytecode = previous_bytecode_setting


def check_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Only HTTPS official GitHub endpoints/asset redirects are allowed")


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_url(url: str, limit: int = MAX_METADATA) -> bytes:
    check_url(url)
    req = urllib.request.Request(url, headers={
        "User-Agent": "gpm-server-skill", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    # Public unauthenticated reads only; never inspect agent/SSH/token files.
    with urllib.request.build_opener(OfficialRedirect).open(req, timeout=30) as response:
        check_url(response.geturl())
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Official response exceeds the bounded download limit")
    return data


def api_json(endpoint: str):
    return json.loads(read_url(API + endpoint))


def release_info(release: dict) -> dict:
    tag = release.get("tag_name", "")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("Only published stable Releases are supported")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Unexpected stable Release tag; review official naming")
    name = f"GPM_Server_{tag[1:]}_source.tar.gz"
    assets = [a for a in release.get("assets", []) if a.get("name") == name]
    if len(assets) != 1:
        raise ValueError("Release must contain exactly one matching Server source asset")
    asset = assets[0]
    digest = asset.get("digest") or ""
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    if (not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or asset.get("browser_download_url") != url
            or type(asset.get("size")) is not int or not 0 < asset["size"] <= MAX_ARCHIVE
            or type(asset.get("id")) is not int or asset["id"] <= 0):
        raise ValueError("Missing/invalid official digest, size, asset identity or origin")
    return {"tag": tag, "asset": name, "asset_id": asset["id"], "size": asset["size"],
            "sha256": digest.removeprefix("sha256:"), "url": url}


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or any(p in (".", "..") for p in name.split("/"))
            or "\\" in name or any(ord(c) < 32 for c in name)
            or str(path) != name.rstrip("/")):
        raise ValueError(f"Unsafe or noncanonical archive/source path: {name!r}")
    return path


def skill_info(commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Skill source must be pinned to a full official commit SHA")
    git_commit = api_json(f"git/commits/{commit}")
    if git_commit.get("sha") != commit:
        raise ValueError("Official commit identity mismatch")
    tree_sha = git_commit["tree"]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise ValueError("Invalid official tree identity")
    tree = api_json(f"git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated") is not False or tree.get("sha") != tree_sha:
        raise ValueError("Incomplete official tree; refusing a partial skill")
    files = []
    for item in tree["tree"]:
        if not item["path"].startswith(SKILL_PATH + "/"):
            continue
        name = item["path"][len(SKILL_PATH) + 1:]
        path = safe_relative(name)
        if path.parts[0] == "local" or "__pycache__" in path.parts or name.endswith(".pyc"):
            raise ValueError("Official skill tree unexpectedly contains local/runtime state")
        if item["type"] == "tree":
            continue
        if (item["type"] != "blob" or item["mode"] not in ("100644", "100755")
                or not re.fullmatch(r"[0-9a-f]{40}", item["sha"])
                or type(item.get("size")) is not int or not 0 <= item["size"] <= MAX_METADATA):
            raise ValueError("Unsupported official skill entry (link/submodule/size/hash)")
        files.append({"path": name, "sha": item["sha"], "size": item["size"], "mode": item["mode"]})
    files.sort(key=lambda x: x["path"])
    required = {".gitignore", "SKILL.md", "server-tools.path", "scripts/server_tools_path.sh"}
    if (not required.issubset({f["path"] for f in files}) or len(files) > MAX_FILES
            or sum(f["size"] for f in files) > MAX_METADATA):
        raise ValueError("Official skill is incomplete or exceeds bounded limits")
    if len({f["path"] for f in files}) != len(files):
        raise ValueError("Duplicate official skill paths")
    entry = next(f for f in files if f["path"] == "SKILL.md")
    raw = read_url(f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{SKILL_PATH}/SKILL.md")
    if len(raw) != entry["size"] or blob_sha(raw) != entry["sha"]:
        raise ValueError("Official skill entrypoint identity mismatch")
    version = re.search(r'^\s*skill-version:\s*"([^"]+)"\s*$', raw.decode("utf-8"), re.MULTILINE)
    return {"channel": "official-repository", "commit": commit, "path": SKILL_PATH,
            "version": version.group(1) if version else None, "tree": tree_sha, "files": files}


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def installed_info(installed: Path, skill: dict) -> dict:
    installed = stager.checked_path(installed)
    differences = []
    for item in skill["files"]:
        if item["path"] == "server-tools.path":
            continue  # A host-local binding is expected to differ from the bundle.
        path = installed / item["path"]
        try:
            stager.checked_path(path)
            matched = path.is_file() and blob_sha(path.read_bytes()) == item["sha"]
        except OSError:
            matched = False
        if not matched:
            differences.append(item["path"])
    result = {"path": str(installed), "skill_matches_official_files": not differences,
              "different_or_missing_files": differences,
              "server_provenance": None}
    try:
        binding = stager.preserved_binding(installed).decode().strip()
        server = stager.checked_path(Path(binding))
        if not server.is_dir():
            raise ValueError("Recorded Server directory is unavailable")
        result["recorded_server_tools"] = str(server)
        for name in ("official-source.json", "SOURCE.json"):
            file = server / name
            stager.checked_path(file)
            if file.is_file():
                result["server_provenance"] = json.loads(file.read_text())
                break
    except (OSError, ValueError, RuntimeError):
        result["recorded_server_tools"] = "unavailable or invalid; use ask-first location policy"
    return result


def check(installed: Path) -> dict:
    server = release_info(api_json("releases/latest"))
    query = urllib.parse.urlencode({"sha": "master", "path": SKILL_PATH, "per_page": 1})
    commits = api_json("commits?" + query)
    if not isinstance(commits, list) or not commits:
        raise ValueError("Official repository has no published skill source")
    skill = skill_info(commits[0]["sha"])
    return {"schema": SCHEMA, "repository": REPOSITORY, "website": SITE,
            "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "server": server, "skill": skill, "installed": installed_info(installed, skill)}


def validate_plan(plan: dict) -> None:
    if (plan.get("schema") != SCHEMA or plan.get("repository") != REPOSITORY
            or plan.get("website") != SITE or not isinstance(plan.get("server"), dict)
            or not isinstance(plan.get("skill"), dict)):
        raise ValueError("Plan must come from this helper's official check")
    tag = plan["server"].get("tag", "")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Invalid pinned release tag")
    server = release_info(api_json(f"releases/tags/{tag}"))
    if server != plan["server"]:
        raise ValueError("Release asset changed since check; obtain and review a fresh plan")
    if skill_info(plan["skill"].get("commit", "")) != plan["skill"]:
        raise ValueError("Official skill identity changed or plan was modified")


def unpack_server(payload: bytes, output: Path) -> Path:
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        raw = stream.read(MAX_UNPACKED + 1)
    if len(raw) > MAX_UNPACKED:
        raise ValueError("Server archive exceeds the unpacked size limit")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        members = []
        for member in archive:
            members.append(member)
            if len(members) > MAX_FILES:
                raise ValueError("Too many archive members")
        seen = set()
        for member in members:
            path = safe_relative(member.name)
            if (path.parts[0] != "GPM_Server" or str(path) in seen
                    or member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE)
                    or member.size < 0 or member.size > MAX_UNPACKED):
                raise ValueError("Archive has unexpected root, duplicate, link or special entry")
            seen.add(str(path))
        # Validation precedes all writes; do not use extractall on a download.
        for member in members:
            target = output / PurePosixPath(member.name)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if member.isdir():
                target.mkdir(exist_ok=True, mode=0o700)
            else:
                with archive.extractfile(member) as src, target.open("xb") as dest:
                    shutil.copyfileobj(src, dest)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
    return output / "GPM_Server"


def stage(plan: dict, installed: Path, output: Path) -> dict:
    installed, output = stager.checked_path(installed), stager.checked_path(output)
    if (output == installed or output in installed.parents or installed in output.parents
            or output.exists() or not output.parent.is_dir()):
        raise ValueError("Choose a new, nonoverlapping output with an existing parent")
    validate_plan(plan)  # Re-fetch pinned identities, not a moving 'latest'.
    output.mkdir(mode=0o700)
    try:
        server = plan["server"]
        archive = read_url(server["url"], MAX_ARCHIVE)
        if len(archive) != server["size"] or hashlib.sha256(archive).hexdigest() != server["sha256"]:
            raise ValueError("Server asset size/SHA-256 mismatch")
        (output / server["asset"]).write_bytes(archive)
        tools = unpack_server(archive, output)
        source = output / "official-skill"
        source.mkdir(mode=0o700)
        for item in plan["skill"]["files"]:
            url = (f"https://raw.githubusercontent.com/{REPOSITORY}/{plan['skill']['commit']}/"
                   f"{SKILL_PATH}/{item['path']}")
            data = read_url(url)
            if len(data) != item["size"] or blob_sha(data) != item["sha"]:
                raise ValueError(f"Skill blob identity mismatch: {item['path']}")
            dest = source / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            dest.write_bytes(data)
            dest.chmod(0o700 if item["mode"] == "100755" else 0o600)
        # Use this installed helper, NOT scripts downloaded from the new source.
        skill = stager.stage(source, installed, output / "gpm-server", tools)
        (skill / "official-source.json").write_text(json.dumps(plan["skill"], indent=2) + "\n")
        (tools / "official-source.json").write_text(json.dumps(server, indent=2) + "\n")
        report = {"state": "staged-not-activated", "server": server, "skill": plan["skill"],
                  "server_tools": str(tools), "installed_skill_candidate": str(skill),
                  "old_installation": str(installed), "local_state_preserved": True,
                  "environment_or_agent_config_changed": False}
        (output / "update-report.json").write_text(json.dumps(report, indent=2) + "\n")
    except BaseException:
        shutil.rmtree(output)  # Only this invocation's new staged downloads.
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    checking = commands.add_parser("check", help="Read-only public official version check")
    checking.add_argument("--installed", type=Path, default=Path(__file__).resolve().parents[1])
    staging = commands.add_parser("stage", help="Prepare a reviewed pinned plan; no activation")
    staging.add_argument("--plan", type=Path, required=True)
    staging.add_argument("--installed", type=Path, required=True)
    staging.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            result = check(args.installed)
        else:
            stager.checked_path(args.plan)
            result = stage(json.loads(args.plan.read_text()), args.installed, args.out)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, tarfile.TarError, EOFError) as exc:
        print(f"ERROR: {exc}; no update was activated.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
