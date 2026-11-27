"""Pinned DEGAP terminal-child recovery, retaining the original process scheduler.

Only consumed final files/logs are restored into a fresh job. Round/checkpoint
folders and preprocessor state are never adopted as completed work.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import shlex
import shutil
import time
import uuid

try:
    from workspace_layout import automatic_dir
    from refinement_native_units import owned, file_fact, seal, checked_json, RECEIPT, SUMMARY, REQUEST, SCHEMA
    from post_lgz_degap import digest, stat_key, atomic_json
    from refinement_tools import fingerprint
    from refinement_path import PathError
    from run_orchestration import OrchestrationContractError
    from workspace_migration import sync_directories
except ModuleNotFoundError:
    from .workspace_layout import automatic_dir
    from .refinement_native_units import owned, file_fact, seal, checked_json, RECEIPT, SUMMARY, REQUEST, SCHEMA
    from .post_lgz_degap import digest, stat_key, atomic_json
    from .refinement_tools import fingerprint
    from .refinement_path import PathError
    from .run_orchestration import OrchestrationContractError
    from .workspace_migration import sync_directories

NO_FILL = "Job execution completed but did not produce expected results"
LOGS = ("process.log", "run.stdout.log", "run.stderr.log")
ENGINE_REVISION = "ee378649de25e09a28cae6e713d75487948f7c9f"
FAMILY = "family-result.json"
FAMILY_NO_FILL = frozenset({"terminal", "round_limit", "length_limit", "exhausted"})
FAMILY_FILES = {"connection-diagnostics.json", "family-components.fa", "family-report.html", "process.agp",
                "process.log", "process.summary", "junction-evidence.json", "junction-integration.fa"}
_CONTEXT = None
_ORIGINAL = None


def terminal(result):
    if (not isinstance(result, dict) or (result.get("exit_code") is not None
            and (type(result["exit_code"]) is not int or result["exit_code"] != 0))):
        return False
    return result.get("status") == "success" or (result.get("status") == "failed" and (
        result.get("error") == NO_FILL or result.get("error") in {"Family search ended: " + state for state in FAMILY_NO_FILL}))


def family_artifact_name(name):
    return isinstance(name, str) and (name in FAMILY_FILES or (Path(name).name == name and "\\" not in name and name.endswith(".final.fa")))


def family_result(directory):
    """Read the pinned upstream terminal manifest, not heuristic log strings."""
    path = directory / FAMILY
    if path.is_symlink() or not path.is_file():
        raise PathError("missing regular DEGAP family manifest")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise PathError("invalid DEGAP family manifest")
    payload = {k: v for k, v in value.items() if k != "payload_sha256"}
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    status, artifacts, final = value.get("status"), value.get("artifacts"), value.get("final_sequence")
    if (value.get("schema") != "degap-family-result-v1" or value.get("payload_sha256") != identity
            or status not in FAMILY_NO_FILL | {"closed"} or (status == "closed") != isinstance(value.get("winner"), dict)
            or not family_artifact_name(final) or not final.endswith(".final.fa") or not isinstance(artifacts, dict)
            or not ({final, "family-components.fa", "process.agp", "process.log", "process.summary",
                      "family-report.html", "connection-diagnostics.json"} <= set(artifacts))):
        raise PathError("incomplete or invalid DEGAP family manifest")
    integration = value.get("integration_sequence")
    if ((integration is not None) != isinstance(value.get("junction"), dict) or (integration is not None and (
            status != "closed" or integration != "junction-integration.fa"
            or not {integration, "junction-evidence.json"} <= set(artifacts)))):
        raise PathError("DEGAP family junction artifacts disagree")
    for name, sha in artifacts.items():
        if not family_artifact_name(name):
            raise PathError("unexpected DEGAP family artifact role")
        source = directory / name
        if source.is_symlink() or not source.is_file() or digest(source) != sha:
            raise PathError("DEGAP family artifact changed: " + name)
    return value


def output_names(directory):
    if (directory / FAMILY).is_file():
        return sorted({FAMILY, *LOGS, *family_result(directory)["artifacts"]})
    return [name for name in LOGS if (directory / name).exists() or (directory / name).is_symlink()] + sorted(path.name for path in directory.glob("*.final.fa"))


def outcome(directory, result, *, selected=None, family=False):
    if not terminal(result):
        raise PathError("DEGAP nonterminal child cannot be sealed")
    if family:
        value = family_result(directory)
        closed = value["status"] == "closed"
        if closed != (result["status"] == "success") or (not closed and result.get("error") != "Family search ended: " + value["status"]):
            raise PathError("DEGAP family state disagrees with scheduler outcome")
        rounds = value.get("total_rounds")
        if type(rounds) is not int or rounds < 0:
            raise PathError("invalid DEGAP completed family round count")
        chosen = (value.get("integration_sequence") or value["final_sequence"]) if closed else None
        if selected is not None and chosen != selected:
            raise PathError("DEGAP family selected result changed")
        return {"outcome": "completed" if closed else "completed_without_native_fill",
                "analysis": {"rounds": rounds, "fill_type": ("extension" if rounds else "direct_connection") if closed else "unfilled",
                             "fill_length": value.get("gap_length", 0), "selected": chosen, "family_status": value["status"]},
                "selected_fasta": {"name": chosen, "sha256": value["artifacts"][chosen]} if chosen else None,
                "recoverable": True}
    log = directory / "process.log"
    text = log.read_text() if log.exists() else ""
    direct = "Decided to use direct connection result" in text
    extension = "GAP can be closed!" in text and "Reach the maximum Length" not in text
    if (direct or extension) != (result["status"] == "success"):
        raise PathError("DEGAP child result and native consumer markers disagree")
    rounds = re.findall(r"ExtensionRound\s+(\d+)", text)
    analysis = {"rounds": int(rounds[-1]) if rounds else 0, "fill_type": "unfilled", "fill_length": 0, "selected": None}
    fasta = None
    eligible = []
    if direct or extension:
        eligible = (list(directory.glob("*.direct.final.fa")) if direct else
                    [path for path in directory.glob("*.final.fa") if ".direct.final.fa" not in str(path)])
        selected = selected or (eligible[0].name if eligible else None)
        if selected not in {path.name for path in eligible}:
            raise PathError("successful DEGAP child lacks its native final FASTA")
        try:
            from refinement_native_checkpoint import fasta_facts
        except ModuleNotFoundError:
            from .refinement_native_checkpoint import fasta_facts
        sha, records, _ = fasta_facts(directory / selected, None)
        lengths = re.findall(r"Overlap length:\s*(\d+)" if direct else r"totalExtensionLength:\s*(\d+)", text)
        analysis.update(fill_type="direct_connection" if direct else "extension", selected=selected,
                        fill_length=int(lengths[0 if direct else -1]) if lengths else 0)
        fasta = {"name": selected, "sha256": sha, "records": records}
    return {"outcome": "completed" if direct or extension else "completed_without_native_fill",
            "analysis": analysis, "selected_fasta": fasta, "recoverable": len(eligible) <= 1}


def prepared_index_fact(path):
    """Permit a fresh SQLite index to settle before its first stable byte read."""
    for delay in (0.1, 0.25, 1.0, None):
        try:
            return file_fact(path)
        except (OrchestrationContractError, PathError) as error:
            message = str(error)
            if delay is None or not message.startswith(("file changed before hashing:", "file changed while hashing:",
                                                        "file changed during hashing:",
                                                        "file changed during hash reuse:", "native unit input changed while hashing")):
                raise
            time.sleep(delay)


def input_binding(root, native, job):
    directory = owned(root, native / "03.gap_filling" / job["job_name"])
    if Path(job["job_dir"]).absolute() != directory:
        raise PathError("DEGAP configured job leaves its native attempt")
    script = owned(root, directory / "run.sh")
    lines = [line.strip() for line in script.read_text().replace("\\\n", " ").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1:
        raise PathError("DEGAP generated script must contain exactly one native command")
    argv = shlex.split(lines[0], comments=True)
    if not argv or argv[0] != "python" or "--mode" not in argv or argv[argv.index("--mode") + 1] != "gapfiller":
        raise PathError("unexpected DEGAP generated command")
    direction = job["direction"]
    options = [("--out", str(directory)), ("--seqleft", str(directory / "seqleft.fasta")), ("--seqright", str(directory / "seqright.fasta"))]
    if direction in {"left", "right"}:
        options.append(("--flag", direction))
    elif direction != "bidirectional" or any(value == "--flag" or value.startswith("--flag=") for value in argv):
        raise PathError("unexpected DEGAP family direction flag")
    for option, expected in options:
        if argv.count(option) != 1 or argv[argv.index(option) + 1] != expected:
            raise PathError("DEGAP generated command does not identify its child inputs")
    if any(any(char in value for char in "$`*?[]{};&|<>()") for value in argv):
        raise PathError("DEGAP generated command contains unsafe shell expansion")
    normalized = []
    for value in argv:
        for prefix, role in ((str(directory), "@job"), (str(native), "@native")):
            if value == prefix or value.startswith(prefix + "/"):
                value = role + value[len(prefix):]
                break
        normalized.append(value)
    files = {"flanks/" + name: owned(root, directory / name) for name in ("seqleft.fasta", "seqright.fasta")}
    preprocessor = owned(root, native / "01.reads_preprocessor")
    for entry in sorted(preprocessor.iterdir()):
        if entry.name == "preprocessing_config.json":
            continue
        entry = owned(root, entry)
        if entry.name == "preprocessing-inputs.json" and direction == "bidirectional":
            # The new upstream manager intentionally does not link this parent
            # receipt. Bind it as evidence without requiring a nonexistent link.
            files["prepared/" + entry.name] = entry
            continue
        linked = directory / entry.name
        if not linked.is_symlink() or linked.resolve() != entry.resolve():
            raise PathError("DEGAP job lacks its fresh prepared-read input link")
        for path in ([entry] if not entry.is_dir() else sorted(entry.rglob("*"))):
            path = owned(root, path)
            if path.is_file():
                files["prepared/" + path.relative_to(preprocessor).as_posix()] = path
    facts, identities = {}, {}
    for role, path in files.items():
        if not path.exists():
            facts[role], identities[path] = {"missing": True}, None
        else:
            read_fact = prepared_index_fact if role in {"prepared/hifi_reads.idx", "prepared/ont_reads.idx"} else file_fact
            facts[role], identities[path] = read_fact(path)
    identities[script] = stat_key(script)
    configuration = {key: value for key, value in job.items() if key != "job_dir"}
    return directory, {"kind": "degap.gap", "job_name": job["job_name"], "argv": normalized,
                       "configuration": configuration}, facts, identities


class DegapUnits:
    def __init__(self, request, *, create=False):
        self.request, self.root, self.run_id = request, Path(request["root"]).resolve(), request["run_id"]
        if not re.fullmatch(r"[0-9a-f]{32}", self.run_id):
            raise PathError("invalid DEGAP unit owner")
        self.base = automatic_dir(self.root, 'degap') / "02_jobs"
        self.jobs = owned(self.root, self.base / self.run_id)
        self.directory = owned(self.root, self.jobs / "native_units")
        self.native = owned(self.root, automatic_dir(self.root, 'degap') / "03_native" / self.run_id)
        if create:
            self.directory.mkdir(exist_ok=False)
            self.write_summary(None)

    def row(self, receipt, value):
        return {"key": value["key"], "unit": value["binding"]["unit"], "result": value["result"],
                "receipt": receipt.relative_to(self.root).as_posix(), "receipt_sha256": digest(receipt),
                "reused": value["origin"] is not None, "origin": value["origin"]}

    def write_summary(self, code):
        rows = []
        for receipt in sorted(self.directory.glob("*/" + RECEIPT)):
            if re.fullmatch(r"[0-9a-f]{64}", receipt.parent.name):
                rows.append(self.row(receipt, checked_json(self.root, receipt)))
        value = {"schema": "cgat.native-refinement-substeps", "schema_version": 1, "tool": "degap",
                 "run_id": self.run_id, "session": self.request["session"], "native_command": self.request["command"],
                 "native_returncode": code, "status": "running" if code is None else "finished", "units": rows}
        atomic_json(self.jobs / SUMMARY, {**value, "payload_sha256": fingerprint(value)})

    def find(self, key, binding):
        for receipt in sorted(self.base.glob("*/native_units/" + key + "/" + RECEIPT)):
            try:
                owner = receipt.parents[2].name
                if owner == self.run_id or not re.fullmatch(r"[0-9a-f]{32}", owner):
                    continue
                value = checked_json(self.root, receipt)
                if (value.get("schema") != SCHEMA or value.get("schema_version") != 1 or value.get("status") != "completed"
                        or value.get("tool") != "degap" or value.get("run_id") != owner or value.get("key") != key
                        or value.get("binding") != binding or value.get("origin") is not None
                        or value.get("execution", {}).get("computed") is not True or value["result"].get("recoverable") is not True):
                    continue
                validate_bundle(self.root, receipt, value)
                return receipt, value
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
        return None

    def run(self, executor, job_info):
        job = job_info["job"]
        directory, unit, facts, identities = input_binding(self.root, self.native, job)
        if output_names(directory) or any((directory / name).exists() or (directory / name).is_symlink()
                                          for name in ("checkpoint.info", ".skip_right")):
            raise PathError("unsealed DEGAP outputs already exist in fresh job")
        binding = {"session": self.request["session"], "unit": unit, "inputs": facts}
        key = fingerprint(binding)
        temporary = self.directory / ("incomplete-" + key + "-" + uuid.uuid4().hex)
        temporary.mkdir()
        seal(temporary / "attempt.json", {"binding": binding, "job_dir": str(directory), "event": "child_started"})
        cached, started = self.find(key, binding), time.monotonic()
        origin, original_seconds = None, None
        if cached is None:
            native_result = _ORIGINAL(executor, job_info)
            seal(temporary / "native_result.json", native_result)
            if not terminal(native_result):
                return native_result
            result = outcome(directory, native_result, family=job["direction"] == "bidirectional")
        else:
            receipt, producer = cached
            shutil.copyfile(receipt, temporary / "producer.json")
            if checked_json(self.root, temporary / "producer.json") != producer:
                raise PathError("DEGAP unit producer changed during restore")
            for name in producer["outputs"]:
                source = owned(self.root, receipt.parent / "outputs" / name)
                shutil.copyfile(source, directory / name)
                if digest(directory / name) != producer["artifacts"]["outputs/" + name]:
                    raise PathError("DEGAP restored consumer changed")
            original_seconds = producer["native_result"]["elapsed_time"]
            native_result = {**producer["native_result"], "job_name": job["job_name"], "job_dir": str(directory),
                             "elapsed_time": time.monotonic() - started}
            result = outcome(directory, native_result, family=job["direction"] == "bidirectional")
            if result != producer["result"]:
                raise PathError("DEGAP restored native consumer differs from producer")
            origin = {"run_id": producer["run_id"], "receipt": receipt.relative_to(self.root).as_posix(),
                      "receipt_sha256": digest(temporary / "producer.json")}
        if any((path.exists() or path.is_symlink()) if before is None else stat_key(path) != before
               for path, before in identities.items()):
            raise PathError("DEGAP prepared input changed during child execution")
        outputs, artifacts = output_names(directory), {}
        (temporary / "outputs").mkdir()
        for name in outputs:
            source = owned(self.root, directory / name)
            fact, before = file_fact(source)
            target = temporary / "outputs" / name
            shutil.copyfile(source, target)
            if digest(target) != fact["sha256"] or stat_key(source) != before:
                raise PathError("DEGAP child output changed while sealing")
            artifacts["outputs/" + name] = fact["sha256"]
        if origin:
            artifacts["producer.json"] = origin["receipt_sha256"]
        value = {"schema": SCHEMA, "schema_version": 1, "status": "completed", "tool": "degap", "run_id": self.run_id,
                 "key": key, "binding": binding, "origin": origin, "native_result": native_result, "result": result,
                 "outputs": outputs, "consumed_job": directory.relative_to(self.root).as_posix(), "artifacts": artifacts,
                 "execution": {"computed": origin is None, "seconds": time.monotonic() - started,
                               "producer_seconds": original_seconds if origin else native_result["elapsed_time"]}}
        # A bundle must reproduce the native consumer before it becomes reusable.
        validate_bundle(self.root, temporary / RECEIPT, value, receipt_required=False)
        for relative in artifacts:
            with (temporary / relative).open("rb") as stream:
                os.fsync(stream.fileno())
        sync_directories(temporary / "outputs")
        seal(temporary / RECEIPT, value)
        destination = self.directory / key
        if destination.exists() or destination.is_symlink():
            raise PathError("DEGAP child unit already exists")
        os.rename(temporary, destination)
        sync_directories(self.directory)
        # Each durable receipt is independently discoverable after interruption.
        # Rebuilding all N receipts after each child would make metadata O(N^2).
        # The parent writes the aggregate once when native execution terminates.
        print(f"[CGAT NATIVE UNIT {'REUSED' if origin else 'COMPLETE'}] {job['job_name']} key={key}", flush=True)
        return {**native_result, "cgat_native_unit": {"key": key, "reused": origin is not None,
                                                     "producer_seconds": value["execution"]["producer_seconds"],
                                                     "receipt": (destination / RECEIPT).relative_to(self.root).as_posix()}}


def validate_bundle(root, receipt, value, *, receipt_required=True):
    unit = value["binding"]["unit"]
    owner = value["run_id"]
    if not isinstance(owner, str) or not re.fullmatch(r"[0-9a-f]{32}", owner):
        raise PathError("DEGAP unit producer is invalid")
    expected_job = automatic_dir(root, 'degap') / "03_native" / owner / "03.gap_filling" / unit["job_name"]
    if (unit.get("kind") != "degap.gap" or Path(unit["job_name"]).name != unit["job_name"]
            or "\\" in unit["job_name"] or value["consumed_job"] != expected_job.relative_to(root).as_posix()
            or value["native_result"].get("job_name") != unit["job_name"]
            or value["native_result"].get("job_dir") != str(expected_job)):
        raise PathError("DEGAP unit result is not its declared native consumer")
    outputs = value["outputs"]
    family = unit.get("configuration", {}).get("direction") == "bidirectional"
    if (not isinstance(outputs, list) or len(outputs) != len(set(outputs))
            or any(not isinstance(name, str) or Path(name).name != name or "\\" in name
                   or (name not in LOGS and not (family_artifact_name(name) or name == FAMILY if family
                                                 else name.endswith(".final.fa"))) for name in outputs)
            or not {"run.stdout.log", "run.stderr.log"}.issubset(outputs)):
        raise PathError("DEGAP unit has an invalid consumed-output inventory")
    expected = {"outputs/" + name for name in outputs} | ({"producer.json"} if value["origin"] else set())
    if set(value["artifacts"]) != expected or not terminal(value["native_result"]):
        raise PathError("DEGAP unit artifacts/result are incomplete")
    artifacts = []
    for name, sha in value["artifacts"].items():
        path = owned(root, receipt.parent / name)
        if digest(path) != sha:
            raise PathError("DEGAP unit artifact changed")
        artifacts.append(path)
    saved_output = receipt.parent / "outputs"
    if family and set(outputs) != {FAMILY, *LOGS, *family_result(saved_output)["artifacts"]}:
        raise PathError("DEGAP family terminal outputs are incomplete")
    preferred = value["result"]["analysis"]["selected"]
    if outcome(saved_output, value["native_result"], selected=preferred, family=family) != value["result"]:
        raise PathError("DEGAP unit does not reproduce its native terminal consumer")
    if value["origin"]:
        producer = checked_json(root, receipt.parent / "producer.json")
        origin = value["origin"]
        if (not isinstance(origin["run_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", origin["run_id"])
                or producer.get("schema") != SCHEMA or producer.get("schema_version") != 1
                or producer.get("status") != "completed" or producer.get("tool") != "degap"
                or producer.get("run_id") != origin["run_id"] or producer.get("key") != value["key"]
                or producer.get("origin") is not None or producer.get("binding") != value["binding"]
                or producer.get("result") != value["result"] or producer.get("outputs") != outputs
                or producer.get("execution", {}).get("computed") is not True
                or not terminal(producer.get("native_result"))
                or producer.get("artifacts") != {name: sha for name, sha in value["artifacts"].items() if name != "producer.json"}
                or origin["receipt_sha256"] != value["artifacts"]["producer.json"]):
            raise PathError("DEGAP original producer is not the completed unit")
        expected_origin = automatic_dir(root, 'degap') / "02_jobs" / origin["run_id"] / "native_units" / value["key"] / RECEIPT
        expected_producer_job = automatic_dir(root, 'degap') / "03_native" / origin["run_id"] / "03.gap_filling" / unit["job_name"]
        if (producer["native_result"].get("job_name") != unit["job_name"]
                or producer["native_result"].get("job_dir") != str(expected_producer_job)
                or producer.get("consumed_job") != expected_producer_job.relative_to(root).as_posix()
                or origin["receipt"] != expected_origin.relative_to(root).as_posix()):
            raise PathError("DEGAP producer receipt has an unowned origin")
    return artifacts + ([receipt] if receipt_required else [])


def capture_units(root, run_id, code, *, required=False):
    jobs = automatic_dir(root, 'degap') / "02_jobs" / run_id
    if not (jobs / SUMMARY).exists() and not required:
        return []
    summary, request = checked_json(root, jobs / SUMMARY), checked_json(root, jobs / REQUEST)
    if (summary.get("schema") != "cgat.native-refinement-substeps" or summary.get("schema_version") != 1
            or summary.get("tool") != "degap" or summary.get("run_id") != run_id or summary.get("status") != "finished"
            or type(summary.get("native_returncode")) is not int or summary["native_returncode"] != code
            or summary["session"] != request["session"] or summary["native_command"] != request["command"]
            or request.get("tool") != "degap" or request.get("run_id") != run_id):
        raise PathError("DEGAP unit summary does not close its native producer")
    artifacts, seen = [jobs / SUMMARY, jobs / REQUEST], set()
    for row in summary["units"]:
        key = row["key"]
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key) or key in seen:
            raise PathError("DEGAP duplicated or invalid unit key")
        seen.add(key)
        receipt = owned(root, jobs / "native_units" / key / RECEIPT)
        value = checked_json(root, receipt)
        if (value.get("schema") != SCHEMA or value.get("schema_version") != 1 or value.get("status") != "completed"
                or value.get("tool") != "degap" or value.get("run_id") != run_id or value.get("key") != key
                or row["receipt"] != receipt.relative_to(root).as_posix() or row["receipt_sha256"] != digest(receipt)
                or fingerprint(value["binding"]) != key or value["binding"]["session"] != summary["session"]
                or row["unit"] != value["binding"]["unit"] or row["result"] != value["result"] or row["origin"] != value["origin"]
                or type(row["reused"]) is not bool or row["reused"] != bool(value["origin"])
                or value["execution"]["computed"] is not (not row["reused"])):
            raise PathError("DEGAP native unit closure is invalid")
        unit = row["unit"]
        if unit.get("kind") != "degap.gap" or Path(unit["job_name"]).name != unit["job_name"] or "\\" in unit["job_name"]:
            raise PathError("DEGAP unit has an unsupported consumer")
        directory = owned(root, automatic_dir(root, 'degap') / "03_native" / run_id / "03.gap_filling" / unit["job_name"])
        if (value["consumed_job"] != directory.relative_to(root).as_posix()
                or value["native_result"].get("job_name") != unit["job_name"] or value["native_result"].get("job_dir") != str(directory)):
            raise PathError("DEGAP native result leaves its consumer job")
        artifacts += validate_bundle(root, receipt, value)
        for name in value["outputs"]:
            path = owned(root, directory / name)
            if digest(path) != value["artifacts"]["outputs/" + name]:
                raise PathError("DEGAP consumed native child output changed")
            artifacts.append(path)
        if outcome(directory, value["native_result"], family=row["unit"]["configuration"].get("direction") == "bidirectional") != value["result"]:
            raise PathError("DEGAP native consumer no longer selects the sealed result")
    return list(dict.fromkeys(artifacts))


def _run_single_job(self, job_info):
    if _CONTEXT is None or _ORIGINAL is None:
        raise PathError("DEGAP recovery worker lost its pinned fork context")
    return DegapUnits(_CONTEXT).run(self, job_info)


def install_hook(module, request):
    global _CONTEXT, _ORIGINAL
    if multiprocessing.get_start_method() != "fork":
        raise PathError("pinned DEGAP recovery requires the managed Linux fork runtime")
    _CONTEXT, _ORIGINAL = request, module.JobExecutor._run_single_job
    module.JobExecutor._run_single_job = _run_single_job
