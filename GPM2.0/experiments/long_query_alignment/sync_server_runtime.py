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


# Pin a reviewed full runtime, not a broad module-name whitelist. Future mapping
# or performance changes automatically lose this one-off legacy migration until
# a maintainer explicitly reviews a new source-profile pair.
_METADATA_FIX_SOURCE_PROFILE = "c9d6e29d620ecd80d48ebd496d811569961a7e6f9a495646d7f46b8584ea686d"
_PARAMETER_SOURCE_PROFILE = "c83a96b95826d2d58055ac551456124e9acbc0d0331287a633f28f3902e3d560"
_PARTITION_SOURCE_PROFILE = "322b55b8b3dc0b0e019bd467c515551a97c77ed7a94e120f269f3f32ef9c90fa"
_PARTITION_RESUME_SOURCE_PROFILE = "9e67482b65ae03e09ea84f83e87d956d677b6f5ca777e981446d5e3fb6cf7f58"
_RESOURCE_GRANT_SOURCE_PROFILE = "19fd54d556005a7fc854fa98c61d0fb74a49e0e0e9496f68fea814248bf0563e"
_NATIVE_STREAM_SOURCE_PROFILE = "aa0bb89f9812cd64ad2d02c8e835369b8ba39eba0f021f90bea8390e70149b01"
_REVIEWED_INITIAL_WINDOW_PROFILE = "4d9244c3be38d5df7796d2917b73738859ab502b367a1c70fcf939b1d610bfab"
_AUTOMATIC_WINDOW_SOURCE_PROFILE = "88e14005c9a1786dc257662106552cb6c20b898e0a943bd3b5088d1ed6e9ba89"
_PRIMARY_LONG_SOURCE_PROFILE = "93b696a78891f06f1dc9362ec710a701899b5b8f587c162efd6b3939e2515671"
_REVIEW_TIMEOUT_SOURCE_PROFILE = "997bc543b9252cad9b4aa392e866654a39177e6085dae4abae3d60e394ba2135"
_PYTHON310_SOURCE_PROFILE = "16682331dc2c1464a7faa6d0ac2622788f0a63b26e4a9445e70603664bee6daf"
_CROSS_TOOL_SOURCE_PROFILE = "5a6f6ae44f11b533ad2541dc77a5aabe7c0d9c170b19d6de990d90563b68ca6f"
_STREAM_METADATA_SOURCE_PROFILE = "ab5f17ccf5cc2b1509ca61a6f94715303f44ea1cfb0fd8ad411d7f4370c047a6"
_DISK_PROFILE_SOURCE_PROFILE = "b61402b11101780c865f9b26654a7a5c104f696c90d3fabb82e53760495a2961"
_ASSIGNMENT_POLICY_SOURCE_PROFILE = "afbe9f6fd32ec4a96bdd8cfd2b7d87b8db562c6d52e908ee8eddce20989a076d"
_AUTOMATIC_ORDINARY_SOURCE_PROFILE = "79a55837358822ba3769efa69b81a7364109e26c6668cc15685b85cb66feae69"
_BUFFERED_STATISTICS_SOURCE_PROFILE = "dccfca050f54e57cc769559ae227dfd2863d532ea55b64f08557a7e6c38a18db"
_LEGACY_METADATA_SOURCE_PROFILE = "85a120a387487e29a71b4e74d8b2ea100b0c2f4cfcf146c6b5558919473cdecd"


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
    hashes = adapter.runtime_files(canonical)
    files = {name: ((canonical / name).read_bytes(), 0o644) for name in hashes}
    companions = {}
    for platform in ("linux-x86_64", "linux-aarch64"):
        directory = Path(bundle).parent / platform
        native = nst.validate_bundle(directory, package_platform=platform)
        if (native.get("runtime_abi") or {}).get("legacy_2_17_checked") is not True:
            raise wa.ExperimentError("Server requires the audited portable companion, never a host-only build")
        if build.elf_platform(directory / build.BINARY) != platform:
            raise wa.ExperimentError("portable companion ELF does not match package platform")
        companions[platform] = {k: native[k] for k in ("sha256", "manifest_sha256")}
        native_names = {build.BINARY: native["sha256"], build.MANIFEST: native["manifest_sha256"],
                        **native.get("third_party_licenses_sha256", {})}
        for name, digest in native_names.items():
            path = directory / name
            if path.is_symlink() or wa.sha256(path) != digest:
                raise wa.ExperimentError("portable companion changed during synchronization")
            files["native/" + platform + "/" + name] = (path.read_bytes(), 0o755 if name == build.BINARY else 0o644)
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
                "native_companions": companions,
                "handoff_base_sha256": hashlib.sha256(files[resume.BASE][0]).hexdigest(),
                "production_ready": False, "customer_configuration_required": False,
                "approximate_output_admission": adapter.ap.POLICY,
                "ordinary_output_admission": adapter.oc.POLICY,
                "generated_from": "GPM2.0/experiments/long_query_alignment; sync_server_runtime.py"}
    profile = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    manifest["native_resume_source_profiles"] = (
        [[_LEGACY_METADATA_SOURCE_PROFILE, profile]] if profile == _METADATA_FIX_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE)]
        if profile == _PARAMETER_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE, _PARAMETER_SOURCE_PROFILE)]
        if profile == _PARTITION_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE)]
        if profile == _PARTITION_RESUME_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE)]
        if profile == _RESOURCE_GRANT_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE)]
        if profile == _NATIVE_STREAM_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE)]
        if profile == _BUFFERED_STATISTICS_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE, _REVIEWED_INITIAL_WINDOW_PROFILE)]
        if profile == _AUTOMATIC_WINDOW_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE)]
        if profile == _AUTOMATIC_ORDINARY_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE)]
        if profile == _ASSIGNMENT_POLICY_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE,
                                    _ASSIGNMENT_POLICY_SOURCE_PROFILE)]
        if profile == _DISK_PROFILE_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE,
                                    _ASSIGNMENT_POLICY_SOURCE_PROFILE, _DISK_PROFILE_SOURCE_PROFILE)]
        if profile == _STREAM_METADATA_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE,
                                    _ASSIGNMENT_POLICY_SOURCE_PROFILE, _DISK_PROFILE_SOURCE_PROFILE, _STREAM_METADATA_SOURCE_PROFILE)]
        if profile == _CROSS_TOOL_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE,
                                    _ASSIGNMENT_POLICY_SOURCE_PROFILE, _DISK_PROFILE_SOURCE_PROFILE, _STREAM_METADATA_SOURCE_PROFILE,
                                    _CROSS_TOOL_SOURCE_PROFILE)]
        if profile == _PYTHON310_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE,
                                    _ASSIGNMENT_POLICY_SOURCE_PROFILE, _DISK_PROFILE_SOURCE_PROFILE, _STREAM_METADATA_SOURCE_PROFILE,
                                    _CROSS_TOOL_SOURCE_PROFILE, _PYTHON310_SOURCE_PROFILE)]
        if profile == _REVIEW_TIMEOUT_SOURCE_PROFILE else
        [[old, profile] for old in (_LEGACY_METADATA_SOURCE_PROFILE, _METADATA_FIX_SOURCE_PROFILE,
                                    _PARAMETER_SOURCE_PROFILE, _PARTITION_SOURCE_PROFILE, _PARTITION_RESUME_SOURCE_PROFILE,
                                    _RESOURCE_GRANT_SOURCE_PROFILE, _NATIVE_STREAM_SOURCE_PROFILE, _BUFFERED_STATISTICS_SOURCE_PROFILE,
                                    _REVIEWED_INITIAL_WINDOW_PROFILE, _AUTOMATIC_WINDOW_SOURCE_PROFILE, _AUTOMATIC_ORDINARY_SOURCE_PROFILE,
                                    _ASSIGNMENT_POLICY_SOURCE_PROFILE, _DISK_PROFILE_SOURCE_PROFILE, _STREAM_METADATA_SOURCE_PROFILE,
                                    _CROSS_TOOL_SOURCE_PROFILE, _PYTHON310_SOURCE_PROFILE, _REVIEW_TIMEOUT_SOURCE_PROFILE)]
        if profile == _PRIMARY_LONG_SOURCE_PROFILE else [])
    manifest["completed_reference_resume_source_profiles"] = (
        [[_PYTHON310_SOURCE_PROFILE, profile]] if profile == _REVIEW_TIMEOUT_SOURCE_PROFILE else
        [[old, profile] for old in (_PYTHON310_SOURCE_PROFILE, _REVIEW_TIMEOUT_SOURCE_PROFILE)]
        if profile == _PRIMARY_LONG_SOURCE_PROFILE else [])
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
