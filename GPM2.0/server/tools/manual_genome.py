"""Apply exactly one eligible result per frozen locus and publish one immutable batch."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

from manual_snapshot import Sources, read_saved, RESULTS, DNA
from refinement_commit import read_json
from refinement_tools import fingerprint
from run_orchestration import sha256_file as digest
from workspace_migration import durable_json, ensure_directory, rename_synced, sync_directories

SCHEMA = "cgat.manual-genome-publication.v1"
PRIORITY = ("degap", "lrgapcloser", "tgsgapcloser", "quartet")


def names(layout,batch):
    from refine_report import manual_patch_path
    if not layout.project_delivery or not re.fullmatch("[0-9a-f]{64}",batch): raise ValueError("invalid manual genome namespace")
    tag="manual-"+batch[:16]
    return {"fasta":layout.path(f"05_final/{layout.result_prefix}.{tag}.fa"),"details":layout.path(f"05_final/details/{tag}/selection.json"),
            "patch":manual_patch_path(layout,batch)}


def winners(manifest,rows):
    lookup={(r["locus_id"],r["tool"]):r for r in rows}
    if len(lookup)!=len(rows): raise ValueError("duplicate manual task result")
    selected={}
    for locus in manifest["loci"]:
        lid=locus["id"]; selected[lid]=None
        eligible="closed" if locus["kind"]=="gap" else "extended"
        for tool in PRIORITY:
            if tool not in locus["tools"]: continue
            row=lookup.pop((lid,tool))
            if row["status"]==eligible:
                if not row.get("patch"): raise ValueError("successful task is missing its admitted patch")
                if selected[lid] is None: selected[lid]=row
    if lookup: raise ValueError("manual result does not belong to an exported task")
    return selected


class Record:
    def __init__(self,stream,chr):
        self.stream=stream; self.hash=hashlib.sha256();self.size=0;self.tail=b""
        stream.write(b">"+chr.encode("utf-8")+b"\n")

    def add(self,data):
        self.hash.update(data);self.size+=len(data)
        data=self.tail+data; end=len(data)//80*80
        if end: self.stream.write(b"\n".join(data[i:i+80] for i in range(0,end,80))+b"\n")
        self.tail=data[end:]

    def finish(self):
        if self.tail: self.stream.write(self.tail+b"\n")
        if not self.size: raise ValueError("empty manual genome chromosome")
        return {"length":self.size,"sha256":self.hash.hexdigest()}


def patch_bytes(row,patches):
    p=row["patch"]; data=patches[p["path"]].read_bytes()
    if len(data)!=p["length"] or hashlib.sha256(data).hexdigest()!=p["sha256"] or DNA.search(data) or b"N" in data:
        raise ValueError("chosen patch no longer contains the admitted closed sequence")
    return data


def assemble(layout,batch_dir,manifest,rows,patches,stage):
    snapshot=read_saved(batch_dir/"01_inputs/snapshot",manifest)
    chosen=winners(manifest,rows); by_target={}
    for locus in manifest["loci"]:
        row=chosen[locus["id"]]
        if row: by_target.setdefault((locus["chr"],locus["target"]),{})[locus["kind"]]=row
    stats={}
    with tempfile.TemporaryDirectory(dir=stage) as temp, (stage/"fasta").open("xb") as stream:
        src=Sources(layout,batch_dir/"01_inputs/snapshot",temp)
        for c in snapshot["chromosomes"]:
            chr=c["chr"]; out=Record(stream,chr)
            for part in c["segments"]:
                w=part["witness"]; changes=by_target.pop((chr,w["segment_id"]),{})
                if not changes:
                    for block in src.blocks(part): out.add(block)
                    continue
                # Check the same frozen original even when both ends of one contig extend.
                if "tel_left" in changes: out.add(patch_bytes(changes["tel_left"],patches))
                old=hashlib.sha256(); size=0
                for block in src.blocks(part):
                    old.update(block);size+=len(block)
                    if "gap" not in changes: out.add(block)
                for kind,row in changes.items():
                    p=row["patch"]
                    if (p["operation"]!={"gap":"replace_gap","tel_left":"prepend_tel","tel_right":"append_tel"}[kind]
                            or p["original_length"]!=size or p["original_sha256"]!=old.hexdigest()):
                        raise ValueError("admitted patch disagrees with the frozen original interval")
                for kind in ("gap","tel_right"):
                    if kind in changes: out.add(patch_bytes(changes[kind],patches))
            stats[chr]=out.finish()
        src.check();stream.flush();os.fsync(stream.fileno())
    if by_target: raise ValueError("manual edit targets are missing from exported assembly")
    return {k:r["tool"] if r else None for k,r in chosen.items()},stats


def _pending(layout,batch): return layout.path(f".runtime/refinement/manual-pending/{batch}")


def finish(layout,batch_dir,batch,manifest, *,override=None):
    from job_final_catalog import refresh_manual_catalog
    from refine_report import publish_manual_report
    files=names(layout,batch); pending=_pending(layout,batch); pointer=batch_dir/"manual-delivery.json"
    if pointer.is_symlink() or pending.is_symlink(): raise ValueError("manual publication path is a symlink")
    committed=pointer.exists()
    if not committed and not pending.exists():
        if any(p.exists() or p.is_symlink() for p in files.values()): raise ValueError("unowned manual output or abbreviated batch name collision")
        return None
    receipt=read_json(pointer if committed else pending/"prepared.json")
    if (receipt.get("schema")!=SCHEMA or receipt.get("batch")!=batch or receipt.get("snapshot_sha256")!=manifest["snapshot_sha256"]
            or set(receipt["files"])!=set(files) or any(not re.fullmatch("[0-9a-f]{64}",h) for h in receipt["files"].values())):
        raise ValueError("manual publication receipt belongs to a different export")
    if override and any(override.get(k) is not None for k in ("hifi","ont")):
        raise ValueError("batch already has a sealed outcome; export a new task to change reads")
    for key,target in files.items():
        ensure_directory(target.parent)
        if target.is_symlink(): raise ValueError("refusing linked manual delivery")
        if not committed:
            src=pending/key
            if src.is_symlink() or not src.is_file() or digest(src)!=receipt["files"][key]: raise ValueError("incomplete prepared manual genome transaction")
            if target.exists() and not target.samefile(src): raise ValueError("refusing to replace an unrelated manual result")
            if not target.exists(): os.link(src,target); sync_directories(target.parent)
        if not target.is_file() or digest(target)!=receipt["files"][key]: raise ValueError("published manual output is missing or changed")
    with ZipFile(files["patch"]) as archive: data=json.loads(archive.read("refinement_results.json"))
    if fingerprint(data)!=receipt["result"]: raise ValueError("manual report differs from the frozen result")
    if not committed: durable_json(pointer,receipt)
    # Readers only discover the batch once all three files and the patch manifest agree.
    refresh_manual_catalog(layout)
    report=publish_manual_report(layout,batch_dir,manifest,data,receipt["reads"],files["patch"])
    if pending.is_dir():
        for key in files:
            src=pending/key
            if src.is_file() and not src.is_symlink() and src.samefile(files[key]): src.unlink()
        saved=pending/"prepared.json"
        if saved.exists() and read_json(saved)==receipt: saved.unlink()
        if not any(pending.iterdir()): pending.rmdir(); sync_directories(pending.parent)
    return {"delivery":str(files["patch"]),"fasta":str(files["fasta"]),"selection":str(files["details"]),**report,"results":data["results"]}


def publish(layout,batch_dir,batch,manifest,rows,patches,reads):
    from refine_run import write_result_zip
    existing=finish(layout,batch_dir,batch,manifest)
    if existing: return existing
    pending=_pending(layout,batch);ensure_directory(pending.parent)
    with tempfile.TemporaryDirectory(dir=pending.parent,prefix=".assemble-") as temp:
        stage=Path(temp)/"stage";stage.mkdir()
        selected,stats=assemble(layout,batch_dir,manifest,rows,patches,stage)
        fasta_sha=digest(stage/"fasta")
        outcome={"snapshot_sha256":manifest["snapshot_sha256"],"genome_sha256":fasta_sha,"selected":selected}
        data={"schema":RESULTS,"batch_sha256":batch,"results":rows,"assembly":outcome}
        durable_json(stage/"details",{"schema":"cgat.manual-genome-selection.v1","batch_sha256":batch,"origin_fasta_sha256":manifest["origin_fasta_sha256"],**outcome,"chromosomes":stats})
        write_result_zip(stage/"patch",data,rows,patches)
        durable_json(stage/"prepared.json",{"schema":SCHEMA,"batch":batch,"snapshot_sha256":manifest["snapshot_sha256"],
            "files":{"fasta":fasta_sha,"patch":digest(stage/"patch"),"details":digest(stage/"details")},
            "accepted":sum(t is not None for t in selected.values()),"reads":reads,"result":fingerprint(data)})
        rename_synced(stage,pending)
    return finish(layout,batch_dir,batch,manifest)
