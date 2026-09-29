"""Delivery archive creation and finalized-report attachment."""
from __future__ import annotations

import argparse
import csv
import contextlib
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def archive_options(root: Path) -> tuple[str, int]:
    path = root / "metadata/prepare_options.tsv"
    options = {}
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as handle:
            options = {row["key"]: row["value"] for row in csv.DictReader(handle, delimiter="\t")}
    # Generated workspaces predating archive_format keep their ZIP contract.
    format_name = options.get("archive_format", "zip")
    if format_name not in {"zip", "tar.gz"}:
        raise ValueError(f"unsupported archive format: {format_name}")
    threads = int(options.get("threads", "1"))
    if threads < 1:
        raise ValueError("archive threads must be positive")
    available = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    return format_name, min(threads, available)


def delivery_staging_root(root: Path) -> Path:
    return root.parent / f".{root.name}.delivery-staging"


def delivery_staging_path(root: Path, kind: str) -> Path:
    if kind not in {"full", "light"}:
        raise ValueError(f"unsupported delivery kind: {kind}")
    return delivery_staging_root(root) / kind / root.name



def publish_delivery_staging(root: Path, kind: str, prepared: Path) -> Path:
    root = root.resolve()
    prepared = prepared.resolve()
    target = delivery_staging_path(root, kind)
    if prepared.name != root.name or not prepared.is_dir():
        raise ValueError(f"prepared delivery staging is invalid: {prepared}")
    staging_root = delivery_staging_root(root)
    staging_root.mkdir(parents=True, exist_ok=True)
    target_parent = target.parent
    backup = staging_root / f".{kind}.before-publish"
    if backup.exists():
        shutil.rmtree(backup)
    try:
        if target_parent.exists():
            os.replace(target_parent, backup)
        os.replace(prepared.parent, target_parent)
    except Exception:
        if backup.exists():
            if target_parent.exists():
                shutil.rmtree(target_parent)
            os.replace(backup, target_parent)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    return target


def validate_delivery_staging(root: Path, kind: str) -> tuple[bool, str]:
    staging = delivery_staging_path(root, kind)
    if not staging.is_dir():
        return False, f"{kind} delivery staging is missing: {staging}"
    if not any(path.is_file() for path in staging.rglob("*")):
        return False, f"{kind} delivery staging is empty: {staging}"
    if (staging / "report").exists():
        return False, f"{kind} delivery staging unexpectedly contains a report: {staging}"
    return True, f"{kind} delivery staging is ready: {staging.name}"

def delivery_path(root: Path, kind: str) -> Path:
    format_name, _ = archive_options(root)
    suffix = "" if kind == "full" else ".light"
    return root.parent / f"{root.name}{suffix}.{format_name}"


def _write_tar_gz(output: Path, threads: int, populate) -> None:
    pigz = shutil.which("pigz")
    if pigz is None:
        raise RuntimeError("pigz is required for tar.gz delivery; run server/install.sh or select --archive-format zip")
    with output.open("wb") as handle, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [pigz, "-6", "-p", str(threads), "-c"], stdin=subprocess.PIPE, stdout=handle, stderr=errors,
        )
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
                populate(archive)
            process.stdin.close()
            code = process.wait()
            if code:
                errors.seek(0)
                raise RuntimeError(f"pigz exited {code}: {errors.read(8192).decode(errors='replace')}")
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
        finally:
            with contextlib.suppress(BrokenPipeError):
                process.stdin.close()


def create_archive(staging: Path, output: Path, format_name: str, threads: int) -> None:
    if format_name == "tar.gz":
        _write_tar_gz(output, threads, lambda archive: archive.add(staging, arcname=staging.name))
    elif format_name == "zip":
        subprocess.run(["zip", "-rq", str(output.resolve()), staging.name], cwd=staging.parent, check=True)
    else:
        raise ValueError(f"unsupported archive format: {format_name}")


def attach_tar_report(source: Path, output: Path, root: Path, report_files: list[Path], threads: int) -> None:
    prefix = f"{root.name}/report/"

    def populate(destination):
        with tarfile.open(source, "r|gz") as archive:
            for member in archive:
                if member.name.rstrip("/") == prefix.rstrip("/") or member.name.startswith(prefix):
                    raise ValueError(f"delivery archive already contains a report: {source}")
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"unsupported delivery archive member: {member.name}")
                content = archive.extractfile(member) if member.isfile() else None
                try:
                    destination.addfile(member, content)
                finally:
                    if content is not None:
                        content.close()
        for path in report_files:
            destination.add(path, arcname=prefix + path.relative_to(root / "report").as_posix())

    _write_tar_gz(output, threads, populate)


def validate_tar_archive(path: Path, required: set[str]) -> None:
    # Drain gzip through its trailer as well as reading every tar member.
    with gzip.open(path, "rb") as stream:
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            names = set()
            for member in archive:
                if member.name in names:
                    raise ValueError(f"duplicate delivery member: {member.name}")
                names.add(member.name)
                if member.isfile():
                    with archive.extractfile(member) as content:
                        while content.read(1024 * 1024):
                            pass
            if not required.issubset(names):
                raise ValueError(f"delivery archive is missing embedded report members: {required - names}")
        while stream.read(1024 * 1024):
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["path", "staging-path", "publish-staging", "create"]
    )
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=["full", "light"], required=True)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "path":
        print(delivery_path(args.server_dir, args.kind))
    elif args.action == "staging-path":
        print(delivery_staging_path(args.server_dir, args.kind))
    elif args.action == "publish-staging":
        if args.staging is None:
            parser.error("publish-staging requires --staging")
        print(publish_delivery_staging(args.server_dir, args.kind, args.staging))
    else:
        if args.staging is None or args.output is None:
            parser.error("create requires --staging and --output")
        format_name, threads = archive_options(args.server_dir)
        print(f"Compressing {format_name}: threads={threads if format_name == 'tar.gz' else 1}", flush=True)
        create_archive(args.staging, args.output, format_name, threads)


if __name__ == "__main__":
    main()
