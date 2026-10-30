#!/usr/bin/env python3
"""Maintainer-only synchronization of the generated Server alignment runtime.

Default: read-only check. --write copies canonical experiment sources and an
already-built, audited portable companion. No compilation/network/user config.
Production hook changes are deliberately reviewed separately, never guessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import tempfile

import build_native_chain_state as build
import native_chain_state as nst
import prepare_branch_server_package as package
import resume_reference as resume
import server_alignment as adapter
import windowed_alignment as wa


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode()


def expected_files(server, canonical, bundle):
    server, canonical = Path(server).resolve(), Path(canonical).resolve()
    # All three production hooks must be exactly the reviewed generated recipe.
    for name, fragment in (("prepare.sh", package.REF_OVERLAY),
                           ("prepare.sh", package.COPY_OVERLAY),
                           ("tools/run_outer_checkpoints.py", package.CHECKPOINT_OVERLAY),
                           ("tools/server_run.py", package.RUN_OVERLAY)):
        if (server / name).read_text().count(fragment) != 1:
            raise wa.ExperimentError("production alignment hook is absent or has drifted: " + name)
    native = nst.validate_bundle(bundle)
    if (native.get("runtime_abi") or {}).get("legacy_2_17_checked") is not True:
        raise wa.ExperimentError("Server requires the audited portable companion, never a host-only build")
    hashes = adapter.runtime_files(canonical)
    files = {name: ((canonical / name).read_bytes(), 0o644) for name in hashes}
    native_root = Path(native["manifest_path"]).parent
    native_names = {build.BINARY: native["sha256"], build.MANIFEST: native["manifest_sha256"],
                    **native.get("third_party_licenses_sha256", {})}
    for name, digest in native_names.items():
        path = native_root / name
        if path.is_symlink() or wa.sha256(path) != digest:
            raise wa.ExperimentError("portable companion changed during synchronization")
        files["native/" + native["platform"] + "/" + name] = (path.read_bytes(), 0o755 if name == build.BINARY else 0o644)
    base_tools = {p.relative_to(server).as_posix(): wa.sha256(p)
                  for p in sorted((server / "tools").rglob("*.py"))
                  if "__pycache__" not in p.parts and "long_cigar_recovery" not in p.relative_to(server).parts}
    base = {"schema": 1, "source_profiles": [{"revision": "installed_server_tools",
            "base_tools_files_sha256": base_tools, "reference_launch_checkpoint_recipe_equal": True}],
            "base_prepare_sha256": wa.sha256(server / "prepare.sh"),
            "source_revision": {"worktree_source_bound_by_file_hashes": True}}
    files[resume.BASE] = (encoded(base), 0o644)
    manifest = {"schema": 1, "status": "source_checked_recovery_runtime", "scope": "initial_reference_asm10_only",
                "files_sha256": hashes, "recovered_output_admission": adapter.pub.POLICY,
                "native_companion_platform": native["platform"], "native_companion_sha256": native["sha256"],
                "handoff_base_sha256": hashlib.sha256(files[resume.BASE][0]).hexdigest(),
                "production_ready": False, "customer_configuration_required": False,
                "generated_from": "GPM2.0/experiments/long_query_alignment; sync_server_runtime.py"}
    files[adapter.MANIFEST] = (encoded(manifest), 0o644)
    return files


def synchronize(server, *, native_bundle=None, write=False):
    server = Path(server).resolve()
    root = server / "tools/long_cigar_recovery"
    canonical = Path(__file__).resolve().parent
    bundle = Path(native_bundle) if native_bundle else root / "native" / build.host_platform()
    files = expected_files(server, canonical, bundle)
    if root.is_symlink() or any(p.is_symlink() for p in root.rglob("*")):
        raise wa.ExperimentError("generated Server runtime contains a symlink")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    extra = actual - set(files)
    if extra:
        raise wa.ExperimentError("unknown generated runtime files; refusing to remove them: " + repr(sorted(extra)))
    changed = [name for name, (data, mode) in files.items()
               if not (root / name).is_file() or (root / name).read_bytes() != data
               or (name.endswith(build.BINARY) and not os.access(root / name, os.X_OK))]
    if changed and not write:
        raise wa.ExperimentError("generated Server runtime is stale: " + ", ".join(changed))
    for name in changed:
        data, mode = files[name]
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".sync-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(data)
            os.chmod(temporary, mode)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    adapter.validate_runtime(root)
    return {"status": "synchronized" if write else "verified", "files": len(files), "changed": changed,
            "production_ready": False, "official_release_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-source", type=Path, default=Path(__file__).resolve().parents[2] / "server")
    parser.add_argument("--native-state-bundle", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(synchronize(args.server_source, native_bundle=args.native_state_bundle, write=args.write), indent=2))


if __name__ == "__main__":
    main()
