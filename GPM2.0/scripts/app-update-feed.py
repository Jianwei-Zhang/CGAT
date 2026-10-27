#!/usr/bin/env python3
"""Build or stage the signed desktop feed. Never publishes or edits a Release.

build: verified CI bundles + canonical bilingual notes -> latest.json and notes.
stage: downloaded Release assets -> docs files, with latest.json replaced LAST.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = "https://riceome.hzau.edu.cn/cgat/downloads"
GITHUB = "https://github.com/Jianwei-Zhang/CGAT/releases/download"
TARGETS = {"windows-x86_64": "win-x86", "windows-aarch64": "win-arm64",
           "darwin-x86_64": "mac-x86", "darwin-aarch64": "mac-arm64"}


def check_version(version):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Expected a stable X.Y.Z version")


def file_info(path, version, limit=256 * 1024 * 1024):
    if path.is_symlink():
        raise ValueError("Symlink update assets are not supported")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", path.name):
        raise ValueError("Unsafe asset name")
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise ValueError("Update asset size is outside the client limit")
    return {"url": f"{GITHUB}/v{version}/{path.name}", "mirror_url": f"{DOCS}/v{version}/{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size}


def localized_notes(release, locale):
    # Extract only App + Server sections, App first for the desktop dialog. Preserve
    # canonical wording; do not ship download instructions or the other language.
    sections = dict(re.findall(r"^### (App|Server)\s*\n(.*?)(?=^### |\Z)", release[locale], re.M | re.S))
    return "\n\n".join(f"{name}\n{sections[name].strip()}" for name in ("App", "Server")) + "\n"


def verify_signature(path, signature, public_key):
    """Use Minisign, not an ad-hoc crypto implementation. Only public data on disk."""
    if not public_key.strip():
        raise ValueError("GPM_UPDATER_PUBLIC_KEY is required to build a publishable feed")
    with tempfile.TemporaryDirectory(prefix="gpm-update-verify-") as temporary:
        key_path = Path(temporary) / "updater.pub"
        sig_path = Path(temporary) / "artifact.sig"
        key_path.write_bytes(base64.b64decode(public_key.strip(), validate=True))
        sig_path.write_bytes(base64.b64decode(signature, validate=True))
        subprocess.run(["minisign", "-Vm", str(path), "-p", str(key_path), "-x", str(sig_path)],
                       check=True, capture_output=True)


def build(version, assets, output, notes_root=None, verifier=None):
    check_version(version)
    spec = importlib.util.spec_from_file_location("release_docs", ROOT / "GPM2.0/scripts/render-release-docs.py")
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    release = archive.read_release((notes_root or ROOT / "GPM2.0/releases") / f"v{version}.md")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "version": version, "pub_date": release["published"] + "T00:00:00Z",
                "platforms": {}, "release_notes": {}}
    for target, platform in TARGETS.items():
        extension = "setup.exe" if target.startswith("windows") else "app.tar.gz"
        candidates = list(assets.glob(f"GPM_{version}_*_{platform}_{extension}"))
        if len(candidates) != 1:
            raise ValueError(f"Expected exactly one {platform} update bundle, found {len(candidates)}")
        package = candidates[0]
        signature = Path(str(package) + ".sig").read_text(encoding="utf-8").strip()
        if verifier is not None:
            verifier(package, signature)
        decoded = base64.b64decode(signature, validate=True).decode("utf-8")
        # Tauri 2.14 binds this signed trusted comment to the announced version.
        comments = [line.removeprefix("trusted comment: ") for line in decoded.splitlines()
                    if line.startswith("trusted comment: ")]
        versions = [field.removeprefix("version:") for line in comments for field in line.split("\t")
                    if field.startswith("version:")]
        if versions != [version]:
            raise ValueError(f"Missing signed version in {package.name}. Use a current Tauri CLI.")
        manifest["platforms"][target] = {**file_info(package, version), "signature": signature}
    for locale in ("en", "zh"):
        content = localized_notes(release, locale).encode("utf-8")
        revision = hashlib.sha256(content).hexdigest()[:16]
        path = output / f"GPM_{version}_notes_{locale}_{revision}.txt"
        path.write_bytes(content)
        manifest["release_notes"][locale] = file_info(path, version, limit=256 * 1024)
    (output / "latest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def stage(assets, public):
    raw = (assets / "latest.json").read_bytes()
    manifest = json.loads(raw)
    version = manifest["version"]
    check_version(version)
    if manifest.get("schema_version") != 1 or set(manifest["platforms"]) != set(TARGETS) or set(manifest["release_notes"]) != {"en", "zh"}:
        raise ValueError("Incomplete update feed")
    # Validate ALL files before writing anything. Latest is promoted only after
    # all immutable version files have been copied and rechecked.
    files = []
    for info in [*manifest["platforms"].values(), *manifest["release_notes"].values()]:
        prefix = f"{GITHUB}/v{version}/"
        if not info["url"].startswith(prefix):
            raise ValueError("Untrusted update URL")
        name = info["url"][len(prefix):]
        if name in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise ValueError("Unsafe update filename")
        path = assets / name
        if file_info(path, version) != {key: info[key] for key in ("url", "mirror_url", "sha256", "size")}:
            raise ValueError(f"Digest, size or URL mismatch: {name}")
        files.append(path)
    directory = public / "downloads" / f"v{version}"
    latest = public / "downloads/updates/latest.json"
    if latest.exists():
        old_version = json.loads(latest.read_text(encoding="utf-8"))["version"]
        check_version(old_version)
        if tuple(map(int, old_version.split("."))) > tuple(map(int, version.split("."))):
            raise ValueError("Refusing to downgrade the docs update feed")
    for source in files:
        target = directory / source.name
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError(f"Refusing to replace immutable asset: {source.name}")
    directory.mkdir(parents=True, exist_ok=True)
    for source in files:
        target = directory / source.name
        if source.resolve() != target.resolve():
            temporary = directory / (source.name + ".tmp")
            shutil.copyfile(source, temporary)
            if hashlib.sha256(temporary.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
                raise ValueError("Mirror copy verification failed")
            temporary.replace(target)
    latest = public / "downloads/updates/latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    temporary = latest.with_suffix(".json.tmp")
    temporary.write_bytes(raw)
    temporary.replace(latest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("--version", required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("stage")
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--public", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        public_key = os.environ.get("GPM_UPDATER_PUBLIC_KEY", "")
        build(args.version, args.assets, args.output,
              verifier=lambda path, signature: verify_signature(path, signature, public_key))
    else:
        stage(args.assets, args.public)
