"""Separately reusable chaining, exact mapping and regional projection receipts.

Call under normal workspace ownership. Window FASTAs are generated inputs, not
published results: after a complete exact mapping they can be regenerated from
bound original sources. Failed mapping inputs/logs and all complete PAFs remain.
No diagnostic wall-clock cutoff is installed in production.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path

try:
    from workspace_layout import WorkspaceLayout, canonical_relative
except ModuleNotFoundError:
    from ..workspace_layout import WorkspaceLayout, canonical_relative
import re
import shutil
import subprocess
import sys
import threading
import uuid

from .common import canonical_json, sha256_bytes, sha256_file, stable_id, write_fasta
from .q0_alignments import read_paf
from .q0_cigar_policy import ChainWork, CigarWorkPolicy, select_cigar_profile
from .q0_query_windows import QueryWindow, TargetWindow, project_regional_paf
from .q0_sources import Q0EvidenceError

try:
    from run_orchestration import open_paf_text, sha256_file as _stable_runtime_sha256
except ModuleNotFoundError:
    from ..run_orchestration import open_paf_text, sha256_file as _stable_runtime_sha256

BASE_FLAGS = ["-D", "-P", "--dual=yes", "--no-long-join"]
CONTEXT_SCHEMA = "lgz_q0_regional_context_v1"
PROJECTION_SCHEMA = "lgz_q0_regional_projection_v1"
MAX_QUERY_BASES = 120_000
MAX_TARGET_BASES = 100_000_000
_LOCKS = {}; _LOCK_GUARD = threading.Lock()


class RegionalFallbackRequired(Q0EvidenceError):
    """No safe regional target scope: caller must use a declared full fallback."""


def _ops():
    from . import q0_preparation
    return q0_preparation


def _normal(value): return json.loads(canonical_json(value))


def _window_context(window):
    return {key: value for key,value in window.record().items() if key != "cores"}


def _source(catalog, segment_id):
    part=catalog.parts[segment_id];sequence=catalog.sequences[part.source]
    cache=getattr(catalog,"_regional_verified_parts",None)
    if cache is None:cache=catalog._regional_verified_parts={}
    previous=cache.get(segment_id)
    if previous is None or previous[0] is not sequence or previous[1:]!=(part.interval,part.sequence_sha256):
        if sha256_bytes(sequence[part.interval.start:part.interval.end].upper().encode("ascii"))!=part.sequence_sha256:
            raise Q0EvidenceError("regional source sequence differs from its catalog identity")
        cache[segment_id]=(sequence,part.interval,part.sequence_sha256)
    return sequence,part


def _sequence(catalog, window):
    sequence,part=_source(catalog,window.segment_id)
    return sequence[part.interval.start+window.start:part.interval.start+window.end].upper()


def _lock(path):
    with _LOCK_GUARD:
        return _LOCKS.setdefault(str(path),threading.Lock())


def _outputs(root, paths):
    return [_ops().identity(root,path) for path in sorted(set(paths))]


def _receipt_inventory(root, receipt, *, spec, required):
    record = _ops().json_file(_ops().artifact_path(root,receipt))
    if (record.get("status") != "success" or record.get("spec") != spec
            or not isinstance(record.get("outputs"),list)
            or len(record["outputs"]) != len(required)
            or {r.get("path") for r in record["outputs"]} != set(required)):
        raise Q0EvidenceError("regional receipt specification or inventory differs")
    return record


def _read_receipt(root, receipt, *, spec, required):
    record = _receipt_inventory(root,receipt,spec=spec,required=required)
    if record["outputs"] != _outputs(root,required):
        raise Q0EvidenceError("regional output content changed")
    return record


def _reuse(root, receipt, spec, required):
    if not (_ops().workspace_artifact_path(root, receipt)).is_file(): return None
    try: return _read_receipt(root,receipt,spec=spec,required=required)
    except (Q0EvidenceError,KeyError,TypeError): return None


def _verified_projection_hit(root, task, spec, required, *, members):
    """Accept a complete project with one full verification, not a preflight reread."""
    receipt = task["receipt"]
    if not (_ops().workspace_artifact_path(root, receipt)).is_file():
        return None
    try:
        checked = verify_regional_task(root, task, members=members)
        if checked["spec"] != spec:
            raise Q0EvidenceError("verified regional projection differs from requested scope")
        return checked
    except Q0EvidenceError:
        # Preserve the existing recovery boundary: missing/corrupt project
        # bytes may be regenerated from a valid raw receipt. If the bytes
        # match their inventory but fail command/geometry checks, fail closed.
        if _reuse(root, receipt, spec, required) is not None:
            raise
        return None


def _private_directory(root, relative):
    path = _ops().workspace_artifact_path(root, relative)
    if path.is_symlink():
        raise Q0EvidenceError("linked private regional cache is forbidden")
    return path


def _fresh_directory(root, relative):
    directory = _private_directory(root,relative)
    if directory.is_symlink(): raise Q0EvidenceError("linked regional task directory is forbidden")
    if directory.exists():
        directory.rename(directory.with_name(directory.name+".invalid-"+uuid.uuid4().hex))
    directory.mkdir(parents=True)
    return directory


def _context(root, catalog, query, targets, tool, preset):
    windows=[query,*targets];ids=sorted({w.segment_id for w in windows})
    if any(w.segment_id not in catalog.parts or w.segment_length != catalog.parts[w.segment_id].interval.length for w in windows):
        raise Q0EvidenceError("regional window source frame differs")
    if any(w.segment_id == query.segment_id for w in targets):
        raise Q0EvidenceError("regional input includes the query segment itself")
    if len({w.window_id for w in targets}) != len(targets): raise Q0EvidenceError("duplicate target window")
    for key in ids:_source(catalog,key)
    spec=_normal({"schema":CONTEXT_SCHEMA,"query":_window_context(query),
                  "targets":[_window_context(w) for w in sorted(targets,key=lambda w:w.window_id)],
                  "members":[[key,catalog.parts[key].sequence_sha256] for key in ids],
                  "tool":tool,"preset":preset,"fasta_format":"wrap80_v1"})
    key=stable_id("q0-regional-context",spec);relative=f"grt/evidence/q0_prepare/regional/{key}"
    directory=_private_directory(root,relative);path=directory/"context.json"
    if path.is_symlink():raise Q0EvidenceError("linked regional context is forbidden")
    if path.exists():
        stored=_ops().json_file(path)
        if (stored.get("spec") != spec or len(stored.get("inputs",[])) != 2
                or {r.get("path") for r in stored["inputs"]} != {relative+"/query.fa",relative+"/target.fa"}):
            raise Q0EvidenceError("regional context identity or input inventory changed")
        return relative,stored
    if directory.exists():directory=_fresh_directory(root,relative)
    else:directory.mkdir(parents=True)
    write_fasta(directory/"query.fa",[(query.window_id,_sequence(catalog,query))])
    write_fasta(directory/"target.fa",((w.window_id,_sequence(catalog,w)) for w in sorted(targets,key=lambda w:w.window_id)))
    record={"spec":spec,"inputs":_outputs(root,[relative+"/query.fa",relative+"/target.fa"]),
            "input_fastas_reconstructible_from_bound_windows":True}
    _ops().atomic_write_json(path,record)
    return relative,record


def _ensure_fastas(root,relative,context,catalog,query,targets):
    directory=_ops().workspace_artifact_path(root, relative)
    for name,windows in [("query",[query]),("target",sorted(targets,key=lambda w:w.window_id))]:
        path=directory/(name+".fa")
        expected=next(r for r in context["inputs"] if r["path"]==relative+"/"+name+".fa")
        if path.is_symlink():raise Q0EvidenceError("linked generated FASTA is forbidden")
        if path.is_file():
            if _ops().identity(root,expected["path"]) != expected:
                raise Q0EvidenceError("existing regional input changed; preserve it for diagnosis")
        else:
            write_fasta(path,((w.window_id,_sequence(catalog,w)) for w in windows))
            if _ops().identity(root,expected["path"]) != expected:
                raise Q0EvidenceError("regenerated window FASTA differs from bound input")


_CHILD_LOADER_POLICY = "clear_same_dependencies_v1"
_CHILD_LOADER = None
_CHILD_LOADER_SCOPE = threading.Lock()


@dataclass(frozen=True)
class _MapperLoader:
    tool_path: str
    tool_sha256: str
    path_sha256: str
    dependencies_sha256: str

    def child(self, tool):
        env = dict(os.environ)
        inherited = _library_path(env)
        if (tool["resolved"] != self.tool_path or tool["sha256"] != self.tool_sha256
                or inherited is None or sha256_bytes(os.fsencode(inherited)) != self.path_sha256):
            return None, None
        del env["LD_LIBRARY_PATH"]
        return env, {"policy": _CHILD_LOADER_POLICY, "inherited_path_sha256": self.path_sha256,
                     "dependencies_sha256": self.dependencies_sha256, "tool_sha256": self.tool_sha256}


def _library_path(env):
    path = env.get("LD_LIBRARY_PATH", "")
    if (not path or env.get("PYTHONHOME") or any(key.startswith(("LD_", "GLIBC_TUNABLES"))
            and key != "LD_LIBRARY_PATH" and value for key, value in env.items())
            or any(not item.startswith("/") or "$" in item for item in path.split(":"))):
        return None
    return path


def _dynamic_paths(binary, env):
    # Only called for the already selected trusted mapper and this interpreter's
    # own binaries, by the controlled reader before any mapper threads start.
    output = subprocess.run(["/usr/bin/ldd", str(binary)], env=env, check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45).stdout
    paths = {}
    for line in output.splitlines():
        row = re.sub(r"\s+\(0x[0-9a-f]+\)$", "", line.strip())
        if not row or row.startswith("linux-vdso.so."):
            continue
        name, sep, path = row.partition(" => ")
        dependency = Path(path if sep else name)
        if name in paths or not dependency.is_absolute() or not dependency.is_file():
            raise ValueError("nonlocal, missing, or unresolved runtime dependency")
        paths[name] = str(dependency.resolve(strict=True))
    if not paths:
        raise ValueError("no comparable ELF dependency inventory")
    return paths


def _probe_mapper_loader(mapper):
    inherited = dict(os.environ)
    search = _library_path(inherited)
    if sys.platform != "linux" or search is None:
        return None
    clean = dict(inherited)
    del clean["LD_LIBRARY_PATH"]
    try:
        import resource
        resolved = shutil.which(mapper)
        if resolved is None:
            return None
        tool = Path(resolved).resolve(strict=True)
        python = Path(sys.executable).resolve(strict=True)
        resource_module = Path(resource.__file__).resolve(strict=True)
        binaries = [python, resource_module, tool]
        before = {str(binary): _dynamic_paths(binary, inherited) for binary in binaries}
        paths = {Path(path) for row in before.values() for path in row.values()} | set(binaries)
        expected_bytes = {str(path): sha256_file(path) for path in sorted(paths)}
        if before != {str(binary): _dynamic_paths(binary, clean) for binary in binaries}:
            return None
        if any(sha256_file(Path(path)) != fingerprint for path, fingerprint in expected_bytes.items()):
            return None
        return _MapperLoader(str(tool), expected_bytes[str(tool)], sha256_bytes(os.fsencode(search)),
                             sha256_bytes(canonical_json([before, expected_bytes]).encode("utf-8")))
    except (OSError, ImportError, AttributeError, ValueError, subprocess.SubprocessError):
        return None  # Different or unverified dependencies: retain original environment.


@contextmanager
def verified_mapper_loader(mapper):
    """Opt in from a bound incident reader; affect only its regional children."""
    global _CHILD_LOADER
    if not _CHILD_LOADER_SCOPE.acquire(blocking=False):
        raise Q0EvidenceError("cannot replace a regional mapper loader scope in use")
    try:
        _CHILD_LOADER = _probe_mapper_loader(mapper)
        yield _CHILD_LOADER is not None
    finally:
        _CHILD_LOADER = None
        _CHILD_LOADER_SCOPE.release()


def _verify_mapper_loader_record(record, tool):
    if (type(record) is not dict or set(record) != {"policy", "tool_sha256", "inherited_path_sha256", "dependencies_sha256"}
            or record["policy"] != _CHILD_LOADER_POLICY or record["tool_sha256"] != tool["sha256"]
            or any(not isinstance(record[k], str) or not re.fullmatch(r"[0-9a-f]{64}", record[k])
                   for k in ("inherited_path_sha256", "dependencies_sha256"))):
        raise Q0EvidenceError("invalid regional mapper loader record")


def _execute(root,directory,context,relative,catalog,query,targets,argv,tool,address_space_bytes):
    _ensure_fastas(root,relative,context,catalog,query,targets)
    # Share the cold binary digest across mapper workers and coarse/exact
    # launches. The process-local memo rechecks resolved path, inode, size,
    # mtime and ctime on every call; any change forces a stable full read.
    if _stable_runtime_sha256(Path(tool["resolved"])) != tool["sha256"]: raise Q0EvidenceError("regional mapper changed")
    guard=Path(__file__).with_name("q0_mapper_guard.py")
    shutil.copyfile(guard,directory/"guard.py")
    command=[sys.executable,str(directory/"guard.py"),"--address-space-bytes",str(address_space_bytes),"--",*argv]
    options = {}
    receipt = {"producer_root":str(root),"producer_layout_version":WorkspaceLayout.detect(root).version,
               "argv":argv,"executed_argv":command,
               "address_space_bytes":address_space_bytes,"guard_sha256":sha256_file(directory/"guard.py"),"wall_clock_limit_added":False}
    loader = _CHILD_LOADER
    if loader is not None:
        child_env, provenance = loader.child(tool)
        if provenance is not None:
            options["env"] = child_env
            receipt["mapper_loader"] = provenance
    _ops().atomic_write_json(directory/"command.json",receipt)
    # Inherit the owning reader's process group, so ordinary Runner/scheduler
    # cancellation reaches every mapper. The guard execs, it has no child tree.
    with (directory/"result.paf.tmp").open("wb") as output,(directory/"stderr.log").open("wb") as log:
        process=subprocess.Popen(command,cwd=directory,stdout=output,stderr=log,**options)
        try: code=process.wait()
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            raise
    if code:raise Q0EvidenceError(f"regional mapper failed ({code}); retain {directory}/stderr.log")
    if context["inputs"] != _outputs(root,[r["path"] for r in context["inputs"]]):
        raise Q0EvidenceError("regional mapping inputs changed during execution")
    if _stable_runtime_sha256(Path(tool["resolved"])) != tool["sha256"]: raise Q0EvidenceError("regional mapper changed during execution")


def chain_work(path,query,target_lengths,policy):
    work=ChainWork()
    with open_paf_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):continue
            f=line.rstrip("\r\n").split("\t")
            try:
                qlen,qs,qe=int(f[1]),int(f[2]),int(f[3]);tlen,ts,te=int(f[6]),int(f[7]),int(f[8])
                matches,span,mapq=map(int,f[9:12]);scores=[t[5:] for t in f[12:] if t.startswith("s1:i:")]
                if (f[0]!=query.window_id or qlen!=query.length or target_lengths.get(f[5])!=tlen
                        or not 0<=qs<qe<=qlen or not 0<=ts<te<=tlen or f[4] not in ("+","-")
                        or not 0<=matches<=min(span,qe-qs,te-ts) or span<1 or not 0<=mapq<=255
                        or len(scores)!=1 or any(t.startswith("cg:") for t in f[12:])):
                    raise ValueError("invalid approximate record")
                work.observe(qe-qs,te-ts,int(scores[0]),policy=policy)
            except (IndexError,ValueError) as exc:raise Q0EvidenceError("invalid pre-CIGAR record") from exc
    return work


def _projected_lines(source, query, targets, *, artifact):
    # One validated window inventory per stream, not one O(targets) dict per
    # PAF row. Producer and verifier render exactly the same original lines.
    query_windows = {query.window_id: query}
    target_windows = {window.window_id: window for window in targets}
    for number, line in enumerate(source, 1):
        if not line.strip() or line.startswith("#"):
            continue
        projected = project_regional_paf(line, query_windows, target_windows, artifact=artifact, line_number=number)
        if projected is not None:
            yield projected + "\n"


def prepare_regional_mapping(root, catalog, query: QueryWindow, targets: list[TargetWindow], tool: dict,
                             *, reference_bases: int, preset="asm10", threads=2,
                             address_space_bytes=4*1024**3, policy=CigarWorkPolicy()):
    root=Path(root).resolve(strict=True)
    if threads<1 or query.length>MAX_QUERY_BASES: raise Q0EvidenceError("uncalibrated regional query/resource budget")
    if not targets or sum(w.length for w in targets)>MAX_TARGET_BASES:
        raise RegionalFallbackRequired("regional target inventory needs declared full fallback")
    # The raw context key excludes cores; complete raw mapping can survive a
    # projection/coverage-selection repair without a new alignment.
    context_hint=stable_id("regional-lock",[_window_context(query),[_window_context(w) for w in sorted(targets,key=lambda w:w.window_id)],tool,preset])
    with _lock(_ops().workspace_artifact_path(root, context_hint)):
        relative,context=_context(root,catalog,query,targets,tool,preset)
        context_path=relative+"/context.json";context_identity=_ops().identity(root,context_path)
        toolargv=[tool["resolved"],"-x",preset,*BASE_FLAGS,"-t",str(threads),str(_ops().workspace_artifact_path(root, relative)/"target.fa"),str(_ops().workspace_artifact_path(root, relative)/"query.fa")]
        target_lengths={w.window_id:w.length for w in targets}
        closure={context_path}
        if preset=="asm10" and reference_bases>=policy.minimum_reference_bases and query.length>=policy.minimum_query_bases:
            pre_spec={"schema":"lgz_q0_regional_chaining_v1","context":context_identity,"flags":BASE_FLAGS}
            pre_rel=relative+"/chaining";pre_receipt=pre_rel+"/success.json"
            required={pre_rel+"/"+name for name in ("result.paf","command.json","guard.py")}
            if _reuse(root,pre_receipt,pre_spec,required) is None:
                directory=_fresh_directory(root,pre_rel)
                _execute(root,directory,context,relative,catalog,query,targets,toolargv,tool,address_space_bytes)
                work=chain_work(directory/"result.paf.tmp",query,target_lengths,policy)
                (directory/"result.paf.tmp").replace(directory/"result.paf")
                _ops().atomic_write_json(_ops().workspace_artifact_path(root, pre_receipt),{"status":"success","spec":pre_spec,"outputs":_outputs(root,required)})
            else:
                work=chain_work(_ops().workspace_artifact_path(root, pre_rel)/"result.paf",query,target_lengths,policy)
            decision=select_cigar_profile(reference_bases,query.length,work,complete=True,preset=preset,policy=policy)
            decision["chaining_receipt"]=_ops().identity(root,pre_receipt)
            closure.update(required|{pre_receipt})
        else:
            decision={"schema":"lgz_q0_cigar_profile_v1","policy":asdict(policy),"reason":"screening_not_needed",
                      "reference_bases":reference_bases,"query_bases":query.length,"additional_flags":[],"approximate_chaining_is_evidence":False}
        decision=_normal(decision);decision_id=stable_id("q0-regional-decision",decision)
        decision_path=relative+"/"+decision_id+".json"
        if not (_ops().workspace_artifact_path(root, decision_path)).exists():_ops().atomic_write_json(_ops().workspace_artifact_path(root, decision_path),decision)
        elif _ops().json_file(_ops().workspace_artifact_path(root, decision_path))!=decision:raise Q0EvidenceError("regional decision changed")
        closure.add(decision_path)
        raw_spec={"schema":"lgz_q0_regional_raw_v1","context":context_identity,"flags":["-c",*BASE_FLAGS,*decision["additional_flags"]]}
        raw_id=stable_id("q0-regional-raw",raw_spec);raw_rel=relative+"/"+raw_id;raw_receipt=raw_rel+"/success.json"
        required={raw_rel+"/"+name for name in ("result.paf","command.json","guard.py")}
        if _reuse(root,raw_receipt,raw_spec,required) is None:
            directory=_fresh_directory(root,raw_rel)
            argv=[tool["resolved"],"-c","-x",preset,*BASE_FLAGS,*decision["additional_flags"],"-t",str(threads),str(_ops().workspace_artifact_path(root, relative)/"target.fa"),str(_ops().workspace_artifact_path(root, relative)/"query.fa")]
            _execute(root,directory,context,relative,catalog,query,targets,argv,tool,address_space_bytes)
            for _ in read_paf(directory/"result.paf.tmp",query_lengths={query.window_id:query.length},target_lengths=target_lengths):pass
            (directory/"result.paf.tmp").replace(directory/"result.paf")
            _ops().atomic_write_json(_ops().workspace_artifact_path(root, raw_receipt),{"status":"success","spec":raw_spec,"outputs":_outputs(root,required)})
        # A fresh raw result was validated before publication above. Both a
        # fresh projection and the final verify_regional_task replay validate
        # every raw record's CIGAR and window identity, including on a cache
        # hit. Do not insert another full, identical geometry scan here.
        closure.update(required|{raw_receipt})
        projection_spec=_normal({"schema":PROJECTION_SCHEMA,"raw_receipt":_ops().identity(root,raw_receipt),
            "context":context_identity,"decision":_ops().identity(root,decision_path),"query":query.record(),
            "targets":[w.record() for w in sorted(targets,key=lambda w:w.window_id)],
            "projector_sha256":_stable_runtime_sha256(Path(__file__).with_name("q0_query_windows.py")),
            "validator_sha256":_stable_runtime_sha256(Path(__file__).with_name("q0_alignments.py"))})
        task_id=stable_id("q0-regional-project",projection_spec);project_rel=f"grt/evidence/q0_prepare/regional/projects/{task_id}"
        receipt=project_rel+"/success.json";paf=project_rel+"/result.paf";required=closure|{paf}
        task={"task_id":task_id,"kind":"regional_discovery","paf":paf,"receipt":receipt,
              "query_ids":[query.segment_id],"target_ids":sorted({w.segment_id for w in targets})}
        if _verified_projection_hit(root,task,projection_spec,required,members=catalog.parts) is None:
            directory=_fresh_directory(root,project_rel)
            try:
                with open_paf_text(_ops().workspace_artifact_path(root, raw_rel)/"result.paf") as source,(directory/"result.paf.tmp").open("w",encoding="utf-8") as output:
                    output.writelines(_projected_lines(source,query,targets,artifact=raw_rel+"/result.paf"))
            except (OSError,UnicodeError) as exc:
                raise Q0EvidenceError(f"cannot project q0 regional evidence {raw_rel}/result.paf: {exc}") from exc
            (directory/"result.paf.tmp").replace(_ops().workspace_artifact_path(root, paf))
            _ops().atomic_write_json(_ops().workspace_artifact_path(root, receipt),{"status":"success","spec":projection_spec,"outputs":_outputs(root,required)})
            verify_regional_task(root,task,members=catalog.parts)
        # Only owned generated inputs are removed, after success. Original
        # genomes, native task FASTAs, failed inputs and complete PAFs are kept.
        for name in ("query.fa","target.fa"):(_ops().workspace_artifact_path(root, relative)/name).unlink(missing_ok=True)
        return task


def _verify_command(root, relative, context_relative, context_spec, flags):
    command=_ops().json_file(_ops().artifact_path(root,relative+"/command.json"))
    argv=command["argv"];producer=Path(command["producer_root"])
    version = command.get("producer_layout_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise Q0EvidenceError("invalid regional producer workspace layout")
    # Command paths belong to the original producer, even when its output was
    # moved or migrated. Replay its namespace without accessing that directory.
    physical_context = canonical_relative(context_relative) if version == 2 else context_relative
    physical_task = canonical_relative(relative) if version == 2 else relative
    if "mapper_loader" in command:
        _verify_mapper_loader_record(command["mapper_loader"], context_spec["tool"])
    if (not producer.is_absolute() or argv[-4]!="-t" or int(argv[-3])<1
            or type(command["address_space_bytes"]) is not int or command["address_space_bytes"]<16*1024*1024):
        raise Q0EvidenceError("invalid regional execution record")
    exact=flags[:1]==["-c"];alignment_flags=flags[1:] if exact else flags
    expected=[context_spec["tool"]["resolved"],*(["-c"] if exact else []),"-x",context_spec["preset"],
              *alignment_flags,"-t",argv[-3],str(producer/physical_context/"target.fa"),str(producer/physical_context/"query.fa")]
    if (argv!=expected or command["executed_argv"][1:]!=[str(producer/physical_task/"guard.py"),
            "--address-space-bytes",str(command["address_space_bytes"]),"--",*argv]
            or command["wall_clock_limit_added"] is not False
            or sha256_file(_ops().workspace_artifact_path(root, relative)/"guard.py")!=command["guard_sha256"]):
        raise Q0EvidenceError("regional executed flags/guard differ from receipt")


def verify_regional_task(root, task, *, members=None):
    """Verify complete raw/projection dependencies, never approximate evidence.

    `members`, when provided by the ready-manifest validator, maps original
    segment IDs to (length, normalized sequence SHA) or SourceSegment objects.
    """
    root=Path(root).resolve(strict=True)
    try:
        receipt=_ops().json_file(_ops().artifact_path(root,task["receipt"]))
        spec=receipt["spec"]
        if spec.get("schema")!=PROJECTION_SCHEMA:raise Q0EvidenceError("unsupported regional projection")
        task_id=stable_id("q0-regional-project",spec);relative=f"grt/evidence/q0_prepare/regional/projects/{task_id}"
        if (task["task_id"]!=task_id or task["receipt"]!=relative+"/success.json" or task["paf"]!=relative+"/result.paf"):
            raise Q0EvidenceError("regional task path differs from its identity")
        if (spec["projector_sha256"]!=_stable_runtime_sha256(Path(__file__).with_name("q0_query_windows.py"))
                or spec["validator_sha256"]!=_stable_runtime_sha256(Path(__file__).with_name("q0_alignments.py"))):
            raise Q0EvidenceError("regional projection implementation changed")
        row=spec["query"];query=QueryWindow(row["segment_id"],row["segment_length"],row["start"],row["end"],tuple(tuple(i) for i in row["cores"]))
        targets=[TargetWindow(r["segment_id"],r["segment_length"],r["start"],r["end"]) for r in spec["targets"]]
        if _normal(query.record())!=row or [_normal(w.record()) for w in targets]!=spec["targets"]:
            raise Q0EvidenceError("regional window identity differs")
        if task["query_ids"]!=[query.segment_id] or task["target_ids"]!=sorted({w.segment_id for w in targets}):
            raise Q0EvidenceError("regional original-source inventory changed")
        context_identity=spec["context"];context=_ops().json_file(_ops().artifact_path(root,context_identity["path"]))
        context_spec=context["spec"];context_key=stable_id("q0-regional-context",context_spec)
        context_rel=f"grt/evidence/q0_prepare/regional/{context_key}"
        if (context_identity["path"]!=context_rel+"/context.json"
                or _ops().identity(root,context_identity["path"])!=context_identity
                or context_spec.get("schema")!=CONTEXT_SCHEMA
                or context_spec["query"]!=_window_context(query)
                or context_spec["targets"]!=[_window_context(w) for w in targets]
                or len(context["inputs"])!=2
                or {r["path"] for r in context["inputs"]}!={context_rel+"/query.fa",context_rel+"/target.fa"}):
            raise Q0EvidenceError("regional context is not fully bound")
        if members is not None:
            expected={}
            for window in [query,*targets]:
                key=window.segment_id;part=members[key]
                length,sha=(part.interval.length,part.sequence_sha256) if hasattr(part,"interval") else part
                if window.segment_length!=length:
                    raise Q0EvidenceError("regional source length differs from catalog")
                expected[key]=sha
            if context_spec["members"]!=[[key,expected[key]] for key in sorted(expected)]:
                raise Q0EvidenceError("regional source content differs from catalog")
        decision_identity=spec["decision"];decision=_ops().json_file(_ops().artifact_path(root,decision_identity["path"]))
        if (decision_identity["path"]!=context_rel+"/"+stable_id("q0-regional-decision",decision)+".json"
                or _ops().identity(root,decision_identity["path"])!=decision_identity):
            raise Q0EvidenceError("regional selection decision changed")
        closure={context_identity["path"],decision_identity["path"]};policy=CigarWorkPolicy(**decision["policy"])
        leaves=[]
        if "chaining_receipt" in decision:
            identity=decision["chaining_receipt"];pre_rel=context_rel+"/chaining";pre_path=pre_rel+"/success.json"
            if identity["path"]!=pre_path or _ops().identity(root,pre_path)!=identity:raise Q0EvidenceError("chaining receipt changed")
            required={pre_rel+"/"+name for name in ("result.paf","command.json","guard.py")}
            pre_spec={"schema":"lgz_q0_regional_chaining_v1","context":context_identity,"flags":BASE_FLAGS}
            leaves.append((pre_path,identity,_receipt_inventory(root,pre_path,spec=pre_spec,required=required),required))
            _verify_command(root,pre_rel,context_rel,context_spec,BASE_FLAGS)
            work=chain_work(_ops().workspace_artifact_path(root, pre_rel)/"result.paf",query,{w.window_id:w.length for w in targets},policy)
            expected=select_cigar_profile(decision["reference_bases"],query.length,work,complete=True,preset=context_spec["preset"],policy=policy)
            expected["chaining_receipt"]=identity
            if _normal(expected)!=decision:raise Q0EvidenceError("CIGAR profile does not match complete chaining evidence")
            closure.update(required|{pre_path})
        else:
            if (decision.get("reason")!="screening_not_needed" or decision.get("additional_flags")!=[]
                    or decision["query_bases"]!=query.length
                    or (context_spec["preset"]=="asm10" and decision["reference_bases"]>=policy.minimum_reference_bases and query.length>=policy.minimum_query_bases)):
                raise Q0EvidenceError("required chaining work was not measured")
        raw_spec={"schema":"lgz_q0_regional_raw_v1","context":context_identity,"flags":["-c",*BASE_FLAGS,*decision["additional_flags"]]}
        raw_rel=context_rel+"/"+stable_id("q0-regional-raw",raw_spec);raw_path=raw_rel+"/success.json"
        if spec["raw_receipt"]["path"]!=raw_path or _ops().identity(root,raw_path)!=spec["raw_receipt"]:
            raise Q0EvidenceError("exact regional raw receipt changed")
        required={raw_rel+"/"+name for name in ("result.paf","command.json","guard.py")}
        leaves.append((raw_path,spec["raw_receipt"],_receipt_inventory(root,raw_path,spec=raw_spec,required=required),required))
        _verify_command(root,raw_rel,context_rel,context_spec,raw_spec["flags"])
        closure.update(required|{raw_path,task["paf"]})
        # Read/hash the entire committed closure once, then require every leaf
        # to declare exactly those verified bytes. Checking leaf inventories
        # does not by itself admit any raw or chaining result.
        verified=_read_receipt(root,task["receipt"],spec=spec,required=closure)
        if verified!=receipt:raise Q0EvidenceError("regional projection receipt changed during verification")
        outputs={r["path"]:r for r in verified["outputs"]}
        for leaf,leaf_identity,record,leaf_paths in leaves:
            if outputs[leaf]!=leaf_identity or record["outputs"]!=[outputs[p] for p in sorted(leaf_paths)]:
                raise Q0EvidenceError("regional leaf outputs differ from verified projection closure")
        # Replay a small, already-finished raw CIGAR stream, not the mapper or
        # reference scan. This catches wrong offsets even if PAF syntax is valid.
        with open_paf_text(_ops().workspace_artifact_path(root, raw_rel)/"result.paf") as source,open_paf_text(_ops().workspace_artifact_path(root, task["paf"])) as output:
            for projected in _projected_lines(source,query,targets,artifact=raw_rel+"/result.paf"):
                if output.readline()!=projected:raise Q0EvidenceError("projected CIGAR differs from bound raw evidence")
            if output.read(1):raise Q0EvidenceError("regional projection contains extra records")
        return receipt
    except (KeyError,IndexError,TypeError,ValueError,OSError) as exc:
        if isinstance(exc,Q0EvidenceError):raise
        raise Q0EvidenceError("invalid regional evidence receipt") from exc
