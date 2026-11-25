#!/usr/bin/env python3
"""Re-render an existing Server report without running tools or opening genome FASTAs."""

import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
from render_manual_report import render_batch
from refinement_commit import current_publication
from render_refinement_report import render_tool_pages, render_failure
from render_overview_report import render_overview
from render_server_report import render as render_lgz
from report_inventory import physical, obj
from report_overview_data import build_overview_view_model, BATCH
from report_privacy import hide_paths, private_reads, public_inputs, recipe_paths
from run_orchestration import sha256_file
from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, relative_path


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def dump(path, data):
    put(path, json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n")


def private_paths(layout):
    paths = set()
    root = layout.root
    for rel in (layout.relative("report") + "/inputs.json", layout.relative("metadata/report_inputs.json")):
        if physical(root, rel).is_file():
            paths.update(private_reads(obj(root, rel)))
    if layout.version == 2:
        config = ".runtime/refinement/config.json"
        if physical(root, config).is_file():
            paths.update(private_reads({}, obj(root, config).get("groups")))
    return sorted(paths, key=len, reverse=True)


def copy_lgz(layout, dest, paths):
    base = layout.relative("report")
    source = physical(layout.root, base)
    if not source.exists():
        return
    for path in source.rglob("*.json"):
        rel = path.relative_to(source).as_posix()
        p = physical(layout.root, base + "/" + rel)
        if not p.is_file():
            raise ValueError("non-regular LGZ report member")
        data = json.loads(p.read_text(encoding="utf-8"))
        dump(dest / rel, public_inputs(data, paths) if rel == "inputs.json" else hide_paths(data, paths))
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("render_server_report.py"), dest / "render_report.py")
    render_lgz(dest)


def copy_tool(layout, tool, source, dest, private):
    root = layout.root
    rel = source.relative_to(root).as_posix()
    manifest = obj(root, rel + "/manifest.json")
    summary = obj(root, rel + "/summary.json")
    run = summary["run_id"]
    files = manifest["files"]
    recipe = summary.get("execution", {}).get("recipe", {})
    private = sorted(set(private) | set(recipe_paths(recipe)), key=len, reverse=True)
    if (
        summary["tool"] != tool
        or not re.fullmatch(r"[\w.-]+", run)
        or not {"report.html", "summary.json"} <= files.keys()
    ):
        raise ValueError("invalid source report identity")
    receipt = current_publication(root, tool, verify=False)
    if receipt and (
        run != receipt["run_id"]
        or sha256_file(source / "manifest.json") != receipt["areas"]["report"]["new"]["files"]["manifest.json"]
    ):
        raise ValueError("source report does not match publication receipt")
    native_redacted = False
    for name, sha in files.items():
        if not (
            name in ("final_path.json", "summary.json") or name.startswith(("assets/", "native_visualization/"))
        ):
            continue
        p = physical(root, rel + "/" + name)
        if not p.is_file() or sha256_file(p) != sha:
            raise ValueError("changed report member: " + name)
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".json") and not name.startswith("native_visualization/"):
            dump(target, hide_paths(json.loads(p.read_text()), private))
        elif private:
            raw = p.read_bytes()
            replaced = raw
            for secret in private:
                replaced = replaced.replace(secret.encode(), b"[private reads]")
            if name.startswith("native_visualization/") and replaced != raw:
                native_redacted = True
            target.write_bytes(replaced)
        else:
            shutil.copyfile(p, target)
    if native_redacted and (dest / "native_visualization/manifest.json").is_file():
        nv_root = dest / "native_visualization"
        dump(
            nv_root / "manifest.json",
            dict(
                schema="cgat.detached-native-report-view.v1",
                tool=tool,
                source_native_manifest_sha256=sha256_file(physical(source, "native_visualization/manifest.json")),
                private_reads_redacted=True,
                files={
                    "native_visualization/" + f.relative_to(nv_root).as_posix(): sha256_file(f)
                    for f in sorted(nv_root.rglob("*"))
                    if f.is_file() and f.name != "manifest.json"
                },
            ),
        )
    summary = obj(dest, "summary.json")
    if summary.get("schema") == "cgat.refinement-failure-report":
        put(dest / "report.html", render_failure(summary))
        return
    code = TOOL_DIRECTORIES[tool]
    expected = manifest["binding"]["provenance_sha256"]
    for logical in (
        f"05_final/{code}/provenance.json",
        f".runtime/refinement/{code}/{run}/final/provenance.json",
        f"04_refinement/{code}/04_accepted/{run}/provenance.json",
    ):
        rel = layout.relative(logical)
        p = physical(root, rel)
        if p.is_file() and sha256_file(p) == expected:
            break
    else:
        raise ValueError("no manifest-bound provenance for " + tool)
    prov = obj(root, rel)
    if prov["run_id"] != run or prov["tool"] != tool:
        raise ValueError("provenance identity mismatch")
    for name, html in render_tool_pages(
        summary, hide_paths(prov, private), obj(dest, "final_path.json"), summary["artifacts"]
    ):
        put(dest / relative_path(name), html)


def detach(vm, destination):
    """Only hyperlink pages actually present in the detached tree."""

    def walk(data):
        if isinstance(data, list):
            for row in data:
                walk(row)
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "links" and isinstance(value, dict):
                    data[key] = {k: v for k, v in value.items() if internal(v)}
                elif key == "href" or key.endswith("_href"):
                    if not internal(value):
                        data[key] = None
                else:
                    walk(value)

    def internal(value):
        try:
            return bool(value and physical(destination, value).is_file())
        except (OSError, ValueError):
            return False

    walk(vm)


def regenerate(root, output):
    layout = WorkspaceLayout.detect(root)
    root = layout.root
    output = Path(output).absolute()
    if (
        output.resolve().is_relative_to(root)
        or root.is_relative_to(output.resolve())
        or any(p.is_symlink() for p in (output, *output.parents))
    ):
        raise ValueError("output must be a separate, non-symlinked directory outside the source")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output is not empty")
    if (
        not physical(root, layout.relative("report") + "/manifest.json").is_file()
        and not physical(root, "06_report/manual_refinement.json").is_file()
        and not physical(root, "06_report/report.html").is_file()
    ):
        raise ValueError("no existing Server report to regenerate")
    vm = build_overview_view_model(root)
    private = private_paths(layout)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        dest = Path(temp) / "report"
        dest.mkdir()
        copy_lgz(layout, dest / "01_lgz", private)
        if (dest / "01_lgz/report.html").is_file():
            vm["lgz_summary"]["href"] = "01_lgz/report.html"
        for tool, code in TOOL_DIRECTORIES.items():
            rel = "06_report/02_refinement/" + code
            src = physical(root, rel)
            if src.is_dir():
                dst = dest / "02_refinement" / code
                copy_tool(layout, tool, src, dst, private)
                # Detached output is never a replacement publication receipt.
                dump(
                    dst / "manifest.json",
                    dict(
                        schema="cgat.detached-tool-report.v1",
                        tool=tool,
                        source_report_manifest_sha256=sha256_file(physical(src, "manifest.json")),
                        files={
                            f.relative_to(dst).as_posix(): sha256_file(f)
                            for f in sorted(dst.rglob("*"))
                            if f.is_file()
                        },
                    ),
                )
        compare = physical(root, "06_report/03_comparison")
        if compare.is_dir():
            for folder in sorted(compare.iterdir()):
                if not BATCH.fullmatch(folder.name):
                    continue
                for name in ("comparison.json", "original_gaps.json", "gap_comparison.tsv"):
                    rel = "03_comparison/" + folder.name + "/" + name
                    p = physical(root, "06_report/" + rel)
                    if p.is_file():
                        target = dest / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if name == "comparison.json":
                            data = obj(root, "06_report/" + rel)
                            if data.get("batch_id") != folder.name:
                                raise ValueError("comparison batch identity mismatch")
                            # Old reports stored entire selections, including ignored files.
                            for row in data.get("tools", []):
                                row.pop("input_selection", None)
                                row["reads"] = [
                                    {k: r[k] for k in ("technology", "sha256") if k in r}
                                    for r in row.get("reads", [])
                                    if isinstance(r, dict)
                                ]
                            dump(target, hide_paths(data, private))
                        else:
                            shutil.copyfile(p, target)
        entries = []
        for b in vm["manual_summary"]["batches"]:
            bid = b["batch_sha256"]
            summary = obj(root, b["summary_relpath"])
            group = summary.get("reads", {})
            secrets = private + [r["path"] for rs in group.values() for r in rs if r.get("path")]
            summary = hide_paths(summary, secrets)
            summary["reads"] = {
                k: [{f: r.get(f) for f in ("technology", "sha256")} for r in rs] for k, rs in group.items()
            }
            folder = dest / "manual" / bid
            dump(folder / "summary.json", summary)
            put(
                folder / "report.html",
                render_batch(
                    summary, {"Overview / 总览": "../../report.html#manual-refinement", "Summary": "summary.json"}
                ),
            )
            b["report_href"] = f"manual/{bid}/report.html"
            entries.append(dict(summary=summary, links={"Batch report / 批次报告": b["report_href"]}))
        detach(vm, dest)
        html = render_overview(vm)
        if entries:
            from refine_report import INDEX_SCHEMA

            dump(
                dest / "manual_refinement.json",
                dict(
                    schema=INDEX_SCHEMA,
                    batches=[
                        {
                            **{k: e["summary"].get(k) for k in ("batch_sha256", "completed_at", "report_status")},
                            "results": [
                                {
                                    **{k: r.get(k) for k in ("tool", "version", "status")},
                                    "patch": {} if r.get("patch") is not None else None,
                                }
                                for r in e["summary"]["results"]
                            ],
                        }
                        for e in entries
                    ],
                ),
            )
        put(dest / "report.html", html)
        dump(dest / "overview_view_model.json", vm)
        dest.replace(output)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out-dir", type=Path)
    group.add_argument(
        "--in-place",
        action="store_true",
        help="Refresh only the receipt-bound overview, never rewrite immutable tool reports",
    )
    args = parser.parse_args(argv)
    if args.out_dir:
        print(regenerate(args.server_dir, args.out_dir))
        return
    from run_all_runner import WorkspaceLock, new_run_id
    from refinement_jobs_index import refresh_after_delivery

    layout = WorkspaceLayout.detect(args.server_dir)
    if layout.version != 2:
        raise ValueError("legacy workspaces have no sealed overview; use --out-dir")
    lock = WorkspaceLock(layout.root, new_run_id())
    lock.acquire()
    try:
        from report_overview_data import current_completion

        lgz = obj(layout.root, layout.relative("report") + "/manifest.json")
        completion = current_completion(layout, lgz["run_id"], recover=True)
        if not completion:
            raise ValueError("no sealed automatic batch; use --out-dir")
        run = Path(completion).stem
        refresh_after_delivery(layout.root, run, lock, verify_content=False)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
