"""Single-ended telomere objective on the persistent family/round engine.

A telomeric read is a detection target, not a fictitious opposing seed family.
The Part2 direct (round-zero) check remains outside this extension adapter.
"""
import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil

from ExtensionFamilies import FamilySearch, atomic_json, fingerprint, read_json
from FamilyGap import prepare_context
from FamilyRound import SingleRound
from FamilyTools import content_hash


def reject_legacy_telomere(directory):
    root = Path(directory)
    if not (root / "families.json").exists() and (
            (root / "extension.log").exists() or any(root.glob("round[0-9]*"))):
        raise ValueError("Legacy single-ended telomere output detected; use a new output directory. "
                         "Old extension histories are not imported.")


def reject_legacy_telomere_project(directory):
    root = Path(directory)
    for status in (root / "telseeker_ctg.jobs").glob("*/result/status.tsv"):
        if not (status.parent.parent / "task-contract.json").exists():
            raise ValueError(f"Legacy telomere endpoint result: {status}; use a new output directory")
    for name in ("part2.chr.end.job", "telseeker_ctg.jobs"):
        for extension in (root / name).glob("*/extension"):
            reject_legacy_telomere(extension)


def load_telomere_result(directory):
    root = Path(directory)
    path = root / "telomere-result.json"
    payload = read_json(path)
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    if payload.get("schema") != "telomere-family-result-v1" or payload.get("payload_sha256") != fingerprint(body):
        raise ValueError(f"Invalid telomere result manifest: {path}")
    for name, digest in payload["artifacts"].items():
        artifact = Path(name)
        if not artifact.is_file() or content_hash(artifact) != digest:
            raise ValueError(f"Telomere result artifact changed: {artifact}")
    return payload


def run_telomere(extender, *, extend=None):
    root = Path(extender.extension_dir).resolve()
    reject_legacy_telomere(root)
    if (root / "telomere-result.json").exists():
        load_telomere_result(root)
    base = copy.copy(extender.base)
    # Prepared reads/index/parts live at the chromosome-end workspace, not
    # inside the extension checkpoint directory. Do not duplicate those inputs.
    base.out = str(Path(extender.work_path).resolve())
    base.terminalSeq = None
    tools = {}
    for name in ("nucmer", "delta-filter", "show-coords"):
        path = shutil.which(name)
        tools[name] = {"path": path, "sha256": content_hash(path) if path else None}
    context = prepare_context(base, {"objective": "telomere", "tools": tools})
    context.update({
        "driver": "family-telomere-v2", "end_type": extender.end_type,
        "telomeric_reads": {"path": str(Path(extender.telo_reads_file).resolve()),
                            "sha256": content_hash(extender.telo_reads_file)},
        "telomere_code": {name: content_hash(Path(__file__).parent / name)
                          for name in ("FamilyTelomere.py", "TelSeekerPart2.py", "TelomereTargets.py")},
    })
    runner = SingleRound(base, context=context)
    extension = extend or runner
    search = FamilySearch(root, [("end", "leftward" if extender.end_type == "L" else "rightward",
                                 extender.seed_file)], primary="end", context=context,
                          max_rounds=extender.max_rounds, max_length=extender.max_extension_length)

    def check(sequence, attempt, directory, *, verify_only=False):
        identity = fingerprint([context, content_hash(sequence), attempt])
        if verify_only and not (Path(directory) / "telomere" / "stage.json").is_file():
            raise ValueError("Missing completed telomere detection receipt")

        def detect(work):
            if verify_only:
                raise ValueError("Missing completed telomere detection receipt")
            extender.round_num = attempt
            result = extender._check_connection(work, Path(sequence))
            # Paths occur in the existing Part2 connection result contract.
            return {"connection": json.loads(json.dumps(result, default=str))}

        return runner._stage(Path(directory), "telomere", identity, detect)["connection"]

    def attempt(family, directory):
        result = extension(family, directory)
        if result.sequence_path:
            connection = check(result.sequence_path, family.attempts, directory)
            if connection:
                result = replace(result, terminal_reason="telomere_connected")
        return result

    def no_opposite(left, right):
        raise AssertionError("A telomere objective has no opposing family")

    search.run(attempt, no_opposite)
    # Even a completed scheduler must verify its terminal linker/evidence before
    # returning success. Also verify earlier completed negative detection stages.
    connection = None
    rounds = []
    last_length = search.families["end"].versions[0].length
    cumulative = 0
    artifacts = [root / "families.json", Path(extender.seed_file).resolve(),
                 Path(extender.telo_reads_file).resolve()]
    for number in range(1, search.completed_attempts + 1):
        directory = root / "attempts" / "0" / str(number)
        receipt = read_json(directory / "result.json")
        artifacts.append(directory / "result.json")
        record = {"round": number, "extension_length": 0, "extension_status": "no_extension",
                  "connection_found": False}
        if receipt["version"]:
            found = check(receipt["version"]["path"], number, directory, verify_only=True)
            version = receipt["version"]
            growth = version["length"] - last_length
            cumulative += growth
            last_length = version["length"]
            artifacts.append(Path(version["path"]))
            artifacts.extend(p for p in (directory / "telomere").rglob("*") if p.is_file())
            record.update(extension_length=growth, extension_status="extended",
                          extended_seq_file=version["path"], connection_found=bool(found))
            diagnostics_file = directory / "telomere" / "connection_check" / "connection-diagnostics.json"
            if diagnostics_file.is_file():
                record["target_search"] = read_json(diagnostics_file)
                record["target_evidence"] = str(diagnostics_file)
            if found:
                record.update(supporting_read_ids=found.get("supporting_read_ids", []),
                              support_count_lower_bound=found.get("support_count_lower_bound", 0))
                aln = found["alignment"]
                record.update(connected_read=found["read_id"], identity=aln["identity"],
                              aln_length=aln["len1"], linker_file=found["linker_file"],
                              checked_reads=found.get("checked_reads"), total_reads=found.get("total_reads"))
                for source, target in (("s1", "ref_start"), ("e1", "ref_end"),
                                       ("s2", "qry_start"), ("e2", "qry_end")):
                    if source in aln:
                        record[target] = aln[source]
            if receipt["terminal_reason"]:
                if not found:
                    raise ValueError("Terminal telomere attempt has no detection evidence")
                connection = found
        record["cumulative_extension"] = cumulative
        rounds.append(record)
    family = search.families["end"]
    extender.round_num = search.total_rounds
    extender.total_extension_length = search.total_length
    extender.connection_result = connection
    extender.end_signal = True
    stop_reason = {"terminal": "telomere_connected", "round_limit": "max_rounds_reached",
                   "length_limit": "max_length_reached"}.get(search.status, family.stop_reason)
    result = extender._generate_result(Path(family.current.path), stop_reason)
    (root / "extension.log").write_text(
        f"Chromosome End: {extender.chr_end}\nEngine: single-ended extension family\n"
        f"Total rounds: {search.total_rounds}\nTotal extension length: {search.total_length} bp\n"
        f"Stop reason: {stop_reason}\nCheckpoint: families.json\n")
    artifacts += [root / "extension.log", root / "extension.summary"]
    artifacts.extend(p for p in (Path(extender.work_path) / "telomere-alignments").rglob("*") if p.is_file())
    payload = {"schema": "telomere-family-result-v1", "result": result, "rounds": rounds,
               "config": {"max_rounds": extender.max_rounds,
                          "max_extension_length": extender.max_extension_length,
                          "edge": extender.edge, "kmer_num": extender.kmer_num,
                          "kmer_size": extender.kmer_size},
               "artifacts": {str(path.resolve()): content_hash(path) for path in artifacts}}
    payload["payload_sha256"] = fingerprint(payload)
    atomic_json(root / "telomere-result.json", payload)
    return result
