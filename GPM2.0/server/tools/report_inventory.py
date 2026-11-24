"""Physical (not logical) report paths. Never follow links into user input or scratch trees."""

import json
import os
from pathlib import Path
import re
from stat import S_ISREG

from delivery_archive import delivery_path
from run_orchestration import sha256_file
from workspace_layout import relative_path, TOOL_DIRECTORIES

SHA = re.compile("[0-9a-f]{64}")


def physical(root, relative):
    path = root
    for part in relative_path(relative).split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink in report path")
    return path


def obj(root, rel):
    with physical(root, rel).open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def file_href(root, rel, report_dir="06_report"):
    try:
        path = physical(root, rel)
        if path.is_file():
            return os.path.relpath(path, root / report_dir)
    except (ValueError, OSError):
        pass
    return None


def tree(layout):
    # Count all regular files once, but do not publish private input names, enumerate
    # millions of unit directories into the VM, or traverse symlinks.
    root = layout.root
    roles = (
        (
            [
                (s, r)
                for s, r in zip(
                    (
                        "01_inputs",
                        "02_alignments",
                        "03_lgz",
                        "04_refinement",
                        "05_final",
                        "06_report",
                        "07_delivery",
                    ),
                    ("inputs", "alignment", "lgz", "refinement", "final", "report", "delivery"),
                )
            ]
            + [(".runtime", "runtime"), (layout.relative(".lib"), "library")]
        )
        if layout.version == 2
        else [
            (s, r)
            for s, r in [
                ("data", "inputs"),
                ("runs", "alignment"),
                ("grt", "lgz"),
                ("degap", "refinement"),
                ("report", "report"),
                ("metadata", "metadata"),
                ("logs", "logs"),
                (".run_all", "runtime"),
                (".prepare_lib", "library"),
                ("tel", "telomeres"),
                ("cen", "centromeres"),
            ]
        ]
    )
    child_roles = {
        "01_reference": "reference",
        "02_assemblies": "assembly_inputs",
        "03_reads": "read_inputs",
        "01_q0": "q0",
        "02_step1": "lgz_step1",
        "03_step2": "lgz_step2",
        "04_step3": "lgz_step3",
        "05_evidence": "lgz_evidence",
        "automatic": "automatic_jobs",
        "manual": "manual_jobs",
        "details": "publication_details",
        "01_lgz": "lgz_report",
        "02_refinement": "tool_reports",
        "03_comparison": "gap_comparison",
        "cache": "runtime_cache",
        "checkpoints": "checkpoints",
        "01_automatic": "automatic_jobs",
        "02_manual": "manual_jobs",
    }
    if layout.version == 2 and not layout.project_delivery:
        roles.append(("08_refinement_jobs", "jobs"))

    def node(rel, role):
        base = root / rel
        item = {
            "path": rel,
            "kind": "directory",
            "stage_ref": role,
            "role_key": role,
            "exists": False,
            "file_count": 0,
            "protected": role in ("runtime", "library"),
            "naming_rules": [],
            "children": [],
            "child_count": 0,
        }
        if role == "runtime":
            item["naming_rules"] = ["never_delete_whole_runtime"]
        if role == "final" and layout.result_prefix:
            item["naming_rules"] = [f"{layout.result_prefix}.<version>.fa", "results.tsv"]
        if role == "delivery" and layout.project_delivery:
            item["naming_rules"] = [
                f"{layout.result_prefix}.{{full,light}}.{{tar.gz,zip}}",
                f"{layout.result_prefix}.auto.patch.zip",
            ]
        try:
            if not physical(root, rel).is_dir():
                return item
        except ValueError:
            return item
        item["exists"] = True
        counts, children, leaves = {}, {}, set()
        for parent, dirs, files in os.walk(base, followlinks=False):
            parent = Path(parent)
            dirs[:] = sorted(d for d in dirs if not (parent / d).is_symlink())
            parts = parent.relative_to(base).parts
            n = sum(S_ISREG((parent / f).lstat().st_mode) for f in files)
            for i in range(min(len(parts), 2) + 1):
                key = parts[:i]
                counts[key] = counts.get(key, 0) + n
            if len(parts) < 2:
                kids = dirs.copy()
                if role in ("final", "delivery", "report"):
                    for f in sorted(files):
                        if S_ISREG((parent / f).lstat().st_mode):
                            kids.append(f)
                            leaves.add((*parts, f))
                children[parts] = kids

        def fill(item, parts):
            kids = children.get(parts, [])
            item.update(file_count=counts.get(parts, 0), child_count=len(kids))
            for name in kids[:200]:
                child = {
                    **item,
                    "path": str(Path(item["path"]) / name),
                    "role_key": child_roles.get(name, role),
                    "naming_rules": [],
                    "children": [],
                }
                if (*parts, name) in leaves:
                    child.update(kind="file", file_count=1, child_count=0)
                else:
                    fill(child, (*parts, name))
                item["children"].append(child)

        fill(item, ())
        return item

    # Historical numbered layouts keep the prepared library *inside* .runtime;
    # only declare .lib at the root when the workspace actually declares it.
    return [node(rel, role) for rel, role in roles if "/" not in rel]


def pickup(layout, batch, manual, verify_content):
    root, prefix = layout.root, layout.result_prefix
    rows = []

    def add(
        category, key, rel, *, expected=None, enabled=True, committed=False, size=None, small=False, current=True
    ):
        href = file_href(root, rel) if rel else None
        exists = href is not None
        actual_size = (root / rel).stat().st_size if exists else None
        sha = sha256_file(root / rel) if exists and (verify_content or small) else expected if exists else None
        valid = bool(
            exists
            and expected
            and expected == sha
            and (size is None or size == actual_size)
            and committed
            and current
        )
        status = (
            "published"
            if valid
            else "historical"
            if not current and exists
            else "observed"
            if exists
            else "not_enabled"
            if not enabled
            else "not_generated"
        )
        if exists and expected and (expected != sha or size is not None and size != actual_size):
            status = "changed"
            href = None
        rows.append(
            dict(
                category=category,
                label_key=key,
                relpath=rel,
                href=href,
                exists=exists,
                status=status,
                size_bytes=actual_size,
                sha256=sha,
                sha256_short=sha[:12] if sha else None,
                publication_verified=valid,
                checksum_source="content" if exists and (verify_content or small) else "receipt" if sha else None,
            )
        )

    if prefix:
        catalog = "05_final/results.tsv"
        try:
            from job_final_catalog import _read_catalog, OWNERS

            automatic, other = _read_catalog(layout)
            binding = obj(root, OWNERS + "/results.tsv.json")["next"]
        except (OSError, ValueError, KeyError, TypeError):
            automatic, other, binding = [], [], None
        if binding is not None and not SHA.fullmatch(binding):
            raise ValueError("invalid catalog hash")
        add("catalog", "genome_catalog", catalog, expected=binding, committed=True, small=True)
        found = set()
        for version, attempt, state, _, _, name, sha, transaction in automatic + other:
            if name != f"{prefix}.{version}.fa" or not SHA.fullmatch(sha) or "/" in name:
                continue
            found.add(version)
            rec = (batch or {}).get("tools", {}).get(version, {})
            current = (
                version == "lgz"
                or version.startswith("manual-")
                or state == rec.get("status") == "published"
                and transaction == rec.get("publication_transaction")
            )
            add("fasta", version, "05_final/" + name, expected=sha, committed=bool(transaction), current=current)
        for version in ("lgz", *TOOL_DIRECTORIES):
            if version not in found:
                add(
                    "fasta",
                    version,
                    f"05_final/{prefix}.{version}.fa",
                    enabled=version == "lgz" or version in (batch or {}).get("tools", {}),
                )
    elif layout.version == 2:
        add("fasta", "lgz", layout.relative("05_final/00_lgz/assembly.fa"))
    else:
        try:
            final = obj(root, layout.relative("metadata/grt_final_path.json"))
            relative = relative_path(final["q4_relpath"])
        except (ValueError, KeyError, OSError):
            relative = None
        add("fasta", "lgz", relative)
    proof = {}
    committed = {}
    if layout.project_delivery:
        from project_delivery_publish import HOME, _checked_receipt, _names
        from delivery_archive import archive_options

        try:
            pending = physical(root, HOME + "/publishing.json")
            if not pending.exists():
                proof = obj(root, HOME + "/committed.json")
                committed = _checked_receipt(proof, _names(layout, archive_options(root)[0]))
        except (ValueError, OSError, KeyError, TypeError):
            pass
    for mode in ("full", "light", "auto"):
        rel = None
        if mode != "auto":
            p = delivery_path(root, mode)
            rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else None
        elif layout.project_delivery:
            rel = f"07_delivery/{prefix}.auto.patch.zip"
        add(
            "app" if mode != "auto" else "auto_patch",
            mode,
            rel,
            expected=committed.get(mode),
            committed=mode in committed,
            enabled=mode != "auto" or bool((batch or {}).get("tools")),
            size=proof.get("files", {}).get(mode, {}).get("size_bytes"),
        )
        if layout.version == 1 and mode in ("full", "light"):
            # Legacy archives are *siblings*. Describe the known name, but never
            # read an external payload or construct a link out of the workspace.
            rows[-1]["relpath"] = "../" + p.name
            rows[-1]["status"] = "external_not_inspected"
    if layout.version == 2 and not layout.project_delivery:
        from refinement_commit import current_publication

        for tool, record in (batch or {}).get("tools", {}).items():
            if record.get("status") != "published":
                continue
            journal = current_publication(root, tool, verify=False)
            if (
                not journal
                or journal["transaction"] != record.get("publication_transaction")
                or journal["run_id"] != record.get("run_id")
            ):
                continue
            code = TOOL_DIRECTORIES[tool]
            final_dir = layout.relative("05_final/" + code)
            if not prefix:
                add(
                    "fasta",
                    tool,
                    final_dir + "/assembly.fa",
                    expected=journal["areas"]["final"]["new"]["files"].get("assembly.fa"),
                    committed=True,
                )
            home = layout.relative("07_delivery/" + code)
            rel = home + "/delivery.json"
            files = journal["areas"]["delivery"]["new"]["files"]
            if file_href(root, rel) and sha256_file(root / rel) == files.get("delivery.json"):
                for mode, item in obj(root, rel).get("archives", {}).items():
                    name = relative_path(item["file"])
                    if "/" not in name and files.get(name) == item["sha256"]:
                        add(
                            "app",
                            tool + "." + mode,
                            home + "/" + name,
                            expected=item["sha256"],
                            size=item.get("size_bytes"),
                            committed=True,
                        )
    if not manual:
        add("manual_patch", "manual_patch", None, enabled=False)
    for m in manual:
        add(
            "manual_patch",
            "manual_patch",
            m["patch_relpath"],
            expected=m.get("delivery_sha256"),
            committed=m["publication_verified"],
        )
    for key, logical in [("runner_log", "logs/run_all.log"), ("run_status", "logs/status.tsv")]:
        add("diagnostics", key, layout.relative(logical), small=True)
    return rows
