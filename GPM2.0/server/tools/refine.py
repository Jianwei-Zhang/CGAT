#!/usr/bin/env python3
"""Run project-scoped manual refinement tasks and publish a result bundle."""
from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    # Isolation ignores PYTHONDONTWRITEBYTECODE; preserve a read-only
    # managed runtime explicitly before importing the workflow or stdlib.
    if not (sys.flags.isolated and sys.flags.dont_write_bytecode):
        os.execv(sys.executable, [sys.executable, "-I", "-B", os.path.abspath(__file__), *sys.argv[1:]])

from contextlib import ExitStack
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from zipfile import BadZipFile, ZipFile

if __name__ != "__main__":
    from refinement_commit import current_publication
    from run_all_runner import RunnerError, WorkspaceLock
    from run_orchestration import sha256_file as digest
    from server_source_identity import resolve_seed
    from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from workspace_migration import durable_json, rename_synced

SCHEMA = "cgat.app-refinement-tasks.v1"
PREPARED = "cgat.app-refinement-prepared.v1"
MANIFEST = "refinement_tasks.json"
MAX_MANIFEST = 8 * 1024 * 1024
MAX_GAP_BP = 100_000_000
TOOLS = ("degap", "lrgapcloser", "tgsgapcloser", "quartet")
TGS_HIFI_MINIMAP_PRESETS = frozenset({"-x asm20", "-x asm5", "-x asm10", "-x map-hifi", "-x map-pb"})
TGS_ONT_MINIMAP_PRESETS = frozenset({"-x ava-ont", "-x map-ont", "-x asm20", "-x asm10"})
QUARTET_MINIMAP_PRESETS = frozenset({"-x asm5", "-x asm10", "-x asm20", "-x map-hifi", "-x map-ont"})
TGS_CORRECTIONS = frozenset({"none", "native_racon"})


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def text(value):
    return isinstance(value, str) and bool(value) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def positive(value):
    return type(value) is int and 0 < value <= (1 << 63) - 1


def bounded_int(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def bounded_number(value, minimum, maximum, *, exclusive_min=False, exclusive_max=False):
    if type(value) not in (int, float):
        return False
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return False
    if exclusive_min and not (number > minimum):
        return False
    if not exclusive_min and not (number >= minimum):
        return False
    if exclusive_max and not (number < maximum):
        return False
    if not exclusive_max and not (number <= maximum):
        return False
    return True


def check_tool_parameters(value):
    if not isinstance(value, dict) or not set(value).issubset(set(TOOLS)):
        raise ValueError("invalid tool_parameters section")
    degap = value.get("degap")
    if degap is not None:
        allowed_degap = {
            "max_extension_rounds", "max_extension_bp", "kmer_filter",
            "kmer_size", "kmer_num", "edge", "filter_depth_hifi", "filter_depth_ont",
            "tel_n", "tel_r", "tel_mm",
        }
        if not isinstance(degap, dict) or not set(degap).issubset(allowed_degap):
            raise ValueError("invalid degap tool_parameters")
        if "max_extension_rounds" in degap:
            v = degap["max_extension_rounds"]
            if v != "unlimited" and not bounded_int(v, 1, 1000):
                raise ValueError("invalid degap max_extension_rounds")
        if "max_extension_bp" in degap:
            v = degap["max_extension_bp"]
            if v != "unlimited" and not bounded_int(v, 1000, MAX_GAP_BP):
                raise ValueError("invalid degap max_extension_bp")
        if "kmer_filter" in degap and type(degap["kmer_filter"]) is not bool:
            raise ValueError("invalid degap kmer_filter")
        if "kmer_size" in degap and not bounded_int(degap["kmer_size"], 11, 127):
            raise ValueError("invalid degap kmer_size")
        if "kmer_num" in degap and not bounded_int(degap["kmer_num"], 1, 1000):
            raise ValueError("invalid degap kmer_num")
        if "edge" in degap and not bounded_int(degap["edge"], 50, 50000):
            raise ValueError("invalid degap edge")
        for key in ("filter_depth_hifi", "filter_depth_ont"):
            if key in degap and degap[key] is not None and not bounded_number(degap[key], 0.0, 1.0, exclusive_min=True, exclusive_max=True):
                raise ValueError(f"invalid degap {key}")
        if "tel_n" in degap and not bounded_int(degap["tel_n"], 10, 10000):
            raise ValueError("invalid degap tel_n")
        if "tel_r" in degap and not bounded_number(degap["tel_r"], 0.01, 1.0):
            raise ValueError("invalid degap tel_r")
        if "tel_mm" in degap and not (type(degap["tel_mm"]) is int and degap["tel_mm"] in (0, 1)):
            raise ValueError("invalid degap tel_mm")

    lr = value.get("lrgapcloser")
    if lr is not None:
        if not isinstance(lr, dict) or not set(lr).issubset({"iterations", "tag_partitions"}):
            raise ValueError("invalid lrgapcloser tool_parameters")
        if "iterations" in lr and not bounded_int(lr["iterations"], 1, 20):
            raise ValueError("invalid lrgapcloser iterations")
        if "tag_partitions" in lr and not bounded_int(lr["tag_partitions"], 1, 16):
            raise ValueError("invalid lrgapcloser tag_partitions")

    tgs = value.get("tgsgapcloser")
    if tgs is not None:
        allowed_tgs = {
            "hifi_correction", "hifi_racon_rounds", "hifi_minimap",
            "ont_correction", "ont_racon_rounds", "ont_minimap",
        }
        if not isinstance(tgs, dict) or not set(tgs).issubset(allowed_tgs):
            raise ValueError("invalid tgsgapcloser tool_parameters")
        if "hifi_correction" in tgs and tgs["hifi_correction"] not in TGS_CORRECTIONS:
            raise ValueError("invalid tgsgapcloser hifi_correction")
        if "hifi_racon_rounds" in tgs and not bounded_int(tgs["hifi_racon_rounds"], 1, 5):
            raise ValueError("invalid tgsgapcloser hifi_racon_rounds")
        if "hifi_minimap" in tgs and tgs["hifi_minimap"] not in TGS_HIFI_MINIMAP_PRESETS:
            raise ValueError("invalid tgsgapcloser hifi_minimap")
        if "ont_correction" in tgs and tgs["ont_correction"] not in TGS_CORRECTIONS:
            raise ValueError("invalid tgsgapcloser ont_correction")
        if "ont_racon_rounds" in tgs and not bounded_int(tgs["ont_racon_rounds"], 1, 5):
            raise ValueError("invalid tgsgapcloser ont_racon_rounds")
        if "ont_minimap" in tgs and tgs["ont_minimap"] not in TGS_ONT_MINIMAP_PRESETS:
            raise ValueError("invalid tgsgapcloser ont_minimap")

    quartet = value.get("quartet")
    if quartet is not None:
        if not isinstance(quartet, dict) or not set(quartet).issubset({"minimap"}):
            raise ValueError("invalid quartet tool_parameters")
        if "minimap" in quartet and quartet["minimap"] not in QUARTET_MINIMAP_PRESETS:
            raise ValueError("invalid quartet minimap")


def unique_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate manifest field: {key}")
        value[key] = item
    return value


def checked_plan(value, witness):
    if not isinstance(value, dict) or set(value) != {"members", "start", "end"} or not isinstance(value["members"], list):
        raise ValueError("invalid seed plan")
    length = 0
    for member in value["members"]:
        if (not isinstance(member, dict) or set(member) != {"dataset", "name", "length", "start", "end", "fasta_sha256", "interval_sha256"}
                or not all(text(member[key]) for key in ("dataset", "name"))
                or not all(positive(member[key]) for key in ("length", "start", "end"))
                or not member["start"] <= member["end"] <= member["length"]
                or not any(sha(member[key]) for key in ("fasta_sha256", "interval_sha256"))
                or any(v is not None and not sha(v) for v in (member["fasta_sha256"], member["interval_sha256"]))):
            raise ValueError("invalid or unbound seed source interval")
        length += member["end"] - member["start"] + 1
    if (not length or length != abs(witness["end"] - witness["start"]) + 1
            or not all(positive(value[key]) for key in ("start", "end"))
            or (value["start"], value["end"]) != ((1, length) if witness["start"] <= witness["end"] else (length, 1))):
        raise ValueError("seed interval does not match its path orientation/length")


def check_manifest(value):
    from manual_snapshot import TASKS
    snap = isinstance(value,dict) and value.get("schema") == TASKS
    keys = {"schema", "export_id", "origin_fasta_sha256", "reads", "loci"} | ({"snapshot_sha256"} if snap else set())
    if (not isinstance(value, dict) or not keys.issubset(value) or set(value) - (keys | {"tool_parameters"}) or (snap and not sha(value["snapshot_sha256"]))
            or value["schema"] not in {SCHEMA,TASKS} or not sha(value["export_id"]) or not sha(value["origin_fasta_sha256"])):
        raise ValueError("not a supported project refinement task manifest")
    if "tool_parameters" in value:
        check_tool_parameters(value["tool_parameters"])
    reads, used = value["reads"], set()
    if not isinstance(reads, dict) or set(reads) != {"hifi", "ont"}:
        raise ValueError("invalid reads groups")
    for rows in reads.values():
        if not isinstance(rows, list):
            raise ValueError("invalid reads group")
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"path", "sha256"} or not text(row["path"])
                    or not row["path"].startswith("/") or row["path"] == "/" or row["path"] in used
                    or (row["sha256"] is not None and not sha(row["sha256"]))):
                raise ValueError("invalid or duplicate Server read path")
            used.add(row["path"])
    ids = set()
    if not isinstance(value["loci"], list) or not value["loci"]:
        raise ValueError("no refinement loci")
    for locus in value["loci"]:
        keys = {"id", "chr", "kind", "target", "tools", "witnesses", "seed_plans"}
        if not isinstance(locus, dict) or not keys.issubset(locus) or locus["kind"] not in ("gap", "tel_left", "tel_right"):
            raise ValueError("invalid refinement locus")
        kind = locus["kind"]
        identity = json.dumps([locus["chr"], kind, locus["target"]], ensure_ascii=False, separators=(",", ":"))
        if (not text(locus["chr"]) or not text(locus["target"])
                or locus["id"] != hashlib.sha256(identity.encode()).hexdigest() or locus["id"] in ids):
            raise ValueError("invalid or duplicate locus identity")
        ids.add(locus["id"])
        tools = locus["tools"]
        if (not isinstance(tools, list) or not tools or tools != [tool for tool in TOOLS if tool in tools]
                or (kind != "gap" and tools != ["degap"])):
            raise ValueError("invalid or duplicate locus tool")
        witnesses, plans = locus["witnesses"], locus["seed_plans"]
        labels = {"seqleft", "seqright"} if kind == "gap" else {"endpoint"}
        if (not isinstance(witnesses, dict) or not isinstance(plans, dict) or set(plans) != labels
                or set(witnesses) != labels | ({"target"} if kind == "gap" else set())):
            raise ValueError("invalid locus witnesses or seed labels")
        for label in labels:
            w = witnesses[label]
            common = {"segment_id", "kind", "start", "end"}
            if not isinstance(w, dict):
                raise ValueError("invalid contig witness")
            assembly = set(w) == common | {"assembly_ctg_id"} and positive(w["assembly_ctg_id"])
            source = set(w) == common | {"dataset", "contig"} and all(text(w[key]) for key in ("dataset", "contig"))
            extra = snap and (set(w)==common|{"patch_sha256"} or set(w)==common|{"reference","member_start","member_end"})
            if (not (assembly or source or extra) or w["kind"] != "ctg" or not text(w["segment_id"])
                    or not all(positive(w[key]) for key in ("start", "end"))):
                raise ValueError("invalid contig witness")
            checked_plan(plans[label], w)
            if extra or (source and snap):
                from manual_snapshot import check_witness
                check_witness(w,plans[label])
            if source and not snap:
                members = plans[label]["members"]
                if (len(members) != 1 or members[0]["dataset"] != w["dataset"] or members[0]["name"] != w["contig"]
                        or [members[0]["start"], members[0]["end"]] != sorted([w["start"], w["end"]])):
                    raise ValueError("seed plan does not match the source witness")
        if kind == "gap":
            size = locus.get("gap_bp")
            if (set(locus) != keys | {"gap_bp"} or not positive(size) or size > MAX_GAP_BP
                    or witnesses["target"] != {"segment_id": locus["target"], "kind": "gap", "gap_bp": size}
                    or len({witnesses[name]["segment_id"] for name in labels} | {locus["target"]}) != 3):
                raise ValueError("invalid original N run or duplicated Gap witness")
        elif (set(locus) != keys | {"motif"} or not isinstance(locus["motif"], str)
              or not re.fullmatch(r"[ACGT]+", locus["motif"]) or witnesses["endpoint"]["segment_id"] != locus["target"]):
            raise ValueError("invalid terminal witness or motif")


def _read_task_archive(archive):
    # Do not extract arbitrary paths or execute code from a task ZIP.
    with ZipFile(archive) as zipped:
        infos = zipped.infolist()
        names = [entry.filename for entry in infos]
        if len(names)>50_003 or len(set(names))!=len(names) or MANIFEST not in names:
            raise ValueError("unexpected/duplicate task archive members")
        if zipped.getinfo(MANIFEST).file_size > MAX_MANIFEST:
            raise ValueError("refinement task manifest exceeds 8 MiB")
        with zipped.open(MANIFEST) as stream:
            raw = stream.read(MAX_MANIFEST + 1)
        if len(raw)>MAX_MANIFEST: raise ValueError("oversize task manifest")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys)
        check_manifest(value)
        if value["schema"] == SCHEMA:
            if not set(names)<={MANIFEST,"README.txt"}: raise ValueError("unexpected legacy task archive member")
        else:
            from manual_snapshot import archive_snapshot
            archive_snapshot(zipped,value)
    return hashlib.sha256(raw).hexdigest(), value, raw


def read_tasks(archive):
    batch, value, _ = _read_task_archive(archive)
    return batch, value


def save_input_manifest(directory, batch, raw):
    manifest = directory / MANIFEST
    if manifest.is_symlink():
        raise ValueError("saved refinement manifest must not be a symlink")
    if manifest.exists():
        if not manifest.is_file() or digest(manifest) != batch:
            raise ValueError("saved refinement task manifest changed")
        return
    with tempfile.TemporaryDirectory(prefix=".manifest-", dir=directory) as work:
        temp = Path(work) / MANIFEST
        with temp.open("wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        rename_synced(temp, manifest)


def check_origin(layout, expected):
    base = json.loads(layout.path("metadata/grt_final_path.json").read_text(encoding="utf-8"))
    final = layout.path(base["q4_relpath"])
    if final.is_file() and digest(final) == expected:
        return "lgz"
    if layout.version == 2:
        for tool in TOOLS:
            publication = current_publication(layout.root, tool, verify=False)
            if not publication or publication["areas"]["final"]["new"]["files"].get("assembly.fa") != expected:
                continue
            path = layout.path(f"05_final/{TOOL_DIRECTORIES[tool]}/assembly.fa")
            if path.is_file() and not path.is_symlink() and digest(path) == expected:
                return tool
    if layout.project_delivery:
        from refinement_commit import committed_final_history
        for tool in TOOLS:
            for home, files in committed_final_history(layout,tool):
                fasta = home / "assembly.fa"
                if files.get("assembly.fa") == expected and fasta.is_file() and not fasta.is_symlink() and digest(fasta) == expected:
                    return tool
    raise ValueError("task batch does not match the Server workspace's LGZ or committed refined origin")


def write_fasta(path, name, blocks):
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write(f">{name}\n")
        carried = ""
        for block in blocks:
            for start in range(0, len(block), 65536):
                text = carried + block[start:start + 65536]
                cut = len(text) // 80 * 80
                if cut:
                    stream.write("\n".join(text[i:i + 80] for i in range(0, cut, 80)) + "\n")
                carried = text[cut:]
        if carried:
            stream.write(carried + "\n")


def gap_blocks(left, size, right):
    yield left
    for pos in range(0, size, 65536):
        yield "N" * min(size - pos, 65536)
    yield right


def verify_prepared(target, batch, locus):
    receipt = json.loads((target / "prepared.json").read_text(encoding="utf-8"))
    if (receipt.get("schema") != PREPARED or receipt.get("batch_sha256") != batch
            or receipt.get("locus_id") != locus["id"]):
        raise ValueError("existing local input does not belong to this locus")
    labels = set(locus["seed_plans"])
    if set(receipt["files"]) != {"local.fa"} | {label + ".fa" for label in labels}:
        raise ValueError("local input inventory is incomplete")
    for name, expected in receipt["files"].items():
        path = target / name
        if not sha(expected) or path.is_symlink() or digest(path) != expected:
            raise ValueError("prepared local input changed")
    if set(receipt["sources"]) != labels:
        raise ValueError("local input source inventory is incomplete")
    for label, plan in locus["seed_plans"].items():
        records = receipt["sources"][label]
        if len(records) != len(plan["members"]):
            raise ValueError("local input source inventory changed")
        for proof, member in zip(records, plan["members"]):
            if (any(proof[k] != member[k] for k in ("dataset", "name", "length", "start", "end"))
                    or (member["fasta_sha256"] and proof["fasta_sha256"] != member["fasta_sha256"])
                    or (member["interval_sha256"] and proof["interval_sha256"] != member["interval_sha256"])):
                raise ValueError("local input source proof differs from the exported plan")
    return receipt


def prepare_locus(root, stage, batch, locus, snapshot_sources=None):
    target = stage / locus["id"]
    if target.is_symlink():
        raise ValueError("manual input directory must not be a symlink")
    if target.exists():
        # Prepared bytes are sealed and safe to inspect; the native runner will
        # revalidate the source inputs before using this proof for a result.
        verify_prepared(target, batch, locus)
        return target
    with tempfile.TemporaryDirectory(prefix=".inputs-", dir=stage) as scratch:
        scratch = Path(scratch)
        output = scratch / "payload"
        output.mkdir()
        sequences, sources = {}, {}
        for label, plan in locus["seed_plans"].items():
            if snapshot_sources is None:
                sequences[label], sources[label] = resolve_seed(root, plan, scratch, require_content=True)
            else:
                w = locus["witnesses"][label]
                sequences[label] = b"".join(snapshot_sources.blocks({"witness":w,"plan":plan})).decode("ascii")
                sources[label] = []
                for m in plan["members"]:
                    file,_,_,_,sha,origin = snapshot_sources.member(m,"reference" in w)
                    sources[label].append({**m,"fasta_sha256":sha,"origin":origin,"source":str(file)})
                snapshot_sources.check()
            write_fasta(output / (label + ".fa"), label, (sequences[label],))
        if locus["kind"] == "gap":
            blocks = gap_blocks(sequences["seqleft"], locus["gap_bp"], sequences["seqright"])
        else:
            blocks = (sequences["endpoint"],)
        write_fasta(output / "local.fa", "locus", blocks)
        files = {name.name: digest(name) for name in output.iterdir()}
        durable_json(output / "prepared.json", {"schema": PREPARED, "batch_sha256": batch,
                                                   "locus_id": locus["id"], "files": files, "sources": sources})
        rename_synced(output, target)
    return target


def prepare_batch(root, archive, *, run=False, reads_override=None, threads=None):
    layout = WorkspaceLayout.detect(root.resolve())
    batch, value, raw = _read_task_archive(archive)
    lock = WorkspaceLock(layout.root, "manual-refinement-" + batch[:24])
    lock.acquire()
    try:
        if value["schema"] != SCHEMA:
            from job_final_catalog import _read_catalog
            if not layout.project_delivery: raise ValueError("this manual snapshot requires a Server job with project deliveries")
            _read_catalog(layout,recover=True)  # A complete manual delivery cannot be appended before the baseline exists.
        origin = check_origin(layout, value["origin_fasta_sha256"])
        directory = (layout.path(f"08_refinement_jobs/02_manual/{batch}/01_inputs") if layout.version == 2
                     else layout.path(f".run_all/manual_refinement/{batch}/01_inputs"))
        if directory.is_symlink():
            raise ValueError("manual batch input directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        save_input_manifest(directory, batch, raw)
        if run and layout.project_delivery:
            from refine_run import existing_manual_delivery
            delivered = existing_manual_delivery(layout,directory.parent,batch,value,reads_override or {})
            if delivered is not None:
                return delivered
        with ExitStack() as stack:
            sources = None
            if value["schema"] != SCHEMA:
                from manual_snapshot import install, Sources
                install(layout,directory,archive,batch,value)
                scratch=stack.enter_context(tempfile.TemporaryDirectory(dir=directory,prefix=".source-indexes-"))
                sources=Sources(layout,directory/"snapshot",scratch)
            outcomes = []
            for locus in value["loci"]:
                try:
                    target = prepare_locus(layout.root, directory, batch, locus, sources)
                    outcomes.append({"id": locus["id"], "status": "prepared", "receipt": str(target.relative_to(layout.root) / "prepared.json")})
                except (OSError, ValueError, KeyError) as exc:
                    outcomes.append({"id": locus["id"], "status": "input_unavailable", "reason": str(exc)})
        result = {"schema": PREPARED, "batch_sha256": batch, "origin": origin, "loci": outcomes}
        durable_json(directory.parent / "prepared.json", result)
        if run:
            from refine_run import execute_manual
            return execute_manual(layout, directory.parent, result, value, reads_override or {}, threads)
        return result
    finally:
        lock.release()


def main():
    parser = argparse.ArgumentParser(prog="refine.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("tasks", type=Path, help="exported refinement_tasks.zip")
    parser.add_argument("--prepare-only", action="store_true", help="validate and prepare inputs without running tools")
    parser.add_argument("--hifi", action="append", help="override one or more HiFi read paths")
    parser.add_argument("--ont", action="append", help="override one or more ONT read paths")
    args = parser.parse_args()
    if args.prepare_only and (args.hifi or args.ont):
        parser.error("read overrides cannot be used with --prepare-only")
    root = Path.cwd().resolve()
    try:
        # A globally copied entrypoint must use the selected workspace's
        # complete runtime, not borrow dependencies from its installation.
        marker = root / ".runtime/workspace.json"
        if marker.is_symlink() or marker.parent.is_symlink():
            raise ValueError("invalid Server workspace marker")
        if marker.exists():
            declaration = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(declaration, dict):
                raise ValueError("invalid Server workspace marker")
            area = ".lib" if declaration.get("prepared_runtime") == ".lib" else ".runtime/prepared"
        else:
            area = ".prepare_lib"
        tools = root / area / "tools"
        for name in ("workspace_layout.py", "refine.py", "refine_run.py", "refine_report.py", "render_manual_report.py", "render_refinement_report.py", "manual_snapshot.py", "manual_genome.py"):
            source = tools / name
            if (source.is_symlink() or not source.is_file()
                    or any(parent.is_symlink() for parent in source.parents if parent.is_relative_to(root))):
                raise ValueError(f"matching Server runtime missing {source}; update this workspace without re-preparing it")
        sys.path.insert(0, str(tools))
        from workspace_layout import WorkspaceLayout
        from refine import prepare_batch
        from run_all_runner import RunnerError
        if WorkspaceLayout.detect(root).path(".lib/tools") != tools:
            raise ValueError("Server runtime does not match the declared workspace layout")
        try:
            result = prepare_batch(root, args.tasks, run=not args.prepare_only,
                                   reads_override={"hifi": args.hifi, "ont": args.ont})
        except RunnerError as exc:
            raise ValueError(str(exc)) from exc
    except (BadZipFile, OSError, ValueError, KeyError, ImportError) as exc:
        print(f"manual refinement input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    if args.prepare_only:
        return int(any(row["status"] != "prepared" for row in result["loci"]))
    return int(any(row["status"] in {"failed", "input_unavailable", "missing_reads", "incomplete"}
                   for row in result["results"]))


if __name__ == "__main__":
    sys.exit(main())
