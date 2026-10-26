#!/usr/bin/env python3
"""Remove internal updater assets after latest.json embeds their signatures.

Tauri needs package/archive and .sig files between build jobs. The runtime update
manifest embeds each verified signature, while docs hosts the downloadable update
bytes. Keep GitHub Releases focused on manual installers, Server source and data.
"""
from __future__ import annotations
import argparse
import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path

SUFFIX = {
    "windows-x86_64": "_win-x86_setup.exe",
    "windows-aarch64": "_win-arm64_setup.exe",
    "darwin-x86_64": "_mac-x86_app.tar.gz",
    "darwin-aarch64": "_mac-arm64_app.tar.gz",
}


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True)


def embedded_signatures(manifest: dict, asset_names: set[str], tag: str) -> set[str]:
    version = manifest.get("version", "")
    assert re.fullmatch(r"\d+\.\d+\.\d+", version) and tag == "v" + version
    assert manifest.get("schema_version") == 1
    assert set(manifest.get("platforms", {})) == set(SUFFIX)
    expected = set()
    for target, suffix in SUFFIX.items():
        package = manifest["platforms"][target]
        name = package["url"].rsplit("/", 1)[-1]
        assert name in asset_names and name.endswith(suffix), f"Missing package for {target}: {name}"
        signature = package.get("signature", "")
        assert isinstance(signature, str) and 0 < len(signature) <= 4096
        lines = base64.b64decode(signature, validate=True).decode("utf-8").splitlines()
        assert len(lines) >= 3 and lines[0].startswith("untrusted comment:")
        raw_signature = base64.b64decode(lines[1], validate=True)
        assert len(raw_signature) == 74 and raw_signature[:2] == b"ED"
        assert lines[2].startswith("trusted comment: ")
        fields = lines[2].removeprefix("trusted comment: ").split("\t")
        assert f"version:{version}" in fields, f"Signature for {target} is not bound to {version}"
        expected.add(name + ".sig")
    return expected


def internal_asset_names(manifest: dict, asset_names: set[str], tag: str) -> set[str]:
    signatures = embedded_signatures(manifest, asset_names, tag)
    packages = {package["url"].rsplit("/", 1)[-1]
                for target, package in manifest["platforms"].items()
                if target.startswith("darwin-")}
    notes = {info["url"].rsplit("/", 1)[-1] for info in manifest["release_notes"].values()}
    assert len(packages) == 2 and packages <= asset_names
    assert len(notes) == 2 and notes <= asset_names
    assert "latest.json" in asset_names
    # Windows installers are also updater packages and remain user-facing.
    return signatures | packages | notes | {"latest.json"}


def cleanup(repo: str, tag: str) -> dict:
    view = json.loads(gh("release", "view", tag, "--repo", repo, "--json", "assets"))
    names = {asset["name"] for asset in view["assets"]}
    assert "latest.json" in names, "The signed update manifest is missing"
    with tempfile.TemporaryDirectory(prefix="gpm-signature-cleanup-") as temporary:
        gh("release", "download", tag, "--repo", repo, "--pattern", "latest.json", "--dir", temporary)
        manifest = json.loads((Path(temporary) / "latest.json").read_text())
    expected = internal_asset_names(manifest, names, tag)
    existing_signatures = {name for name in names if name.endswith(".sig")}
    expected_signatures = {name for name in expected if name.endswith(".sig")}
    assert existing_signatures <= expected_signatures, f"Unexpected signature assets: {sorted(existing_signatures - expected_signatures)}"
    removed = sorted(expected & names)
    for name in removed:
        gh("release", "delete-asset", tag, name, "--repo", repo, "--yes")
    after = {asset["name"] for asset in json.loads(
        gh("release", "view", tag, "--repo", repo, "--json", "assets"))["assets"]}
    assert not (expected & after)
    assert all(name in after for name in names if name.endswith(("_win-x86_setup.exe", "_win-arm64_setup.exe")))
    return {"tag": tag, "removed": removed, "remaining_assets": len(after),
            "embedded_signatures_preserved": True, "docs_only_update_source": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Jianwei-Zhang/CGAT")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    print(json.dumps(cleanup(args.repo, args.tag), indent=2))
