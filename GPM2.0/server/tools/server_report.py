#!/usr/bin/env python3
"""Record and deliver a portable report for prepare.sh and run_all.sh."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
import zipfile
from collections import deque
from pathlib import Path

from server_report_collect import (
    capture_final, collect_grt_result, collect_unit, final_summary, inputs,
)
from server_report_io import SCHEMA, digest, local_path, now, read_json, write_json
from render_server_report import render

TITLES = {
    "prepare": "输入准备", "assign": "染色体归属与排列",
    "grt_prepare": "质量评估、q0 与供体构建", "grt_step1": "GRT Step1",
    "grt_step23": "GRT Step2 / Step3", "grt_telomere_finalize": "端粒处理与最终路径",
    "finalize_evidence": "证据整理与结果校验", "package_full": "完整包交付",
    "package_light": "Light 轻量包交付", "step1_round1": "Step1 · 第一阶段",
    "step1_filter": "Step1 · 过滤阶段", "step1_round2": "Step1 · 第二阶段",
    "step2": "Step2 · 补丁验证与处理分支", "step3": "Step3 · 结构修正与优化填补",
    "step4_telomere": "Step4 · 端粒处理",
}


def title(unit_id: str) -> str:
    if unit_id.startswith("ref:"):
        return "参考比对 · " + unit_id[4:]
    if unit_id.startswith("chr:"):
        return "染色体比对与注释 · " + unit_id[4:]
    return TITLES.get(unit_id, unit_id)


def fresh_directory(root: Path) -> Path:
    report = root / "report"
    if report.exists():
        previous = read_json(report / "manifest.json", {})
        # Archive rather than overwrite records from previous invocations.
        archive = root / ".report_history" / (str(previous.get("run_id", "unknown")) + "-" + uuid.uuid4().hex[:8])
        archive.parent.mkdir(parents=True, exist_ok=True)
        report.rename(archive)
    (report / "steps").mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("render_server_report.py"), report / "render_report.py")
    return report


def step_record(run_id: str, unit_id: str, **values) -> dict:
    return {"schema_version": SCHEMA, "run_id": run_id, "stage_id": unit_id,
            "title": title(unit_id), "recorded_at": now(), **values}


def record_grt_result(root: Path, result: dict) -> None:
    """Called at publication, before later stages can reconcile these events."""
    run_id = os.environ.get("GPM_REPORT_RUN_ID")
    unit_id = os.environ.get("GPM_REPORT_UNIT_ID")
    if not run_id or not unit_id:
        return
    report = root / "report"
    manifest = read_json(report / "manifest.json", {})
    if manifest.get("run_id") != run_id:
        raise ValueError("report invocation does not match the running GRT stage")
    path = report / "steps" / ("grt-" + result["stage"] + ".json")
    if path.exists():
        return  # First publication is immutable, including during republishing.
    write_json(path, step_record(run_id, result["stage"], parent_unit=unit_id,
                               status="success", execution="see_parent_unit",
                               facts=collect_grt_result(root, result)))


class ReportSession:
    def __init__(self, root: Path, units, run_id: str):
        self.root = root
        self.report = fresh_directory(root)
        self.run_id = run_id
        saved = read_json(root / "metadata/report_inputs.json")
        current_inputs = inputs(root)
        if saved is None:
            saved = {"schema_version": SCHEMA, "provenance": "reconstructed_at_run_start",
                     "notes": ["该工作目录没有准备阶段记录；原始命令和准备时间未知。"],
                     "facts": current_inputs}
        else:
            prepared_inputs = saved.get("facts", {})
            if prepared_inputs != current_inputs:
                saved["preparation_snapshot"] = prepared_inputs
                saved.setdefault("notes", []).append("工作目录的输入或参数与准备阶段快照不同；本报告统计已按运行开始时的实际文件重新计算。")
            saved["facts"] = current_inputs
        saved["preparation_id"] = saved.get("run_id")
        saved["run_id"] = run_id
        self.input_data = saved.get("facts", {})
        write_json(self.report / "inputs.json", saved)
        self.manifest = {"schema_version": SCHEMA, "run_id": run_id,
                         "started_at": now(), "ended_at": None, "status": "running",
                         "workspace_name": root.name, "steps": [], "errors": []}
        self.records = {}
        self.output_tails = {}
        self.cached_stages_by_unit = {}
        self.current_unit_id = None
        for index, unit in enumerate(units, 1):
            filename = f"steps/{index:03d}.json"
            record = step_record(run_id, unit.unit_id, order=index, status="pending",
                                 command=unit.command_relpath, execution="not_started", history=[])
            record["command_text"] = local_path(root, unit.command_relpath).read_text(encoding="utf-8")
            self.records[unit.unit_id] = (filename, record)
            self.manifest["steps"].append(filename)
            write_json(self.report / filename, record)
        self.save()
        render(self.report)

    def save(self):
        write_json(self.report / "manifest.json", self.manifest)

    def event(self, event: str, unit, message: str, row: dict | None):
        if unit is None:
            if event == "SUCCESS":
                self.manifest["status"] = "success"
            elif event == "INTERRUPTED":
                self.manifest["status"] = "interrupted"
            self.save()
            return
        filename, record = self.records[unit.unit_id]
        record["history"].append({"at": now(), "event": event, "message": message})
        record["recorded_at"] = now()
        if row:
            record["runtime"] = dict(row)
            record["status"] = row["state"]
        if event == "START":
            self.current_unit_id = unit.unit_id
            self.output_tails[unit.unit_id] = deque(maxlen=80)
            self.cached_stages_by_unit[unit.unit_id] = set()
            record["execution"] = "computed"
            script = local_path(self.root, unit.command_relpath)
            record["command_text"] = script.read_text(encoding="utf-8")
        if event in {"CACHE_HIT", "SKIP_VALID"}:
            record["execution"] = "cache_reused"
        if event in {"SUCCESS", "SKIP_VALID"}:
            record["facts"] = collect_unit(self.root, unit.unit_id, self.input_data)
            for path in (self.report / "steps").glob("grt-*.json"):
                substage = read_json(path)
                if substage.get("parent_unit") == unit.unit_id:
                    cached = self.cached_stages_by_unit.get(unit.unit_id, set())
                    substage["execution"] = "cache_reused" if substage["stage_id"] in cached else "computed"
                    write_json(path, substage)
            if unit.unit_id == "grt_telomere_finalize":
                write_json(self.report / "final_snapshot.json", {
                    "schema_version": SCHEMA, "run_id": self.run_id,
                    **capture_final(self.root)})
        if event in {"FAILED", "INTERRUPTED"}:
            self.manifest["status"] = event.lower()
        if event in {"SUCCESS", "FAILED", "INTERRUPTED"}:
            record["output_tail"] = list(self.output_tails.get(unit.unit_id, ()))
        write_json(self.report / filename, record)
        self.save()
        if event in {"SUCCESS", "SKIP_VALID", "FAILED", "INTERRUPTED"}:
            self.refresh()

    def child_output(self, line: str, unit_id: str | None = None):
        unit_id = unit_id or self.current_unit_id
        self.output_tails.setdefault(unit_id, deque(maxlen=80)).append(line[:4000])
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "GRT" and parts[2:4] == ["cache", "hit:"]:
            self.cached_stages_by_unit.setdefault(unit_id, set()).add(parts[1])

    def refresh(self):
        write_json(self.report / "final_summary.json", final_summary(self.root, self.report))
        render(self.report)

    def finish(self, error: str | None = None):
        if error:
            self.manifest["errors"].append(error)
            self.manifest["status"] = "failed"
            for filename, record in self.records.values():
                if record["status"] == "running":
                    record["status"] = "failed"
                    record["history"].append({"at": now(), "event": "FAILED", "message": error})
                    write_json(self.report / filename, record)
        elif self.manifest["status"] == "running":
            self.manifest["status"] = "interrupted"
        self.manifest["ended_at"] = now()
        for filename, record in self.records.values():
            if record["status"] == "pending":
                record["not_executed_reason"] = "pipeline_stopped_before_this_stage"
                write_json(self.report / filename, record)
        self.save()
        self.refresh()
        # Older releases wrote report sidecars beside the App delivery archives.
        # The report now ships inside both delivery archives, so remove stale
        # sidecars to leave only the two user-facing ZIPs.
        for suffix in (".report.html", ".report.zip"):
            (self.root.parent / f"{self.root.name}{suffix}").unlink(missing_ok=True)

    def delivery_failure(self, error: str):
        self.manifest["status"] = "failed"
        self.manifest["errors"].append(error)
        self.manifest["ended_at"] = now()
        self.save()
        self.refresh()


def embed_report_in_delivery_archives(root: Path, archives: list[Path]) -> list[dict[str, object]]:
    """Atomically attach the finalized report directory to delivery ZIPs."""
    root = root.resolve()
    report = root / "report"
    required = (report / "manifest.json", report / "report.html", report / "render_report.py")
    missing = next((path for path in required if not path.is_file()), None)
    if missing is not None:
        raise ValueError(f"final report artifact is missing: {missing}")
    report_files = [
        path for path in sorted(report.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]
    prefix = f"{root.name}/report/"
    prepared: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    artifacts: list[dict[str, object]] = []
    swap_complete = False
    try:
        for archive_path in archives:
            archive_path = archive_path.resolve()
            if not archive_path.is_file():
                raise FileNotFoundError(f"delivery archive is missing: {archive_path}")
            temporary = archive_path.with_name(
                f".{archive_path.name}.with-report.{uuid.uuid4().hex}.tmp"
            )
            shutil.copyfile(archive_path, temporary)
            try:
                with zipfile.ZipFile(temporary, "a", compression=zipfile.ZIP_DEFLATED) as archive:
                    if any(name.startswith(prefix) for name in archive.namelist()):
                        raise ValueError(f"delivery archive already contains a report: {archive_path}")
                    for path in report_files:
                        relative = path.relative_to(report).as_posix()
                        archive.write(path, prefix + relative)
                with zipfile.ZipFile(temporary) as archive:
                    corrupt = archive.testzip()
                    if corrupt is not None:
                        raise ValueError(f"delivery archive contains a corrupt member: {corrupt}")
                    names = set(archive.namelist())
                    for path in required:
                        member = prefix + path.relative_to(report).as_posix()
                        if member not in names:
                            raise ValueError(f"delivery archive is missing embedded report member: {member}")
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            prepared.append((archive_path, temporary))

        for archive_path, temporary in prepared:
            backup = archive_path.with_name(
                f".{archive_path.name}.before-report.{uuid.uuid4().hex}.bak"
            )
            os.replace(archive_path, backup)
            backups.append((archive_path, backup))
            os.replace(temporary, archive_path)
        artifacts = [
            {
                "file": archive_path.name,
                "path": str(archive_path),
                "size_bytes": archive_path.stat().st_size,
                "sha256": digest(archive_path),
            }
            for archive_path, _ in prepared
        ]
        swap_complete = True
    except Exception:
        for archive_path, backup in reversed(backups):
            if backup.exists():
                archive_path.unlink(missing_ok=True)
                os.replace(backup, archive_path)
        raise
    finally:
        for _, temporary in prepared:
            temporary.unlink(missing_ok=True)
        if swap_complete:
            for _, backup in backups:
                backup.unlink(missing_ok=True)

    return artifacts


def prepare_start(root: Path, argv: list[str]):
    report = fresh_directory(root)
    run_id = "prepare-" + uuid.uuid4().hex
    sources = []
    for index, value in enumerate(argv):
        if value in {"--ref", "--ds"} and index + 2 < len(argv):
            name, original = argv[index + 1:index + 3]
        elif value in {"--reads", "--cen"} and index + 1 < len(argv):
            name, original = value[2:], argv[index + 1]
        else:
            continue
        path = Path(original).resolve()
        sources.append({"option": value, "name": name, "original_path": str(path),
                        "size_bytes": path.stat().st_size if path.is_file() else None,
                        "mtime_ns": path.stat().st_mtime_ns if path.is_file() else None,
                        "sha256": None, "identity_note": "原始文件记录路径、大小和修改时间；规范化 FASTA 另记 SHA-256。"})
    data = {"schema_version": SCHEMA, "run_id": run_id, "started_at": now(),
            "status": "running", "argv": argv, "sources": sources, "facts": {}}
    write_json(report / "inputs.json", data)
    # Invalidate old preparation provenance immediately, including on failure.
    write_json(root / "metadata/report_inputs.json", data)
    write_json(report / "manifest.json", {"schema_version": SCHEMA, "run_id": run_id,
               "workspace_name": root.name, "status": "preparing", "started_at": data["started_at"],
               "ended_at": None, "steps": [], "errors": []})
    render(report)


def prepare_finish(root: Path, exit_code: int):
    report = root / "report"
    data = read_json(report / "inputs.json")
    if data is None:
        raise ValueError("preparation report was not initialized")
    data.update(status="success" if exit_code == 0 else "failed", ended_at=now(), exit_code=exit_code)
    if exit_code == 0:
        data["facts"] = inputs(root)
    else:
        data["notes"] = ["输入准备未完成；没有把残留文件当成本次成功输出。详见 prepare 的终端错误。"]
    write_json(report / "inputs.json", data)
    write_json(root / "metadata/report_inputs.json", data)
    manifest = read_json(report / "manifest.json")
    manifest.update(status="prepared" if exit_code == 0 else "failed", ended_at=now())
    write_json(report / "manifest.json", manifest)
    render(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare-start", "prepare-finish", "embed-delivery-report"]
    )
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--archive", type=Path)
    # Preserve the exact prepare argv without interpreting its option names.
    raw = sys.argv[1:]
    split = raw.index("--") if "--" in raw else len(raw)
    args = parser.parse_args(raw[:split])
    root = args.server_dir.resolve()
    if args.action == "prepare-start":
        prepare_start(root, raw[split + 1:])
    elif args.action == "prepare-finish":
        prepare_finish(root, args.exit_code)
    else:
        if args.archive is None:
            parser.error("embed-delivery-report requires --archive")
        embed_report_in_delivery_archives(root, [args.archive])


if __name__ == "__main__":
    main()
