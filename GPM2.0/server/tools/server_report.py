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
from server_report_io import SCHEMA, local_path, now, read_json, write_json
from render_server_report import render

TITLES = {
    "prepare": "输入准备", "assign": "染色体归属与排列",
    "grt_prepare": "质量评估、q0 与供体构建", "grt_step1": "GRT Step1",
    "grt_step23": "GRT Step2 / Step3", "grt_telomere_finalize": "端粒处理与最终路径",
    "finalize_evidence": "证据整理与结果校验", "package_full": "完整包交付",
    "package_light": "轻量包交付", "step1_round1": "Step1 · 第一阶段",
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
        self.output_tail = deque(maxlen=80)
        self.cached_stages = set()
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
            self.output_tail.clear()
            self.cached_stages.clear()
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
                    substage["execution"] = "cache_reused" if substage["stage_id"] in self.cached_stages else "computed"
                    write_json(path, substage)
            if unit.unit_id == "grt_telomere_finalize":
                write_json(self.report / "final_snapshot.json", {
                    "schema_version": SCHEMA, "run_id": self.run_id,
                    **capture_final(self.root)})
        if event in {"FAILED", "INTERRUPTED"}:
            self.manifest["status"] = event.lower()
        if event in {"SUCCESS", "FAILED", "INTERRUPTED"}:
            record["output_tail"] = list(self.output_tail)
        write_json(self.report / filename, record)
        self.save()
        if event in {"SUCCESS", "SKIP_VALID", "FAILED", "INTERRUPTED"}:
            self.refresh()

    def child_output(self, line: str):
        self.output_tail.append(line[:4000])
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "GRT" and parts[2:4] == ["cache", "hit:"]:
            self.cached_stages.add(parts[1])

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
        # These sidecars are outside the data ZIPs so their recorded ZIP hashes
        # are final and do not create a report/archive checksum cycle.
        html_target = self.root.parent / f"{self.root.name}.report.html"
        html_temporary = html_target.with_suffix(".html.tmp")
        shutil.copyfile(self.report / "report.html", html_temporary)
        os.replace(html_temporary, html_target)
        zip_target = self.root.parent / f"{self.root.name}.report.zip"
        temporary = zip_target.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(self.report.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, "report/" + path.relative_to(self.report).as_posix())
            os.replace(temporary, zip_target)
        finally:
            temporary.unlink(missing_ok=True)


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
    parser.add_argument("action", choices=["prepare-start", "prepare-finish"])
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, default=0)
    # Preserve the exact prepare argv without interpreting its option names.
    raw = sys.argv[1:]
    split = raw.index("--") if "--" in raw else len(raw)
    args = parser.parse_args(raw[:split])
    root = args.server_dir.resolve()
    if args.action == "prepare-start":
        prepare_start(root, raw[split + 1:])
    else:
        prepare_finish(root, args.exit_code)


if __name__ == "__main__":
    main()
