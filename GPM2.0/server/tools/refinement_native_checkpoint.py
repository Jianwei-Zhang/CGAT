"""Content-bound native completion, separate from current CGAT admission.

Only this trusted completion boundary creates a checkpoint. Orphan outputs and
parent exit zero alone are never adopted. The outer caller holds the workspace
lock; each new admission retains the original native attempt as immutable evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from datetime import datetime, timezone

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, relative_path
    from workspace_migration import durable_json, sync_directories
    from post_lgz_degap import digest, stat_key, atomic_json
    from refinement_tools import fingerprint
    from refinement_path import PathError
    from refinement_native_trace import TraceError
    from refinement_native_units import launch, capture_units, checked_json, SUMMARY
    from refinement_degap_units import FAMILY, FAMILY_NO_FILL, family_result
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, relative_path
    from .workspace_migration import durable_json, sync_directories
    from .post_lgz_degap import digest, stat_key, atomic_json
    from .refinement_tools import fingerprint
    from .refinement_path import PathError
    from .refinement_native_trace import TraceError
    from .refinement_native_units import launch, capture_units, checked_json, SUMMARY
    from .refinement_degap_units import FAMILY, FAMILY_NO_FILL, family_result

SCHEMA = "cgat.native-refinement-completion"
NAME = "native_complete.json"


class NativeProcessError(subprocess.CalledProcessError):
    def __str__(self):
        if self.returncode < 0:
            try:
                name = signal.Signals(-self.returncode).name
            except ValueError:
                name = str(-self.returncode)
            return f"Native tool process terminated by signal {name} (return code {self.returncode}). See the native execution log."
        return f"Native tool process exited with code {self.returncode}. See the native execution log."


def quartet_empty_outcome(code, log, directory, prepared):
    if code != 1:
        return None
    lines = log.read_text(errors="replace").splitlines()
    if not lines:
        return None
    if lines[-1].endswith("[ERROR] Input genome does not have valid gap."):
        return "no_eligible_flanks"
    if (not lines[-1].endswith("[ERROR] No gap can be closed.")
            or not any(line.endswith("All files processed.") for line in lines)):
        return None
    # In the pinned CGAT recipe successful empty alignments continue to the next
    # input. Every selected input must have produced its own fresh PAF.
    for path in prepared:
        name = "quartet.flank_map_" + Path(path).name + ".paf"
        # Pinned util.minimap moves PAFs to tmp; root is retained for older
        # sealed/controlled evidence, never as an unsealed recovery fallback.
        paf = directory / "tmp" / name
        if not paf.exists() and not paf.is_symlink():
            paf = directory / name
        if not paf.is_file() or paf.is_symlink():
            raise TraceError("quarTeT no-candidate outcome lacks a completed alignment artifact")
    return "no_candidates"



def validate_native_job_summary(payload, config):
    """A zero AutoGapfiller exit must not hide failed child processes.

    Pinned DEGAP calls an exit-zero unresolved job "failed" too. Keep that exact
    no-fill outcome separate from nonzero exits, exceptions and missing jobs.
    """
    try:
        native = payload["steps"]["step3"]["result"]
        configured = [row["job_name"] for row in config["jobs"]]
        families = {row["job_name"] for row in config["jobs"] if row.get("direction") == "bidirectional"}
        if len(configured) != len(set(configured)) or any(not isinstance(name, str) or not name for name in configured):
            raise ValueError("duplicate or invalid configured job")
        rows, hard_failures = [], []
        for field, statuses in (("completed", {"success"}), ("failed", {"failed", "error", "timeout", "exception"}), ("skipped", {"skipped"})):
            values = native[field + "_jobs"]
            if not isinstance(values, list) or type(native[field]) is not int or native[field] != len(values):
                raise ValueError("native job count does not match records")
            for value in values:
                if not isinstance(value, dict) or value.get("status") not in statuses:
                    raise ValueError("unexpected native job status")
                row = dict(value)
                exit_code = row.get("exit_code")
                if exit_code is not None and (type(exit_code) is not int or exit_code != 0):
                    hard_failures.append(row["job_name"])
                elif field == "failed":
                    expected = ({"Family search ended: " + state for state in FAMILY_NO_FILL}
                                if row["job_name"] in families else {"Job execution completed but did not produce expected results"})
                    if row["status"] != "failed" or row.get("error") not in expected:
                        hard_failures.append(row["job_name"])
                    else:
                        row["cgat_execution_outcome"] = "completed_without_native_fill"
                if field == "skipped" and row["job_name"] in families:
                    hard_failures.append(row["job_name"])
                rows.append(row)
        if (type(native["total_jobs"]) is not int or native["total_jobs"] != len(rows)
                or len(rows) != len(configured) or len({row["job_name"] for row in rows}) != len(rows)
                or {row["job_name"] for row in rows} != set(configured)):
            raise ValueError("missing or duplicated native child jobs")
        result = {"total_jobs": len(rows), "jobs": rows, "hard_failures": hard_failures}
        return result
    except (KeyError, TypeError, ValueError) as error:
        raise PathError("DEGAP native child-job summary is incomplete: " + str(error)) from error


def fasta_facts(path, expected_names):
    """One bounded pass binds file bytes and actual chromosome/N identities."""
    before = stat_key(path)
    raw_sha, records = hashlib.sha256(), {}
    name, length, n_bases, sequence_sha = None, 0, 0, None
    def finish():
        if name is None:
            return
        if name in records or length == 0:
            raise PathError("native FASTA has duplicate or empty chromosome")
        records[name] = {"length": length, "sha256": sequence_sha.hexdigest(), "n_bases": n_bases}
    with path.open("rb") as stream:
        line_start = True
        while raw := stream.readline(1024 * 1024):
            raw_sha.update(raw)
            if line_start and raw.startswith(b">"):
                if len(raw) == 1024 * 1024 and not raw.endswith(b"\n"):
                    raise PathError("native FASTA header is unreasonably long")
                finish()
                fields = raw[1:].split()
                if not fields:
                    raise PathError("native FASTA has an empty header")
                name = fields[0].decode("utf-8")
                length, n_bases, sequence_sha = 0, 0, hashlib.sha256()
            else:
                sequence = raw.strip().upper()
                if sequence:
                    if name is None or re.fullmatch(rb"[ACGTRYSWKMBDHVN]+", sequence) is None:
                        raise PathError("native FASTA has missing header or invalid DNA sequence")
                    length += len(sequence)
                    n_bases += sequence.count(b"N")
                    sequence_sha.update(sequence)
            line_start = raw.endswith(b"\n")
    finish()
    if not records or (expected_names is not None and set(records) != set(expected_names)) or stat_key(path) != before:
        raise PathError("native assembly has missing/unexpected chromosomes or changed during validation")
    return raw_sha.hexdigest(), records, before


def dependency_roles(input_hashes, paths):
    result = {}
    for name, sha in input_hashes.items():
        role = name
        for key in ("01_inputs", "02_jobs", "03_native"):
            prefix = str(paths[key])
            if name == prefix or name.startswith(prefix + "/"):
                role = "@" + key + name[len(prefix):]
                break
        if role in result:
            raise PathError("duplicate native input role")
        result[role] = sha
    return result


def binding(invocation, recipe, paths, input_hashes):
    """Normalize declared attempt roles, not arbitrary textual substrings."""
    aliases = [(str(paths[name]), "@" + name) for name in ("01_inputs", "02_jobs", "03_native")]
    command, i = [], 0
    thread_option = "--thread" if invocation.tool in {"degap", "tgsgapcloser"} else "-t"
    while i < len(invocation.command):
        item = invocation.command[i]
        if item == thread_option:
            if i + 1 >= len(invocation.command) or invocation.command[i + 1] != str(recipe.get("threads", invocation.recipe["threads"])):
                raise PathError("unexpected native thread argument")
            command += [item, "@native_threads"]
            i += 2
            continue
        for prefix, role in aliases:
            if item == prefix or item.startswith(prefix + "/"):
                item = role + item[len(prefix):]
                break
        command.append(item)
        i += 1
    cwd = str(invocation.cwd)
    for prefix, role in aliases:
        if cwd == prefix or cwd.startswith(prefix + "/"):
            cwd = role + cwd[len(prefix):]
            break
    native_recipe = {key: value for key, value in invocation.recipe.items() if key not in {"threads", "reads"}}
    return {"tool": invocation.tool, "command": command, "cwd": cwd,
            "required_outputs": list(invocation.required_outputs), "native_recipe": native_recipe,
            "native_inputs": dependency_roles(input_hashes, paths),
            "runtime_sha256": recipe["runtime_sha256"], "reads": recipe["reads"],
            "baseline_sha256": recipe["baseline_sha256"], "baseline_final_path_sha256": recipe["baseline_final_path_sha256"],
            "baseline_source_files": recipe["baseline_source_files"],
            "native_input_sha256": recipe.get("native_input_sha256", recipe["baseline_sha256"]),
            "chromosome_names": recipe.get("chromosome_names"),
            "conversions": recipe.get("conversions", {}),
            "environment": {name: invocation.environment.get(name) for name in
                            ("LC_ALL", "LANG", "CGAT_LR_PROGRAM_DIR", "LD_LIBRARY_PATH", "LD_PRELOAD", "PERL5LIB", "PYTHONPATH", "PYTHONHOME")}}


def checked_file(root, path, *, prefixes):
    relative = Path(path).absolute().relative_to(root).as_posix()
    relative_path(relative)
    safe = WorkspaceLayout.detect(root).path(relative)
    if not any(relative.startswith(prefix + "/") for prefix in prefixes) or safe.is_symlink() or not safe.is_file():
        raise PathError("native evidence must be a regular owned attempt file: " + relative)
    return safe, relative


def capture(root, tool, run_id, native_directory, invocation, code, log, chromosomes, parameters, prepared_files, driver,
            *, require_units=False, manual_attempt=None):
    base = WorkspaceLayout.detect(root).relative("04_refinement/" + TOOL_DIRECTORIES[tool])
    if manual_attempt is None:
        prefixes = [base + "/03_native/" + run_id, base + "/02_jobs/" + run_id]
    else:
        # Manual attempts have a separate namespace and never reuse the
        # whole-assembly scheduler's private units or checkpoints.
        name = Path(manual_attempt).absolute().relative_to(root).as_posix()
        if require_units or not re.fullmatch(
            r"(?:04_refinement/manual|08_refinement_jobs/02_manual|[.]run_all/manual_refinement)/[a-f0-9]{64}/02_jobs/[a-f0-9]{64}/"
            + re.escape(tool) + r"/[a-f0-9]{32}", name,
        ):
            raise PathError("invalid manual native evidence directory")
        prefixes = [name]
    artifacts, identities, genomes = {}, {}, {}
    def add(path, *, fasta=False, expected=chromosomes):
        path, relative = checked_file(root, path, prefixes=prefixes)
        before = stat_key(path)
        if fasta:
            sha, records, before = fasta_facts(path, expected)
            genomes[relative] = records
        else:
            sha = digest(path)
        if stat_key(path) != before:
            raise PathError("native evidence changed while sealing completion")
        artifacts[relative], identities[path] = sha, before
        return relative
    add(log)
    if driver is not None:
        add(driver)
    empty = quartet_empty_outcome(code, log, native_directory, prepared_files) if tool == "quartet" else None
    if code and not empty:
        raise NativeProcessError(code, invocation.command)
    jobs = None
    if empty:
        for parent in (native_directory, native_directory / "tmp"):
            for path in parent.glob("quartet.flank_map_*.paf"):
                add(path)
    else:
        for relative in invocation.required_outputs:
            path = native_directory / relative
            if not path.is_file() or path.is_symlink():
                raise PathError("native exit is not success: missing artifact " + relative)
            add(path, fasta=relative.endswith((".fasta", ".fa")) or relative == "tgs.scaff_seqs")
    terminal = None
    if tool == "degap":
        report = native_directory / invocation.required_outputs[0]
        payload = json.loads(report.read_text())
        if not isinstance(payload.get("gaps"), list) or any(not isinstance(row, dict) for row in payload["gaps"]):
            raise PathError("DEGAP native gap report is incomplete")
        summary, config = native_directory / "autogapfiller_summary.json", native_directory / "03.gap_filling/job_manager_config.json"
        add(summary)
        add(config)
        configuration = json.loads(config.read_text())
        jobs = validate_native_job_summary(json.loads(summary.read_text()), configuration)
        if jobs["hard_failures"]:
            failed = set(jobs["hard_failures"])
            details = [f"{row['job_name']}: {row.get('error') or row['status']}" for row in jobs["jobs"]
                       if row["job_name"] in failed]
            raise PathError("DEGAP child processes failed despite top-level exit 0: " + "; ".join(details))
        by_job = {row["job_name"]: row for row in jobs["jobs"]}
        families = {}
        for definition in configuration["jobs"]:
            if definition.get("direction") != "bidirectional":
                continue
            name = definition["job_name"]
            directory = native_directory / "03.gap_filling" / name
            if Path(name).name != name or name in {".", ".."} or Path(definition["job_dir"]) != directory:
                raise PathError("DEGAP family job directory does not match its native identity")
            add(directory / FAMILY)
            family = family_result(directory)
            job = by_job[name]
            closed = family["status"] == "closed"
            if (closed != (job["status"] == "success") or (not closed and
                    job.get("error") != "Family search ended: " + family["status"])):
                raise PathError("DEGAP family manifest disagrees with completed job")
            for name, expected in family["artifacts"].items():
                relative = add(directory / name)
                if artifacts[relative] != expected:
                    raise PathError("DEGAP family artifact changed during native capture")
            key = (definition["chromosome"], definition["gap_id"])
            if key in families:
                raise PathError("duplicate DEGAP family result for one native gap")
            families[key] = (directory, family)
        for row in payload["gaps"]:
            key = (row.get("chromosome"), row.get("gap_id"))
            if row.get("report_direction") == "bidirectional" or key in families:
                if key not in families or row.get("report_direction") != "bidirectional":
                    raise PathError("DEGAP family gap row lacks a matching native job")
                directory, family = families.pop(key)
                closed = family["status"] == "closed"
                candidate = directory / (family.get("integration_sequence") or family["final_sequence"])
                if ((row.get("filled") is True) != closed or row.get("junction") != family.get("junction")
                        or (closed and Path(row.get("final_sequence_file") or "") != candidate)):
                    raise PathError("DEGAP family gap row does not bind the sealed integration result")
                continue  # Manifest-owned sequence can be empty for verified overlap deletion.
            if row.get("filled") is True:
                value = row.get("final_sequence_file")
                if not isinstance(value, str) or not value:
                    raise PathError("completed DEGAP candidate has no source FASTA")
                path = Path(value)
                add(path if path.is_absolute() else native_directory / path, fasta=True, expected=None)
        if families:
            raise PathError("missing DEGAP gap rows for completed family jobs")
        for row in configuration["jobs"]:
            if not row.get("job_dir"):
                continue  # Missing optional diagnostics is not missing scientific output.
            directory = Path(row["job_dir"])
            if not directory.is_absolute():
                directory = native_directory / directory
            for name in ("run.stdout.log", "run.stderr.log", "process.log"):
                path = directory / name
                if path.exists() or path.is_symlink():
                    add(path)
        visual = native_directory / "05.visualization/Global.report.html"
        if visual.exists() or visual.is_symlink():
            add(visual)
        terminal = (native_directory / invocation.required_outputs[1]).relative_to(root).as_posix()
    elif tool == "lrgapcloser":
        maximum = parameters["iterations"]
        iterations = [number for number in range(1, maximum + 1) if (native_directory / f"iteration-{number}/gapclosed.fasta").is_file()]
        if not iterations or iterations != list(range(1, len(iterations) + 1)):
            raise PathError("LR_Gapcloser iterations are incomplete")
        for number in iterations:
            relative = (native_directory / f"iteration-{number}/gapclosed.fasta").relative_to(root).as_posix()
            if relative not in genomes:
                add(root / relative, fasta=True)
            add(native_directory / f"iteration-{number}/tmp/info_filter2")
        terminal = (native_directory / f"iteration-{iterations[-1]}/gapclosed.fasta").relative_to(root).as_posix()
        if len(iterations) < maximum and any(row["n_bases"] for row in genomes[terminal].values()):
            raise PathError("LR_Gapcloser stopped early while gaps still remain")
    elif not empty:
        terminal = (native_directory / invocation.required_outputs[0]).relative_to(root).as_posix()
    unit_artifacts = ([] if manual_attempt is not None
                      else capture_units(root, tool, run_id, code, required=require_units))
    if unit_artifacts:
        summary_path = root / base / "02_jobs" / run_id / SUMMARY
        summary = checked_json(root, summary_path)
        if tool == "quartet":
            expected = [] if empty == "no_eligible_flanks" else ["flank_map_" + Path(path).name for path in prepared_files]
            if [row["unit"]["suffix"] for row in summary["units"]] != expected:
                raise PathError("native substeps do not cover every selected quarTeT input in order")
        elif tool == "degap":
            attempted = {row["job_name"]: row for row in jobs["jobs"] if row["status"] != "skipped"}
            covered = [row["unit"]["job_name"] for row in summary["units"]]
            if len(covered) != len(set(covered)) or set(covered) != set(attempted):
                raise PathError("DEGAP native substeps do not cover every attempted child")
            definitions = {row["job_name"]: row for row in configuration["jobs"]}
            left_definitions = {}
            for definition in configuration["jobs"]:
                if definition.get("direction") == "left":
                    left_definitions.setdefault((definition.get("chromosome"), definition.get("gap_id")), []).append(definition)
            for skipped in (row for row in jobs["jobs"] if row["status"] == "skipped"):
                definition = definitions[skipped["job_name"]]
                lefts = left_definitions.get((definition.get("chromosome"), definition.get("gap_id")), [])
                if (definition.get("direction") != "right" or skipped.get("reason") != "LEFT task succeeded"
                        or len(lefts) != 1 or attempted.get(lefts[0]["job_name"], {}).get("status") != "success"):
                    raise PathError("DEGAP skipped child lacks a successful LEFT dependency")
            for row in summary["units"]:
                name = row["unit"]["job_name"]
                expected_result = attempted[name]
                expected_config = {key: value for key, value in definitions[name].items() if key != "job_dir"}
                if row["unit"]["configuration"] != expected_config:
                    raise PathError("DEGAP unit geometry differs from its native job configuration")
                if (row["result"]["outcome"] == "completed") != (expected_result["status"] == "success"):
                    raise PathError("DEGAP native summary and terminal unit disagree")
    for path in unit_artifacts:
        add(path)
    result = {"outcome": empty or "completed", "artifacts": artifacts, "native_assembly": genomes.get(terminal, {}),
              "native_jobs": jobs}
    if manual_attempt is not None:
        result["terminal"] = terminal
    return result, identities


def find_completed(root, tool, native_binding, current_inputs):
    layout = WorkspaceLayout.detect(root)
    key = fingerprint(native_binding)
    parent = layout.path("04_refinement/" + TOOL_DIRECTORIES[tool] + "/02_jobs")
    for receipt in sorted(parent.glob("*/" + NAME)):
        try:
            run_id = receipt.parent.name
            if not re.fullmatch(r"[0-9a-f]{32}", run_id) or receipt.is_symlink():
                continue
            checked_file(root, receipt, prefixes=[layout.relative(f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}")])
            value = json.loads(receipt.read_text())
            checksum = value.pop("payload_sha256")
            if (checksum != fingerprint(value) or value.get("schema") != SCHEMA or value.get("schema_version") != 1
                    or value.get("status") != "completed" or value.get("tool") != tool or value.get("run_id") != run_id
                    or value.get("binding") != native_binding or value.get("native_key") != key):
                continue
            expected_native = layout.relative(f"04_refinement/{TOOL_DIRECTORIES[tool]}/03_native/{run_id}")
            expected_paths = {name: str(layout.path(f"04_refinement/{TOOL_DIRECTORIES[tool]}/{name}/{run_id}"))
                              for name in ("01_inputs", "02_jobs", "03_native")}
            if (value["native_root"] != expected_native or value["attempt_paths"] != expected_paths
                    or dependency_roles(value["input_dependencies"], expected_paths) != native_binding["native_inputs"]):
                continue
            prefixes = [expected_native, layout.relative(f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}")]
            identities = {}
            for relative, sha in value["result"]["artifacts"].items():
                path, _ = checked_file(root, root / relative, prefixes=prefixes)
                before = stat_key(path)
                if digest(path) != sha or stat_key(path) != before:
                    raise PathError("native completion artifact changed")
                identities[path] = before
            if not value["result"]["artifacts"]:
                continue
            for name, sha in value["input_dependencies"].items():
                path = Path(name)
                if not path.is_absolute():
                    raise PathError("native input dependency must have an absolute source path")
                before = stat_key(path)
                actual = current_inputs.get(name)
                if actual is None:
                    actual = digest(path)
                if actual != sha or stat_key(path) != before:
                    raise PathError("native completion input changed")
                identities[path] = before
            relative = receipt.relative_to(root).as_posix()
            identities[receipt] = stat_key(receipt)
            sha = digest(receipt)
            result = {**value["result"], "artifacts": {**value["result"]["artifacts"], relative: sha}}
            return {**value, "result": result, "reused": True, "receipt": relative, "receipt_sha256": sha, "identities": identities}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def execute(root, invocation, recipe, paths, record, identities, verify_inputs, *, chromosomes, parameters,
            input_hashes, prepared_files, driver_factory=None):
    root = Path(root).resolve()
    verify_inputs()
    native_binding = binding(invocation, recipe, paths, input_hashes)
    cached = find_completed(root, invocation.tool, native_binding, input_hashes)
    marker = paths["02_jobs"] / "invocation.json"
    validator = fingerprint({name: digest(Path(__file__).with_name(name)) for name in
                             ("refinement_native_checkpoint.py", "refinement_native_units.py", "refinement_degap_units.py", "refinement_tgs_units.py", "refinement_lr_units.py")})
    if cached is not None and cached.get("validator_revision") != validator:
        # A verifier/reporting fix is not a changed native program. Recheck the
        # original, sealed bytes under the current completion rules instead of
        # burning another native run or trusting an older validator blindly.
        try:
            old_root = WorkspaceLayout.detect(root).path(cached["native_root"])
            old_native = old_root / "output" if invocation.tool == "lrgapcloser" else old_root
            old_log = WorkspaceLayout.detect(root).path(f"04_refinement/{TOOL_DIRECTORIES[invocation.tool]}/02_jobs/{cached['run_id']}/native.log")
            old_driver = root / cached["execution"]["driver"] if cached["execution"].get("driver") else None
            result, observed = capture(root, invocation.tool, cached["run_id"], old_native, invocation,
                                        cached["execution"]["returncode"], old_log, chromosomes, parameters, prepared_files, old_driver)
            sealed = {name: sha for name, sha in cached["result"]["artifacts"].items() if name != cached["receipt"]}
            if result["artifacts"] != sealed:
                raise PathError("current completion rules require different or unsealed native evidence")
            cached["result"] = {**result, "artifacts": {**sealed, cached["receipt"]: cached["receipt_sha256"]}}
            cached["identities"].update(observed)
            verify_inputs()
        except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
            cached = None
    if cached is None:
        invocation.cwd.mkdir(parents=True, exist_ok=True)
        directory = paths["03_native"] / "output" if invocation.tool == "lrgapcloser" else paths["03_native"]
        if invocation.tool == "lrgapcloser" and directory.exists():
            raise PathError("LR_Gapcloser native output must not already exist")
        driver = driver_factory(invocation) if driver_factory else None
        log = paths["02_jobs"] / "native.log"
        launcher, launch_request = launch(root, invocation, paths, record, native_binding)
        if launch_request is not None:
            record["launcher_command"] = list(launcher)
            atomic_json(marker, record)
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        print(f"[REFINEMENT NATIVE START] tool={invocation.tool} run={record['run_id']} log={log}", flush=True)
        with log.open("xb") as stream:
            process = subprocess.run(launcher, cwd=invocation.cwd, env=invocation.environment,
                                     stdout=stream, stderr=subprocess.STDOUT)
        seconds = time.monotonic() - started
        record.update(native_returncode=process.returncode, native_status="validating", phase="native")
        record["timing"]["native_seconds"] = seconds
        atomic_json(marker, record)
        verify_inputs()
        try:
            # A failed producer may never write its substep summary. Report the
            # actual process exit first; capture still requires valid substeps
            # for a successful or explicitly supported no-candidate outcome.
            result, native_identities = capture(root, invocation.tool, record["run_id"], directory, invocation,
                                                process.returncode, log, chromosomes, parameters, prepared_files, driver,
                                                require_units=launch_request is not None)
            if launch_request is not None:
                substeps = checked_json(root, paths["02_jobs"] / SUMMARY)
                record["native_substeps"] = {"producer_run_id": record["run_id"], "completed": len(substeps["units"]),
                                             "computed": sum(not row["reused"] for row in substeps["units"]),
                                             "reused": sum(row["reused"] for row in substeps["units"]),
                                             "summary": (paths["02_jobs"] / SUMMARY).relative_to(root).as_posix()}
        except Exception:
            record.update(native_status="failed", phase="native")
            atomic_json(marker, record)
            raise
        identities.update(native_identities)
        verify_inputs()
        value = {"schema": SCHEMA, "schema_version": 1, "status": "completed", "tool": invocation.tool,
                 "run_id": record["run_id"], "native_key": fingerprint(native_binding), "binding": native_binding,
                 "validator_revision": validator,
                 "native_root": paths["03_native"].relative_to(root).as_posix(), "input_dependencies": input_hashes,
                 "attempt_paths": {name: str(paths[name]) for name in ("01_inputs", "02_jobs", "03_native")},
                 "execution": {"command": list(invocation.command), "cwd": str(invocation.cwd), "threads": record["threads"],
                               "returncode": process.returncode, "native_seconds": seconds, "started_at": started_at,
                               "driver": driver.relative_to(root).as_posix() if driver is not None else None,
                               **({"launcher_command": list(launcher), "native_substeps": record["native_substeps"]}
                                  if launch_request is not None else {}),
                               "ended_at": datetime.now(timezone.utc).isoformat()}, "result": result}
        for relative in result["artifacts"]:
            with (root / relative).open("rb") as stream:
                os.fsync(stream.fileno())
        sync_directories(*((root / relative).parent for relative in result["artifacts"]))
        layout = WorkspaceLayout.detect(root)
        if layout.project_delivery:
            try:
                try:
                    from refinement_scratch import capture_scratch
                except ModuleNotFoundError:
                    from .refinement_scratch import capture_scratch
                value["scratch_inventory"] = capture_scratch(layout, invocation.tool, paths["03_native"], result["artifacts"])
            except (ImportError, OSError, ValueError) as exc:
                # Optional maintenance metadata is never a reason to rerun a successful native tool.
                print(f"[NATIVE SCRATCH] no compaction inventory recorded: {exc}", flush=True)
        value["payload_sha256"] = fingerprint(value)
        receipt = paths["02_jobs"] / NAME
        durable_json(receipt, value)
        relative = receipt.relative_to(root).as_posix()
        sha = digest(receipt)
        result = {**result, "artifacts": {**result["artifacts"], relative: sha}}
        identities[receipt] = stat_key(receipt)
        cached = {**value, "result": result, "reused": False, "receipt": relative, "receipt_sha256": sha, "identities": native_identities}
    else:
        identities.update(cached["identities"])
        paths["03_native"] = WorkspaceLayout.detect(root).path(cached["native_root"])
        record["requested_threads"] = record["threads"]
        record["threads"] = cached["execution"]["threads"]
        if "threads" in recipe:
            recipe["threads"] = record["threads"]
        record["timing"]["native_seconds"] = 0.0
        record["command"], record["cwd"] = cached["execution"]["command"], cached["execution"]["cwd"]
        verify_inputs()
    for name in ("launcher_command", "native_substeps"):
        if name in cached["execution"]:
            record[name] = cached["execution"][name]
    record.update(native_reused=cached["reused"], native_executed=not cached["reused"], native_status="success", phase="admission",
                  native_returncode=cached["execution"]["returncode"], recipe_sha256=fingerprint(recipe),
                  native_origin={"run_id": cached["run_id"], "native_root": cached["native_root"],
                                 "receipt": cached["receipt"], "receipt_sha256": cached["receipt_sha256"],
                                 "validator_revision": cached["validator_revision"], "verified_by": validator,
                                 **cached["execution"]})
    print(f"[REFINEMENT NATIVE {'REUSED' if cached['reused'] else 'COMPLETE'}] tool={invocation.tool} "
          f"origin={cached['run_id']} admission={record['run_id']} native_threads={cached['execution']['threads']}", flush=True)
    atomic_json(paths["01_inputs"] / "recipe.json", recipe)
    atomic_json(marker, record)
    return cached
