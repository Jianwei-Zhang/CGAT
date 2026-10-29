"""Native raw-overlap witnesses for window joins, not global DP certification.

No second normalization, coordinate adjustment, score heuristic or row dropping.
Store raw origins as offsets/provenance rather than another full raw PAF. Load a
pair for comparison plus its bounded overlap clips. Explicit work/row/line bounds
refuse instead of skipping data.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
import hashlib
import json
from pathlib import Path
import re

import windowed_alignment as wa

MAX_LINE = 32*1024**2
MAX_PROOF_LINE = 4*1024**2
MAX_ROWS = 1_000_000
MAX_COMPARISONS = 100_000
MAX_READ_BYTES = 16*1024**3
HASH = re.compile(r"[0-9a-f]{64}\Z")


def _integer(value,minimum=0):
    return type(value) is int and minimum<=value<=wa.INT32_MAX


def signature(hit):
    return (hit.query,hit.qlen,hit.strand,hit.target,hit.tlen,hit.qs,hit.qe,hit.ts,hit.te,
            wa.join_operations(hit.ops))


def path_digest(value):
    digest = hashlib.sha256(json.dumps(value[:-1],separators=(",",":")).encode("ascii"))
    for size,op in value[-1]:
        digest.update(f";{size}{op}".encode("ascii"))
    return digest.hexdigest()


@dataclass(frozen=True)
class Origin:
    row: int
    start: int
    end: int
    digest: str
    alias: str
    owner: int
    lifted: tuple
    mapq: int


class SeamSources:
    def __init__(self,raw,proof,records,windows,targets,*,raw_sha256,proof_sha256):
        self.raw,self.proof = Path(raw).resolve(),Path(proof).resolve()
        if not self.raw.is_file() or not self.proof.is_file():
            raise wa.ExperimentError("raw overlap evidence must be regular files")
        if not all(type(h) is str and HASH.fullmatch(h) for h in (raw_sha256,proof_sha256)):
            raise wa.ExperimentError("raw overlap evidence requires immutable producer hashes")
        self.raw_sha256,self.proof_sha256 = raw_sha256,proof_sha256
        self.implementation_sha256 = wa.sha256(Path(__file__))
        if len(records)>MAX_ROWS:
            raise wa.ExperimentError("owned overlap candidates exceed the supported row bound")
        self.identities = [wa.fingerprint(p) for p in (self.raw,self.proof)]
        self.records,self.windows,self.targets = records,windows,targets
        self.origins = {i+1:[] for i in range(len(records))}
        self.comparisons = self.read_bytes = self.raw_rows_read = 0
        self.edges = self.compatible_edges = self.no_crossing_overlap = self.path_conflicts = 0
        self.witnesses = {}
        retained = set()
        digest = hashlib.sha256()
        previous_end,count = 0,0
        with self.proof.open("rb") as source:
            while data := source.readline(MAX_PROOF_LINE+1):
                digest.update(data); count += 1
                if len(data)>MAX_PROOF_LINE or not data.endswith(b"\n") or count>MAX_ROWS:
                    raise wa.ExperimentError("raw overlap provenance exceeds supported row/line bounds")
                row = json.loads(data)
                start,end = row.get("raw_byte_start"),row.get("raw_byte_end")
                raw_hash = row.get("raw_sha256")
                if (type(row.get("raw_line")) is not int or row["raw_line"]!=count or type(start) is not int or type(end) is not int
                        or start!=previous_end or not start<end<=self.identities[0]["size"] or end-start>MAX_LINE
                        or type(raw_hash) is not str or not HASH.fullmatch(raw_hash)):
                    raise wa.ExperimentError("raw overlap provenance has missing/noncontiguous row extents")
                previous_end = end
                window_data = row.get("window",{})
                alias = window_data.get("alias") if isinstance(window_data,dict) else None
                if alias not in windows or window_data!=asdict(windows[alias]):
                    raise wa.ExperimentError("raw overlap provenance differs from original window manifest")
                status,owner = row.get("status"),row.get("owned_row")
                if status=="outside_owned_core":
                    if owner is not None:
                        raise wa.ExperimentError("context-only raw row claims an owned candidate")
                    continue
                if not _integer(owner,1):
                    raise wa.ExperimentError("raw overlap origin requires an integer owned-row identity")
                if status=="retained":
                    if not _integer(owner,1) or owner!=len(retained)+1:
                        raise wa.ExperimentError("retained overlap origins do not preserve owned-row order")
                    retained.add(owner)
                elif status!="exact_duplicate" or owner not in retained:
                    raise wa.ExperimentError("raw overlap duplicate lacks an earlier retained owner")
                if owner not in self.origins:
                    raise wa.ExperimentError("raw overlap provenance has a foreign owned row")
                hit,window,*_ = records[owner-1]
                lifted = row.get("lifted")
                if (window.alias!=alias or hit.mapq!=255 or not isinstance(lifted,list) or len(lifted)!=6
                        or not _integer(lifted[0]) or not _integer(lifted[1],1)
                        or not windows[alias].start<=lifted[0]<lifted[1]<=windows[alias].end
                        or lifted[2:4]!=[hit.strand,hit.target]
                        or not _integer(lifted[4]) or not _integer(lifted[5],1)
                        or not 0<=lifted[4]<lifted[5]<=hit.tlen or not _integer(row.get("raw_mapq"))
                        or row["raw_mapq"]>255):
                    raise wa.ExperimentError("raw overlap origin differs from its owned query/target scope")
                self.origins[owner].append(Origin(count,start,end,raw_hash,alias,owner,tuple(lifted),row["raw_mapq"]))
        if (retained!=set(self.origins) or previous_end!=self.identities[0]["size"]
                or digest.hexdigest()!=proof_sha256
                or [wa.fingerprint(p) for p in (self.raw,self.proof)]!=self.identities):
            raise wa.ExperimentError("raw overlap origins are incomplete or changed from their producer receipt")
        self.raw_rows = count
        self.handle = self.raw.open("rb")
        try:
            # Even singleton/unjoined owners need an actual native source path;
            # otherwise a changed owned PAF could evade all edge comparisons.
            for origins in self.origins.values():
                self._load(origins[0])
        except BaseException:
            self.handle.close()
            raise

    def close(self):
        self.handle.close()

    def _load(self,origin):
        size = origin.end-origin.start
        if self.read_bytes+size>MAX_READ_BYTES:
            raise wa.ExperimentError("native overlap comparison exceeded its explicit read-work bound")
        self.handle.seek(origin.start)
        data = self.handle.read(size)
        self.read_bytes += len(data); self.raw_rows_read += 1
        if len(data)!=size or not data.endswith(b"\n") or hashlib.sha256(data).hexdigest()!=origin.digest:
            raise wa.ExperimentError("raw overlap path changed from its recorded native row")
        raw = wa.parse_hit(data.decode("ascii"),self.windows,self.targets)
        if raw.query!=origin.alias or raw.mapq!=origin.mapq:
            raise wa.ExperimentError("raw overlap row belongs to another window/provenance record")
        window = self.windows[origin.alias]
        hit = wa.lift(raw,window)
        if (hit.qs,hit.qe,hit.strand,hit.target,hit.ts,hit.te)!=origin.lifted:
            raise wa.ExperimentError("raw overlap coordinates differ from validated recovery provenance")
        owned = wa.clip_to_core(hit,window)
        if owned is None or signature(owned)!=signature(self.records[origin.owner-1][0]):
            raise wa.ExperimentError("raw overlap CIGAR no longer backs its original owned candidate")
        return hit

    def compatible(self,left,right):
        self.edges += 1
        if self.edges>MAX_COMPARISONS:
            raise wa.ExperimentError("native overlap graph exceeded its explicit candidate-edge bound")
        a,b = self.records[left][0],self.records[right][0]
        seam = a.qe if a.strand=="+" else a.qs
        crossing = False
        for first in self.origins[left+1]:
            for second in self.origins[right+1]:
                self.comparisons += 1
                if self.comparisons>MAX_COMPARISONS:
                    raise wa.ExperimentError("native overlap graph exceeded its explicit origin-pair bound")
                lo,hi = max(first.lifted[0],second.lifted[0]),min(first.lifted[1],second.lifted[1])
                if not lo<seam<hi:
                    continue
                crossing = True
                full_left,full_right = self._load(first),self._load(second)
                window = wa.Window(a.query,a.query,a.qlen,0,a.qlen,lo,hi)
                clipped_left,clipped_right = wa.clip_to_core(full_left,window),wa.clip_to_core(full_right,window)
                if clipped_left is None or clipped_right is None:
                    raise wa.ExperimentError("crossing raw overlap unexpectedly clipped to an empty path")
                common = signature(clipped_left)
                if common!=signature(clipped_right):
                    # Do not retain the previous pair while reading the next.
                    del full_left,full_right,clipped_left,clipped_right,common
                    continue
                witness = {"left_owned_row":left+1,"right_owned_row":right+1,
                           "native_raw_rows":[first.row,second.row],"overlap_query":[lo,hi],
                           "seam_query":seam,"shared_path_sha256":path_digest(common),
                           "rule":"exact_native_CIGAR_on_entire_shared_overlap_straddling_seam"}
                self.witnesses[(left,right)] = witness
                self.compatible_edges += 1
                return True
        if crossing:
            self.path_conflicts += 1
        else:
            self.no_crossing_overlap += 1
        return False

    def receipt(self):
        if ([wa.fingerprint(p) for p in (self.raw,self.proof)]!=self.identities
                or wa.sha256(self.raw)!=self.raw_sha256 or wa.sha256(self.proof)!=self.proof_sha256
                or wa.sha256(Path(__file__))!=self.implementation_sha256
                or [wa.fingerprint(p) for p in (self.raw,self.proof)]!=self.identities):
            raise wa.ExperimentError("native overlap evidence changed before stitched publication")
        return {"overlap_consistency_required":True,"overlap_policy":"native_raw_shared_path",
                "raw_sha256":self.raw_sha256,"owned_provenance_sha256":self.proof_sha256,
                "implementation_sha256":self.implementation_sha256,
                "raw_rows":self.raw_rows,"candidate_edges_checked":self.edges,
                "origin_pairs_checked":self.comparisons,"compatible_edges":self.compatible_edges,
                "rejected_no_crossing_overlap":self.no_crossing_overlap,"rejected_path_conflict":self.path_conflicts,
                "raw_rows_read":self.raw_rows_read,"raw_bytes_read":self.read_bytes,
                "whole_query_dp_equivalence_certified":False}
