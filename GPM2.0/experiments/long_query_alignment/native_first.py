"""Native-first primitives for the isolated long-CIGAR hypothesis branch.

Normal native success is opaque/unchanged. After the exact target assertion only,
whole-record diagnostic groups may be divided; partial failed PAF is NEVER used.
No parameter sweep, tool update, source patch, runtime build or new customer flag.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import signal

import windowed_alignment as wa

MAX_MID_OCC_UPDATES = 10000
MAX_LOG_LINE = 64*1024
MAX_PREFIX = 2*wa.CHUNK+4096
PREDICATE = b"qoff == r->qe - r->qs && toff == r->re - r->rs"
ASSERTION = re.compile(rb"(?:^|[ /])align\.c:[0-9]+: mm_update_extra: Assertion [`'\"]"+
                       re.escape(PREDICATE)+rb"['\"] failed\.")
MID_OCC = re.compile(rb"\[M::mm_mapopt_update::[^\]]+\] mid_occ = ([0-9]+)\s*$")


class RawFastaCatalog:
    """Validated raw byte ranges/lengths only; no normalized sequence spool.

    Construct only after native failure. Native success does not acquire stricter
    FASTA/PAF acceptance rules. Group copies preserve complete original records,
    names, case, comments and arbitrary wrapping, in original relative order.
    """
    def __init__(self,source):
        self.source = Path(source).resolve()
        before = wa.fingerprint(self.source)
        digest = hashlib.sha256()
        records = {}
        current = None
        offset = 0
        line_start = True
        with self.source.open("rb") as inp:
            while raw := inp.readline(wa.CHUNK):
                digest.update(raw)
                if line_start and raw.startswith(b">"):
                    if len(raw)>=wa.CHUNK and not raw.endswith(b"\n"):
                        raise wa.ExperimentError("oversized raw FASTA header")
                    words = raw[1:].split()
                    if not words:
                        raise wa.ExperimentError("empty raw FASTA identifier")
                    name = words[0].decode("ascii")
                    if name in records or any(not 33<=ord(c)<=126 for c in name):
                        raise wa.ExperimentError("duplicate/unsupported raw FASTA identifier")
                    if current is not None:
                        current["byte_end"] = offset
                    current = {"length":0,"byte_start":offset,"byte_end":None,"order":len(records)}
                    records[name] = current
                else:
                    sequence = raw.rstrip(b"\r\n").upper()
                    if sequence:
                        if current is None or sequence.translate(None,wa.ALPHABET):
                            raise wa.ExperimentError("plain IUPAC DNA FASTA required for assertion recovery")
                        current["length"] += len(sequence)
                        if current["length"]>wa.INT32_MAX:
                            raise wa.ExperimentError("recovery query/reference record exceeds int32 coordinates")
                offset += len(raw)
                line_start = raw.endswith(b"\n")
        if current is not None:
            current["byte_end"] = offset
        if not records or any(not r["length"] for r in records.values()) or wa.fingerprint(self.source)!=before:
            raise wa.ExperimentError("raw FASTA empty, changed or contains an empty record")
        self.records = records
        self.identity = {"source":str(self.source),**before,"sha256":digest.hexdigest()}

    def unchanged(self):
        return wa.fingerprint(self.source)=={k:self.identity[k] for k in ("size","mtime_ns","ctime_ns","inode")}

    def copy_group(self,names,destination):
        if (not names or len(set(names))!=len(names) or any(name not in self.records for name in names)
                or [self.records[n]["order"] for n in names]!=sorted(self.records[n]["order"] for n in names)):
            raise wa.ExperimentError("diagnostic group omits/duplicates/permutes original record identities")
        if not self.unchanged():
            raise wa.ExperimentError("query changed before raw-record isolation")
        digest = hashlib.sha256()
        with self.source.open("rb") as inp,Path(destination).open("xb") as out:
            for name in names:
                record = self.records[name]
                inp.seek(record["byte_start"])
                remaining = record["byte_end"]-record["byte_start"]
                while remaining:
                    raw = inp.read(min(wa.CHUNK,remaining))
                    if not raw:
                        raise wa.ExperimentError("truncated raw query during isolation")
                    out.write(raw); digest.update(raw); remaining -= len(raw)
        if not self.unchanged():
            raise wa.ExperimentError("query changed during raw-record isolation")
        return {"path":str(Path(destination).resolve()),"sha256":digest.hexdigest(),"queries":list(names),
                "source_sha256":self.identity["sha256"],"raw_records_preserved":True}


def source_identity(path):
    path = Path(path)
    if not path.is_file():
        raise wa.ExperimentError("native input/tool must be a regular file")
    before = wa.fingerprint(path)
    digest = wa.sha256(path)
    if wa.fingerprint(path)!=before:
        raise wa.ExperimentError("source changed while capturing native input identity")
    return {"source":str(path.resolve()),**before,"sha256":digest}


def identity_unchanged(path,identity):
    return wa.fingerprint(Path(path))=={key:identity[key] for key in ("size","mtime_ns","ctime_ns","inode")}


def inspect_stderr(path):
    """Bounded memory, not a new success-path file/line size restriction.

    Unusually long log lines can still contain the assertion. Only recovery's
    threshold metadata becomes ineligible if a line/update bound was exceeded.
    A successful opaque native result must not fail merely for a long log.
    """
    matched = False
    mid_occ = []
    metadata_complete = True
    total = 0
    tail = b""
    continuing = False
    with Path(path).open("rb") as inp:
        while raw := inp.readline(MAX_LOG_LINE+1):
            total += len(raw)
            matched = matched or ASSERTION.search(tail+raw) is not None
            whole_line = not continuing and raw.endswith(b"\n")
            if not whole_line:
                metadata_complete = False
            value = MID_OCC.search(raw) if whole_line else None
            if value:
                text = value[1]
                if len(text)>10 or not 1<=int(text)<=wa.INT32_MAX or len(mid_occ)>=MAX_MID_OCC_UPDATES:
                    metadata_complete = False
                else:
                    mid_occ.append(int(text))
            tail = b"" if raw.endswith(b"\n") else (tail+raw)[-512:]
            continuing = not raw.endswith(b"\n")
    return {"target_assertion_observed":matched,"mid_occ_updates":mid_occ,
            "threshold_metadata_complete":metadata_complete,"stderr_bytes":total}


def classify(execution,log):
    rc = execution["returncode"]
    if "interrupted" in execution:
        return "other_failure"
    if rc==0:
        return "masked_assertion_failure" if log["target_assertion_observed"] else "native_success"
    if rc in (-signal.SIGABRT,128+signal.SIGABRT) and log["target_assertion_observed"]:
        return "target_assertion"
    return "other_failure"


def attempt(mm,target,query,root,args,*,mid_occ=None):
    root.mkdir(parents=True,exist_ok=False)
    output = root/"native.partial.paf"
    flags = ["-f",str(mid_occ)] if mid_occ is not None else []
    command = [mm,"-c","-x","asm10",*flags,"-t",str(args.threads),"-o",str(output),str(target),str(query)]
    execution = wa.run_command(command,root,"native",args.timeout,args.memory_gib,allow_failure=True)
    log = inspect_stderr(root/"native.stderr")
    status = classify(execution,log)
    if status=="native_success":
        if not output.is_file():
            raise wa.ExperimentError("native success without its requested PAF output")
        complete = root/"native.complete.paf"
        output.replace(complete)
        output = complete
    report = {"status":status,"execution":execution,**log,"path":str(output),
              "paf_sha256":wa.sha256(output) if output.is_file() else None,
              "paf_usable":status=="native_success","partial_PAF_reused":False,
              "stderr_sha256":wa.sha256(root/"native.stderr"),"automatic_parameter_retry":False}
    wa.write_json(root/"native-attempt.json",report)
    return report


def shared_mid_occ(failed_attempt,parts):
    values = failed_attempt["mid_occ_updates"]
    if (failed_attempt["status"]!="target_assertion" or not failed_attempt.get("threshold_metadata_complete",False)
            or not 1<=len(values)<=parts
            or len(set(values))!=1):
        raise wa.ExperimentError("failed native prefix cannot establish original shared mid_occ")
    return values[0]


def isolate_part(mm,part,query,root,args,*,on_native,on_assertion,check_unchanged=None):
    """Binary isolation of ACTUAL target assertions, never a length-based retry.

    Each group is attempted once. A target-asserting non-singleton is divided
    into two nonempty original-order whole-record groups; only an actually
    asserting singleton invokes recovery. Non-target failures stop immediately.
    The bound 2*N-1 is a structural limit, not an unbounded parameter retry loop.
    """
    root = Path(root)
    root.mkdir(exist_ok=False)
    names = list(query.records)
    report = {"status":"running","part_index":part["part_index"],"attempts":[],
              "attempt_bound":2*len(names)-1,"native_groups":0,"assertion_leaves":0,
              "length_is_not_a_recovery_trigger":True,"partial_PAF_reused":False}
    pending = [(names,None)]
    index = Path(part["path"])
    index_identity = wa.fingerprint(index)
    try:
        while pending:
            if check_unchanged is not None:
                check_unchanged()
            group,parent = pending.pop()
            number = len(report["attempts"])
            if number>=report["attempt_bound"]:
                raise wa.ExperimentError("whole-record assertion isolation exceeded its structural bound")
            directory = root/f"group-{number:06d}"
            directory.mkdir()
            if group==names:
                source = {"path":str(query.source),"sha256":query.identity["sha256"],"queries":group,
                          "raw_records_preserved":True,"uses_original_query_file":True}
            else:
                source = query.copy_group(group,directory/"query.fa")
            query_file = Path(source["path"])
            before = wa.fingerprint(query_file)
            if not query.unchanged() or wa.fingerprint(index)!=index_identity:
                raise wa.ExperimentError("original query/index changed before native assertion isolation")
            result = attempt(mm,index,query_file,directory/"native",args,mid_occ=part["mid_occ"])
            row = {"group":number,"parent_group":parent,"queries":group,"source":source,
                   "attempt_receipt":str(directory/"native"/"native-attempt.json"),"status":result["status"]}
            report["attempts"].append(row)
            wa.write_json(root/"isolation.json",report)
            if check_unchanged is not None:
                check_unchanged()
            if (not query.unchanged() or wa.fingerprint(index)!=index_identity
                    or wa.fingerprint(query_file)!=before):
                raise wa.ExperimentError("query/index changed during native assertion isolation")
            if result["status"]=="native_success":
                on_native(result,group,part)
                report["native_groups"] += 1
            elif result["status"]!="target_assertion":
                raise wa.ExperimentError("native isolation stopped on a non-target failure; partial PAF retained only as evidence")
            elif len(group)==1:
                row["recovery"] = on_assertion(group[0],query_file,part,directory)
                report["assertion_leaves"] += 1
            else:
                cut = len(group)//2
                pending.extend([(group[cut:],number),(group[:cut],number)])
            if check_unchanged is not None:
                check_unchanged()
            if (not query.unchanged() or wa.fingerprint(index)!=index_identity
                    or wa.fingerprint(query_file)!=before):
                raise wa.ExperimentError("query/index changed while accepting a completed isolation group")
            wa.write_json(root/"isolation.json",report)
        report["status"] = "all_groups_completed"
    except BaseException as exc:
        report.update(status="refused_or_failed",error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root/"isolation.json",report)
    return report


class CellMerger:
    """Merge only complete source groups, original part -> original query order.

    Native PAF bodies are streamed unchanged without parsing/requiring cg/AS.
    A failed group's partial PAF can never register any completed cell. Empty
    native output is valid only with an actual complete native-success receipt.
    """
    def __init__(self,root,queries,targets,parts):
        self.root = Path(root)
        self.root.mkdir(exist_ok=False)
        self.queries,self.targets = queries,targets
        self.query_ids = {name:i for i,name in enumerate(queries)}
        self.parts = [p["part_index"] for p in parts]
        self.membership = {}
        for part in parts:
            for row in part["records"]:
                if row["name"] in self.membership:
                    raise wa.ExperimentError("reference record belongs to multiple original parts")
                self.membership[row["name"]] = part["part_index"]
        if set(self.membership)!=set(targets) or len(set(self.parts))!=len(self.parts):
            raise wa.ExperimentError("reference part membership is incomplete/duplicated")
        self.cells = {}
        self.sources = []
        self.shard_digests = {}
        self.failed = False

    def _prefix(self,raw,allowed,part_index):
        fields = raw.split(b"\t",12)[:12]
        if len(fields)<12:
            raise wa.ExperimentError("native PAF has incomplete core columns")
        fields[-1] = fields[-1].rstrip(b"\r\n")
        try:
            name,target = fields[0].decode("ascii"),fields[5].decode("ascii")
            qlen,qs,qe = (int(v) for v in fields[1:4])
            tlen,ts,te,mlen,blen,mapq = (int(v) for v in fields[6:12])
        except (ValueError,UnicodeError) as exc:
            raise wa.ExperimentError("native PAF core columns are invalid") from exc
        if (name not in allowed or target not in self.membership or qlen!=self.queries[name]["length"]
                or tlen!=self.targets[target]["length"] or not 0<=qs<qe<=qlen or not 0<=ts<te<=tlen
                or fields[4] not in (b"+",b"-") or not 0<=mlen<=blen or not 0<=mapq<=255):
            raise wa.ExperimentError("native PAF core ownership/coordinates differ from source")
        index = self.membership[target]
        if part_index is not None and index!=part_index:
            raise wa.ExperimentError("native PAF target escaped its original index part")
        return index,name

    def add_native(self,receipt,names,*,part_index=None):
        if receipt.get("status")!="native_success" or not receipt.get("paf_usable"):
            raise wa.ExperimentError("failed or partial native PAF cannot enter result assembly")
        return self._add(Path(receipt["path"]),receipt["paf_sha256"],names,"native",part_index=part_index)

    def add_recovered(self,path,sha256,name,part_index,validator):
        return self._add(Path(path),sha256,[name],"recovered",part_index=part_index,validator=validator)

    def _add(self,path,expected_sha,names,route,*,part_index,validator=None):
        if self.failed:
            raise wa.ExperimentError("result assembly was invalidated by an earlier rejected source")
        try:
            return self._add_checked(path,expected_sha,names,route,part_index=part_index,validator=validator)
        except BaseException:
            self.failed = True
            raise

    def _add_checked(self,path,expected_sha,names,route,*,part_index,validator=None):
        if not names or len(set(names))!=len(names) or any(n not in self.queries for n in names):
            raise wa.ExperimentError("completed native/recovery group has foreign/duplicate queries")
        part_ids = self.parts if part_index is None else [part_index]
        keys = [(i,n) for i in part_ids for n in names]
        if any(i not in self.parts for i in part_ids) or any(k in self.cells for k in keys):
            raise wa.ExperimentError("native/recovery cells overlap or have a foreign original part")
        counts = {key:0 for key in keys}
        digest = hashlib.sha256()
        allowed = set(names)
        if validator is not None:
            with path.open("rb") as source:
                while raw := source.readline(32*1024**2+1):
                    if len(raw)>32*1024**2 or not raw.endswith(b"\n"):
                        raise wa.ExperimentError("recovered PAF line is incomplete/oversized")
                    validator(raw)
                    key = self._prefix(raw,allowed,part_index)
                    with self._shard(key).open("ab") as out:
                        out.write(raw)
                        self.shard_digests.setdefault(key,hashlib.sha256()).update(raw)
                    digest.update(raw); counts[key] += 1
        else:
            prefix = bytearray()
            out = None
            boundary = True
            try:
                with path.open("rb") as source:
                    while raw := source.readline(wa.CHUNK):
                        digest.update(raw)
                        boundary = raw.endswith(b"\n")
                        if out is None:
                            prefix.extend(raw)
                            if prefix.count(b"\t")>=12 or boundary:
                                key = self._prefix(bytes(prefix),allowed,part_index)
                                out = self._shard(key).open("ab")
                                out.write(prefix)
                                self.shard_digests.setdefault(key,hashlib.sha256()).update(prefix)
                                prefix.clear(); counts[key] += 1
                            elif len(prefix)>MAX_PREFIX:
                                raise wa.ExperimentError("native PAF core prefix exceeds source header bounds")
                        else:
                            out.write(raw)
                            self.shard_digests[key].update(raw)
                        if boundary:
                            if out is None:
                                raise wa.ExperimentError("native PAF core prefix is incomplete")
                            out.close(); out = None
                if not boundary or prefix or out is not None:
                    raise wa.ExperimentError("native PAF has an incomplete trailing record")
            finally:
                if out is not None:
                    out.close()
        if digest.hexdigest()!=expected_sha:
            raise wa.ExperimentError("completed PAF changed while combining cells")
        if route=="recovered" and not sum(counts.values()):
            raise wa.ExperimentError("an asserting recovery cannot register an empty no-hit cell")
        for key,n in counts.items():
            self.cells[key] = {"route":route,"rows":n,"source_sha256":expected_sha}
        self.sources.append({"path":str(path),"sha256":expected_sha,"route":route,"queries":list(names),"parts":part_ids})
        return sum(counts.values())

    def _shard(self,key):
        part,name = key
        return self.root/f"{part:04d}-{self.query_ids[name]:08d}.paf"

    def finish(self,path):
        expected = {(i,name) for i in self.parts for name in self.queries}
        if self.failed or set(self.cells)!=expected:
            raise wa.ExperimentError("native-first assembly omits original query/index-part cells")
        with Path(path).open("xb") as out:
            for part in self.parts:
                for name in self.queries:
                    key = (part,name)
                    shard = self._shard(key)
                    if key in self.shard_digests:
                        digest = hashlib.sha256()
                        with shard.open("rb") as source:
                            while raw := source.read(wa.CHUNK):
                                out.write(raw); digest.update(raw)
                        if digest.digest()!=self.shard_digests[key].digest():
                            raise wa.ExperimentError("native/recovered shard changed before final assembly")
                    elif shard.exists():
                        raise wa.ExperimentError("unregistered shard appeared for a completed empty cell")
        return {"original_cells":len(expected),"native_cells":sum(v["route"]=="native" for v in self.cells.values()),
                "recovered_cells":sum(v["route"]=="recovered" for v in self.cells.values()),
                "rows_by_query":{n:sum(self.cells[(i,n)]["rows"] for i in self.parts) for n in self.queries},
                "output_order":"original_part_then_original_query","native_row_bytes_preserved":True,
                "all_cells_completed":True,"partial_PAF_reused":False,"sources":self.sources}


def long_operation_witness(guidance_root,result,query_name,validator):
    """Require a source-supported PRE-filter path with an overflowing native op.

    -c's logical M includes both = and X. Looking only for a long '=' or only at
    retained output would miss a SNP-rich or post-DP-filtered offending path.
    This supports the hypothesis; it does not retrospectively prove every
    internal operation in the crashed original process.
    """
    recovery = result.get("native_recovery")
    if not recovery:
        raise wa.ExperimentError("recovery has no original-state/DP candidate evidence")
    source = Path(result["unfiltered_paf"])
    if wa.sha256(source)!=result["unfiltered_sha256"]:
        raise wa.ExperimentError("recovered witness PAF identity changed")
    candidates = {}
    ledgers = []
    for i,receipt in enumerate(recovery["queries"]):
        if receipt["query"]!=query_name:
            raise wa.ExperimentError("singleton recovery produced a foreign query")
        path = Path(guidance_root)/"native-recovery"/f"recovered-states-{i:06d}.jsonl"
        if wa.sha256(path)!=receipt["recovered_states_sha256"]:
            raise wa.ExperimentError("source-supported candidate ledger changed")
        ledgers.append((path,receipt["recovered_states_sha256"]))
        with path.open("rb") as inp:
            while raw := inp.readline(32*1024**2+1):
                if len(raw)>32*1024**2 or not raw.endswith(b"\n"):
                    raise wa.ExperimentError("candidate witness ledger is incomplete/oversized")
                row = json.loads(raw)
                if row["path_score"]["query"]!=query_name or row["anchor_count"]<1:
                    raise wa.ExperimentError("candidate witness lacks original query/anchor support")
                candidates.setdefault(row["fragment_id"],[]).append(row["chain_row"])
    witness = None
    with source.open("rb") as inp:
        number = 0
        while raw := inp.readline(32*1024**2+1):
            number += 1
            if len(raw)>32*1024**2 or not raw.endswith(b"\n"):
                raise wa.ExperimentError("witness candidate PAF incomplete/oversized")
            if number not in candidates:
                continue
            validator(raw)
            fields = raw.decode("ascii").rstrip("\n").split("\t")
            cigar = [t[5:] for t in fields[12:] if t.startswith("cg:Z:")][0]
            previous,length = None,0
            for match in re.finditer(r"([1-9][0-9]*)([M=XID])",cigar):
                size,op = int(match[1]),match[2]
                op = "M" if op in "M=X" else op
                if op==previous:
                    length += size
                else:
                    if length>wa.LIMIT and witness is None:
                        witness = {"fragment_id":number,"original_chain_rows":candidates[number],"operation":previous,
                                   "logical_length":length,"encoded_28bit_length":length&wa.LIMIT,
                                   "missing_28bit_blocks":length>>28}
                    previous,length = op,size
            if length>wa.LIMIT and witness is None:
                witness = {"fragment_id":number,"original_chain_rows":candidates[number],"operation":previous,
                           "logical_length":length,"encoded_28bit_length":length&wa.LIMIT,
                           "missing_28bit_blocks":length>>28}
    if any(wa.sha256(path)!=expected for path,expected in ledgers):
        raise wa.ExperimentError("source-supported witness ledger changed during acquisition")
    if wa.sha256(source)!=result["unfiltered_sha256"] or witness is None:
        raise wa.ExperimentError("target assertion recovery lacks a supported overlong logical CIGAR operation")
    return {"status":"recovered_path_supports_long_CIGAR_hypothesis","query":query_name,
            "first_overflow_witness":witness,"source_sha256":result["unfiltered_sha256"],
            "scope":"original-chain-supported_pre_filter_paths","customer_root_cause_confirmed":False,
            "production_ready":False,"execution_validated":False}
