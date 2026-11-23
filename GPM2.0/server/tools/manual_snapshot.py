"""Frozen project assembly accompanying a v2 manual task. No payload-supplied filesystem paths."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

from post_lgz_degap import IndexedFasta, CHUNK, stat_key
from run_orchestration import sha256_file as digest
from server_source_identity import candidates, read_rows
from workspace_migration import rename_synced, sync_directories

FILE = "assembly_snapshot.json"
TASKS = "cgat.app-refinement-tasks.v2"
RESULTS = "cgat.app-refinement-results.v2"
LIMIT = 128 * 1024 * 1024
MAX_OBJECT = 512 * 1024 * 1024
DNA = re.compile(b"[^ACGTRYSWKMBDHVN]")
RC = bytes.maketrans(b"ACGTRYSWKMBDHVN", b"TGCAYRSWMKVHDBN")


def load_snapshot(raw, manifest):
    from refine import checked_plan, positive, sha, text, unique_keys
    if len(raw)>LIMIT or hashlib.sha256(raw).hexdigest()!=manifest["snapshot_sha256"]:
        raise ValueError("exported assembly snapshot digest mismatch")
    value=json.loads(raw,object_pairs_hook=unique_keys)
    if (set(value)!={"schema","origin_fasta_sha256","chromosomes","objects"} or value["schema"]!="cgat.manual-assembly-snapshot.v1"
            or value["origin_fasta_sha256"]!=manifest["origin_fasta_sha256"] or not isinstance(value["chromosomes"],list)
            or not value["chromosomes"] or not isinstance(value["objects"],dict) or len(value["objects"])>50_000
            or any(not sha(k) or not positive(v) or v>MAX_OBJECT for k,v in value["objects"].items()) or sum(value["objects"].values())>8*1024**3):
        raise ValueError("invalid whole-assembly snapshot or object inventory")
    index, used, chrs = {}, set(), set()
    for c in value["chromosomes"]:
        chr=c["chr"]
        if (set(c)!={"chr","segments"} or not text(chr) or chr.startswith(">") or chr in chrs
                or not isinstance(c["segments"],list) or not c["segments"]):
            raise ValueError("invalid snapshot chromosome")
        chrs.add(chr)
        for i,part in enumerate(c["segments"]):
            w,plan=part["witness"],part["plan"]
            key=(chr,w["segment_id"])
            if set(part)!={"witness","plan"} or not text(key[1]) or key in index:
                raise ValueError("duplicate or invalid snapshot segment")
            index[key]=(c["segments"],i)
            if w["kind"]=="gap":
                if set(w)!={"segment_id","kind","gap_bp"} or not positive(w["gap_bp"]) or plan is not None:
                    raise ValueError("invalid frozen gap")
                continue
            if w["kind"]!="ctg" or not all(positive(w[k]) for k in ("start","end")):
                raise ValueError("invalid snapshot source witness")
            checked_plan(plan,w)
            check_witness(w,plan)
            for m in plan["members"]:
                if m["fasta_sha256"] is None and "reference" not in w:
                    key_hash=m["interval_sha256"]
                    if value["objects"].get(key_hash)!=m["end"]-m["start"]+1:
                        raise ValueError("snapshot lacks required App sequence interval")
                    used.add(key_hash)
    if used!=set(value["objects"]):
        raise ValueError("unreferenced snapshot sequence object")
    for locus in manifest["loci"]:
        pair=index.get((locus["chr"],locus["target"]))
        if not pair: raise ValueError("task is absent from the exported working assembly")
        rows,i=pair
        if locus["kind"]=="gap":
            if i==0 or i+1==len(rows): raise ValueError("frozen gap lacks both immediate flanks")
            pos={"seqleft":i-1,"target":i,"seqright":i+1}
        else:
            if i!=(0 if locus["kind"]=="tel_left" else len(rows)-1): raise ValueError("task is not a frozen assembly endpoint")
            pos={"endpoint":i}
        for label,n in pos.items():
            if rows[n]["witness"]!=locus["witnesses"][label] or rows[n]["plan"]!=locus["seed_plans"].get(label):
                raise ValueError("local task differs from its whole-assembly snapshot")
    return value


def check_witness(w,plan):
    from refine import positive, sha, text
    fields=set(w)-{"kind","segment_id","start","end"}
    if fields=={"assembly_ctg_id"} and positive(w["assembly_ctg_id"]): return
    if len(plan["members"])!=1: raise ValueError("invalid single-source snapshot witness")
    m=plan["members"][0]; lo,hi=sorted((w["start"],w["end"]))
    if fields=={"reference","member_start","member_end"}:
        if (not text(w["reference"]) or not positive(w["member_start"]) or not positive(w["member_end"])
                or w["member_end"]>m["length"] or hi>w["member_end"]-w["member_start"]+1): raise ValueError("invalid reference witness")
        lo+=w["member_start"]-1; hi+=w["member_start"]-1
        identity=("@reference",w["reference"])
    elif fields=={"patch_sha256"} and sha(w["patch_sha256"]): identity=("@app-patch",w["patch_sha256"])
    elif fields=={"dataset","contig"}: identity=(w["dataset"],w["contig"])
    else: raise ValueError("invalid frozen source witness")
    if (m["dataset"],m["name"],m["start"],m["end"])!=(*identity,lo,hi): raise ValueError("snapshot source identity or slice disagrees with witness")


def archive_snapshot(z,manifest):
    entry=z.getinfo(FILE)
    if entry.file_size>LIMIT: raise ValueError("snapshot index exceeds 128 MiB")
    raw=z.read(entry); value=load_snapshot(raw,manifest)
    names={"refinement_tasks.json",FILE}|{"snapshot_objects/"+s for s in value["objects"]}
    if "README.txt" in z.namelist(): names.add("README.txt")
    if len(z.infolist())!=len(names) or set(z.namelist())!=names: raise ValueError("unexpected or missing task archive members")
    for sha,size in value["objects"].items():
        f=z.getinfo("snapshot_objects/"+sha)
        if f.file_size!=size: raise ValueError("incorrect snapshot object length")
    return raw,value


def install(layout,directory,archive,batch,manifest):
    if not layout.project_delivery: raise ValueError("whole-assembly tasks require a project-delivery Server workspace")
    target=directory/"snapshot"
    if target.is_symlink(): raise ValueError("invalid snapshot directory")
    if target.exists():
        return read_saved(target,manifest)
    with ZipFile(archive) as z, tempfile.TemporaryDirectory(dir=directory,prefix=".snapshot-") as tmp:
        if z.getinfo("refinement_tasks.json").file_size>8*1024**2 or hashlib.sha256(z.read("refinement_tasks.json")).hexdigest()!=batch:
            raise ValueError("exported task changed during preparation")
        raw,value=archive_snapshot(z,manifest)
        stage=Path(tmp)/"snapshot"; stage.mkdir(); (stage/"objects").mkdir()
        with (stage/FILE).open("xb") as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        for sha,size in value["objects"].items():
            dst=stage/"objects"/sha; h=hashlib.sha256(); n=0
            with z.open("snapshot_objects/"+sha) as source,dst.open("xb") as out:
                while block:=source.read(CHUNK):
                    n+=len(block)
                    if n>size or DNA.search(block): raise ValueError("invalid embedded snapshot sequence")
                    h.update(block);out.write(block)
                out.flush();os.fsync(out.fileno())
            if n!=size or h.hexdigest()!=sha: raise ValueError("changed embedded snapshot sequence")
        sync_directories(stage/"objects",stage)
        rename_synced(stage,target)
    return value


def read_saved(home,manifest):
    if (home.is_symlink() or (home/FILE).is_symlink() or (home/FILE).stat().st_size>LIMIT or (home/"objects").is_symlink()):
        raise ValueError("invalid saved assembly snapshot")
    value=load_snapshot((home/FILE).read_bytes(),manifest)
    for sha,size in value["objects"].items():
        obj=home/"objects"/sha
        if obj.is_symlink() or not obj.is_file() or obj.stat().st_size!=size or digest(obj)!=sha: raise ValueError("saved sequence object changed")
    return value


class Sources:
    """Resolve and hash each source by content, stream slices in either orientation."""
    def __init__(self,layout,home,scratch):
        self.layout,self.home,self.scratch=layout,home,Path(scratch)
        self.rows={}; self.refs={}; self.indexes={}; self.resolved={}; self.identities={}
        for row in read_rows(layout.path("metadata/source_seq_locator.tsv")):
            self.rows[(row["dataset_name"],row["seq_name"])]=layout.path(row["fasta_relpath"])
        for row in read_rows(layout.path("metadata/reference_chr_locator.tsv")):
            self.refs[row["reference_chr_name"]]=layout.path(row["fasta_relpath"])

    def bind_file(self, path):
        before = stat_key(path)
        if self.identities.setdefault(path, before) != before:
            raise ValueError(f"snapshot source changed during reconstruction: {path}")

    def member(self,m,ref=False):
        key=(m["dataset"],m["name"],m["length"],m["start"],m["end"],m["fasta_sha256"],m["interval_sha256"],ref)
        if key in self.resolved: return self.resolved[key]
        name=m["name"]; size=m["end"]-m["start"]+1
        obj=self.home/"objects"/m["interval_sha256"] if m["fasta_sha256"] is None and not ref else None
        if obj is not None:
            self.bind_file(obj)
            if obj.is_symlink() or not obj.is_file() or obj.stat().st_size!=size or digest(obj)!=m["interval_sha256"]:
                raise ValueError("missing or corrupted embedded sequence interval")
            val=(obj,None,0,size,m["interval_sha256"],"app_interval")
        else:
            def paths():
                if ref:
                    if name in self.refs: yield self.refs[name],None,"reference"
                else:
                    original=self.rows.get((m["dataset"],name))
                    if original: yield original,None,"original"
                    yield from candidates(self.layout.root,m)
            seen=set()
            for source,admitted,origin in paths():
                source=source.resolve(strict=True)
                if source in seen: continue
                seen.add(source); self.bind_file(source); sha=digest(source)
                if any(s is not None and s!=sha for s in (admitted,m["fasta_sha256"])): continue
                if source not in self.indexes:
                    self.indexes[source]=IndexedFasta(source,self.scratch/(str(len(self.indexes))+".fa"))
                index=self.indexes[source]
                if name not in index.records or index.records[name][0]!=m["length"]: continue
                if m["interval_sha256"]:
                    h=hashlib.sha256()
                    for block in index.blocks(name,m["start"]-1,m["end"]): h.update(block.upper())
                    if h.hexdigest()!=m["interval_sha256"]: continue
                val=(source,index,m["start"]-1,m["end"],sha,origin); break
            else: raise ValueError(f"missing content-matching snapshot source {m['dataset']}:{name}")
        self.bind_file(val[0]); self.resolved[key]=val
        return val

    def blocks(self,part):
        w,plan=part["witness"],part["plan"]
        if w["kind"]=="gap":
            for offset in range(0,w["gap_bp"],CHUNK): yield b"N"*min(CHUNK,w["gap_bp"]-offset)
            return
        reverse=plan["start"]>plan["end"]
        for m in (reversed(plan["members"]) if reverse else plan["members"]):
            file,index,start,end,*_=self.member(m,"reference" in w)
            # Coordinates here are always forward zero-based; reverse the chunks AND their bases.
            with file.open("rb") as raw:
                for off in range(0,end-start,CHUNK):
                    lo,hi=(max(start,end-off-CHUNK),end-off) if reverse else (start+off,min(end,start+off+CHUNK))
                    if index: block=index.fetch(m["name"],lo,hi).upper()
                    else:
                        raw.seek(lo); block=raw.read(hi-lo)
                        if len(block)!=hi-lo or DNA.search(block): raise ValueError("snapshot object changed")
                    yield block.translate(RC)[::-1] if reverse else block

    def check(self):
        if any(stat_key(path)!=before for path,before in self.identities.items()): raise ValueError("snapshot source changed during reconstruction")
