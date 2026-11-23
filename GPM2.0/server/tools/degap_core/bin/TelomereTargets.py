"""Shared, disk-backed telomere targets; no target extension or global clustering.

The exact sampled-seed index is an admissibility filter, not an approximate
nearest-neighbour/top-N search. Every locally unique, complex query 21-mer is
looked up. All retrieved records enter one multi-query MUMmer comparison.
"""
import csv
import fcntl
import hashlib
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter
from functools import lru_cache

from Bio import SeqIO
from ExtensionFamilies import atomic_json, fingerprint, read_json
from FamilyTools import content_hash
from FamilyOverlap import MummerOverlap

POLICY = {"version": "telomere-targets-v1", "k": 21, "stride": 20,
          "anchor_span": 500, "anchor_seeds": 3, "min_support": 2,
          "support_bases": 200, "support_identity": 80.0, "projection_limit": 1000,
          "batch_records":256, "batch_bases":8*1024*1024, "anchor_grid":50,
          "ranking": "identity-overlap-overhang-readid-sequence-v1"}
_TRANS = str.maketrans("ACGT", "0123")


@lru_cache(maxsize=65536)
def seed_code(word):
    if len(word) != POLICY["k"] or any(c not in "ACGT" for c in word):
        return None
    # A telomeric motif (including rotations), homopolymer or short tandem
    # repeat is not a chromosome-assignment anchor. No pool-frequency filter:
    # a genuine high-depth locus must not be discarded because many reads share it.
    if max(word.count(c) for c in "ACGT") > len(word) * .8:
        return None
    if any(word[p:] == word[:-p] for p in range(1, 13)):
        return None
    if len({word[i:i+3] for i in range(len(word)-2)}) < 10:
        return None
    return int(word.translate(_TRANS), 4)


def query_seeds(sequence):
    """Keep only keys unique within this cumulative chromosome sequence."""
    keys, repeated = {}, set()
    k = POLICY["k"]
    for pos in range(len(sequence)-k+1):
        code = seed_code(sequence[pos:pos+k])
        if code is None or code in repeated:
            continue
        if code in keys:
            del keys[code]
            repeated.add(code)
        else:
            keys[code] = pos
    return keys


def prefix_projection(reference, query, *, unique=True):
    """Global reference / free query suffix edit alignment, for <= edge bases.

    Return the unique best query cut. Ambiguous cuts never authorize a splice.
    The chromosome sequence itself is retained; this only locates a read cut.
    """
    if not reference:
        return 0
    if len(reference) > 1000:
        raise ValueError("Terminal projection exceeds the bounded 1000 bp window")
    allowance = max(1, math.floor(len(reference)*.2))
    query = query[:len(reference)+allowance]
    previous = list(range(len(query)+1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(query, 1):
            current.append(min(previous[j]+1, current[j-1]+1, previous[j-1]+(a != b)))
        previous = current
    best = min(previous)
    cuts = [j for j, score in enumerate(previous) if score == best]
    if best > allowance or (unique and len(cuts) != 1):
        return None
    return cuts[0]


class TargetIndex:
    """One immutable SQLite postings index per pool content, shared across ends."""
    def __init__(self, pool, shared_directory):
        self.pool = Path(pool).resolve()
        self.source_hash = content_hash(self.pool)
        self.identity = fingerprint({"schema": "telomere-target-index-v2",
                                     "source": self.source_hash,
                                     "k": POLICY["k"], "stride": POLICY["stride"],
                                     "seed_policy": POLICY["version"], "code_sha256": content_hash(__file__)})
        shared = Path(shared_directory).resolve()
        shared.mkdir(parents=True, exist_ok=True)
        self.directory = shared / self.identity
        with (shared / (self.identity + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (self.directory / "index.json").exists():
                self._build(shared)
            self.manifest = read_json(self.directory / "index.json")
            body = {k: v for k, v in self.manifest.items() if k != "payload_sha256"}
            if (self.manifest.get("payload_sha256") != fingerprint(body) or
                    self.manifest.get("identity") != self.identity):
                raise ValueError("Changed completed telomere index manifest")
            for name, digest in self.manifest["files"].items():
                if content_hash(self.directory / name) != digest:
                    raise ValueError(f"Changed completed telomere index: {name}")
        self.db = sqlite3.connect((self.directory / "targets.sqlite").as_uri()+"?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row
        self.fasta = (self.directory / "targets.fa").open("rb")

    def close(self):
        self.db.close()
        self.fasta.close()

    def _build(self, shared):
        # Interrupted construction is never mistaken for a completed index.
        work = Path(tempfile.mkdtemp(prefix=self.identity + ".pending.", dir=shared))
        db = sqlite3.connect(work / "targets.sqlite")
        raw = duplicates = total_bases = 0
        try:
            db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
                             "PRAGMA cache_size=-65536; PRAGMA temp_store=FILE;"
                             "CREATE TABLE reads (number INTEGER PRIMARY KEY, read_id TEXT, digest TEXT,"
                             " offset INTEGER, length INTEGER, UNIQUE(read_id,digest));"
                             "CREATE TABLE seeds (code INTEGER NOT NULL, number INTEGER NOT NULL);")
            with (work / "targets.fa").open("wb") as fasta, self.pool.open() as source:
                for record in SeqIO.parse(source, "fasta"):
                    raw += 1
                    sequence = str(record.seq).upper()
                    if not sequence or any(c not in "ACGTRYSWKMBDHVN" for c in sequence):
                        raise ValueError(f"Invalid telomere target sequence: {record.id}")
                    digest = hashlib.sha256(sequence.encode()).hexdigest()
                    if db.execute("SELECT 1 FROM reads WHERE read_id=? AND digest=?", (record.id,digest)).fetchone():
                        duplicates += 1
                        continue
                    number = raw
                    fasta.write(f">tel_{number:012d}\n".encode())
                    offset = fasta.tell()
                    fasta.write(sequence.encode()+b"\n")
                    db.execute("INSERT INTO reads VALUES(?,?,?,?,?)", (number,record.id,digest,offset,len(sequence)))
                    codes = {seed_code(sequence[p:p+POLICY["k"]])
                             for p in range(0, len(sequence)-POLICY["k"]+1, POLICY["stride"])}
                    codes.discard(None)
                    db.executemany("INSERT INTO seeds VALUES(?,?)", ((code,number) for code in sorted(codes)))
                    total_bases += len(sequence)
            db.commit()
            # Append postings sequentially, then let SQLite bulk-sort once.
            # Maintaining a key-first B-tree per inserted seed causes severe
            # small random-write latency on shared cluster filesystems.
            db.execute("CREATE UNIQUE INDEX seeds_lookup ON seeds(code,number)")
            db.commit()
            distinct = db.execute("SELECT count(DISTINCT read_id) FROM reads").fetchone()[0]
            records = db.execute("SELECT count(*) FROM reads").fetchone()[0]
            postings = db.execute("SELECT count(*) FROM seeds").fetchone()[0]
            db.close()
            if content_hash(self.pool) != self.source_hash:
                raise ValueError("Telomere pool changed during index construction")
            manifest = {"identity": self.identity, "schema": "telomere-target-index-v2",
                        "source_sha256": self.source_hash, "raw_records": raw,
                        "indexed_records": records, "distinct_read_ids": distinct,
                        "duplicate_records": duplicates, "bases": total_bases, "postings": postings,
                        "builder":"sequential-postings-then-covering-index", "build_cache_mib":64,
                        "files": {name: content_hash(work/name) for name in ("targets.fa","targets.sqlite")}}
            manifest["payload_sha256"] = fingerprint(manifest)
            atomic_json(work / "index.json", manifest)
            if self.directory.exists():
                # Retain incomplete evidence rather than recursively deleting it.
                self.directory.rename(shared / (self.identity+".incomplete."+work.name.rsplit(".",1)[-1]))
            os.replace(work, self.directory)
        finally:
            db.close()

    def candidates(self, keys):
        numbers = set()
        codes = sorted(keys)
        for start in range(0, len(codes), 400):
            chunk = codes[start:start+400]
            statement = "SELECT DISTINCT number FROM seeds WHERE code IN ("+",".join("?" for _ in chunk)+")"
            numbers.update(row[0] for row in self.db.execute(statement, chunk))
        return sorted(numbers)

    def metadata(self, number):
        row = self.db.execute("SELECT * FROM reads WHERE number=?", (number,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown indexed telomere read: {number}")
        return dict(row)

    def record(self, number):
        row = self.metadata(number)
        self.fasta.seek(row["offset"])
        return row,self.fasta.read(row["length"]).decode()

    def batches(self, numbers):
        batch,bases = [],0
        for number in numbers:
            record,sequence = self.record(number)
            if batch and (len(batch)>=POLICY["batch_records"] or bases+len(sequence)>POLICY["batch_bases"]):
                yield batch
                batch,bases = [],0
            batch.append((record,sequence))
            bases += len(sequence)
        if batch:
            yield batch


def alignment_rank(item):
    a = item["alignment"]
    return (-a["identity"], -min(a["len1"], a["len2"]), item["overhang"],
            item["read_id"], item["digest"], a["s1"], a["e1"], a["s2"], a["e2"])


def _eligible(alignment, reference, query, keys, edge, minimum_length, minimum_identity):
    a = alignment
    if a["s1"] > a["e1"] or a["s2"] > a["e2"]:
        return None, "inverted_alignment"
    if min(a["len1"], a["len2"]) < minimum_length:
        return None, "short_alignment"
    if a["identity"] < minimum_identity:
        return None, "low_identity"
    end_type = a["end_type"]
    distance = ((a["s1"]-1)+(a["qry_len"]-a["e2"]) if end_type == "L" else
                (a["ref_len"]-a["e1"])+(a["s2"]-1))
    if end_type == "L":
        terminal = a["s1"]-1 <= edge and a["qry_len"]-a["e2"] <= edge
    else:
        terminal = a["ref_len"]-a["e1"] <= edge and a["s2"]-1 <= edge
    if not terminal:
        return None, "nonterminal_alignment"
    k = POLICY["k"]
    anchors = 0
    # A fixed chromosome-coordinate grid is shared by differently trimmed
    # reads; their pool-index sampling phases must not determine corroboration.
    lo, hi = a["s2"]-1, a["e2"]
    grid = POLICY["anchor_grid"]
    first = ((a["s1"]-1+grid-1)//grid)*grid
    for pos in range(first, a["e1"]-k+1, grid):
        word = reference[pos:pos+k]
        code = seed_code(word)
        if code not in keys or keys[code] != pos:
            continue
        found = query.find(word, lo, hi)
        if (found >= 0 and query.find(word, found+1, hi) < 0 and
                abs((found-lo)-(pos-(a["s1"]-1))) <= max(edge, .2*(pos-(a["s1"]-1)))):
            anchors |= 1 << (pos//grid)
    count,span = anchor_stats(anchors)
    if count < POLICY["anchor_seeds"] or span < POLICY["anchor_span"]:
        return None, "insufficient_nonrepeat_anchor"
    if end_type == "R":
        unaligned, rest = reference[a["e1"]:], query[a["e2"]:]
    else:
        unaligned, rest = reference[:a["s1"]-1][::-1], query[:a["s2"]-1][::-1]
    if len(unaligned) > 1000:
        return None, "unprojectable_boundary"
    cut = prefix_projection(unaligned, rest)
    if cut is None:
        return None, "ambiguous_boundary_projection"
    # outward is oriented away from the chromosome for either end. Reversal
    # (not complementation) is sufficient because all same-end targets agree.
    outward = rest[cut:]
    return {"alignment": a, "anchors": anchors, "overhang": distance,
            "outward": outward[:POLICY["support_bases"]*6//5], "novel_bases":len(outward), "projected_read_cut": (a["e2"]+cut if end_type == "R" else a["s2"]-1-cut)}, None


def anchor_stats(mask):
    if not mask:
        return 0,0
    return mask.bit_count(),(mask.bit_length()-(mask & -mask).bit_length())*POLICY["anchor_grid"]+POLICY["k"]


def _support(leader, other):
    """Read-ID-independent evidence for the same anchor and junction, not polishing."""
    if leader["read_id"] == other["read_id"]:
        return False
    shared = leader["anchors"] & other["anchors"]
    count,span = anchor_stats(shared)
    if count < POLICY["anchor_seeds"] or span < POLICY["anchor_span"]:
        return False
    n = min(POLICY["support_bases"], len(leader["outward"]))
    if n and (len(other["outward"]) < n or prefix_projection(
            leader["outward"][:n], other["outward"][:n+max(1,n//5)], unique=False) is None):
        return None
    return {"read_id":other["read_id"], "common_anchor_seeds":count,
            "common_anchor_span":span,
            "junction_bases_tested":n,"minimum_identity":POLICY["support_identity"]}


@lru_cache(maxsize=8)
def nucmer_thread_options(executable, executable_hash):
    # MUMmer 4 defaults to the host core count. Endpoint-level parallelism and
    # small candidate batches must not silently consume a whole compute node.
    help_text = subprocess.run([executable,"--help"],stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,check=False,text=True).stdout
    return ["--threads=1"] if "--threads" in help_text else []


class TelomereTargets:
    def __init__(self, pool, shared_directory, cache_directory, *, edge=500,
                 minimum_length=10000, minimum_identity=80.0):
        if type(minimum_length) is not int or minimum_length <= 0:
            raise ValueError("Minimum telomere overlap must be a positive integer")
        if not math.isfinite(minimum_identity) or not 0 <= minimum_identity <= 100:
            raise ValueError("Invalid minimum telomere identity")
        if type(edge) is not int or edge < 0:
            raise ValueError("Invalid telomere edge tolerance")
        self.index = TargetIndex(pool, shared_directory)
        self.edge, self.minimum_length, self.minimum_identity = edge, minimum_length, minimum_identity
        self.directory = Path(cache_directory).resolve()
        self.aligner = MummerOverlap(self.directory, edge)
        self.thread_options = nucmer_thread_options(self.aligner.tools["nucmer"],
                            self.aligner.contract["tools"]["nucmer"]["sha256"])
        self.contract = {"policy": POLICY, "edge": edge, "minimum_length": minimum_length,
                         "minimum_identity": minimum_identity, "index": self.index.identity,
                         "code_sha256": content_hash(__file__), "tools": self.aligner.contract["tools"]}
        self.aligner.contract = self.contract

    def close(self):
        self.index.close()

    def search(self, sequence_file, end_type):
        if end_type not in ("L","R"):
            raise ValueError("Invalid telomere endpoint")
        if content_hash(self.index.pool) != self.index.source_hash:
            raise ValueError("Telomere target pool changed during search")
        for name, digest in self.index.manifest["files"].items():
            if content_hash(self.index.directory/name) != digest:
                raise ValueError(f"Changed completed telomere index: {name}")
        query_hash = content_hash(sequence_file)
        with Path(sequence_file).open() as stream:
            records = list(SeqIO.parse(stream, "fasta"))
        if len(records) != 1:
            raise ValueError("Telomere chromosome query must have exactly one sequence")
        reference = str(records[0].seq).upper()
        if not reference or any(c not in "ACGTRYSWKMBDHVN" for c in reference):
            raise ValueError("Invalid telomere chromosome sequence")
        if content_hash(sequence_file) != query_hash:
            raise ValueError("Chromosome query changed during search")
        identity = fingerprint([self.contract, query_hash, end_type])
        root = self.directory / identity
        root.mkdir(parents=True, exist_ok=True)
        receipt_path = root / "search.json"
        with (self.directory / (identity+".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if receipt_path.exists():
                receipt = read_json(receipt_path)
                body = {k:v for k,v in receipt.items() if k != "payload_sha256"}
                if receipt.get("identity") != identity or receipt.get("payload_sha256") != fingerprint(body):
                    raise ValueError("Changed completed telomere search receipt")
                for name,digest in receipt["files"].items():
                    if content_hash(root/name) != digest:
                        raise ValueError(f"Changed completed telomere search artifact: {name}")
                return root, receipt["connection"]
            connection = self._search(root, reference, end_type)
            files = {str(p.relative_to(root)): content_hash(p) for p in root.rglob("*") if p.is_file()}
            receipt = {"identity": identity, "connection": connection, "files": files}
            receipt["payload_sha256"] = fingerprint(receipt)
            atomic_json(receipt_path, receipt)
        return root, connection

    def _search(self, root, reference, end_type):
        keys = query_seeds(reference)
        numbers = self.index.candidates(keys)
        query = root / "chromosome.fa"
        query.write_text(">chromosome\n"+reference+"\n")
        rejections = Counter()
        record_rejections = {}
        eligible = {}
        blocks = batches = 0
        for batch_number,batch in enumerate(self.index.batches(numbers),1):
            batches += 1
            directory = root / f"batch-{batch_number:06d}"
            directory.mkdir(exist_ok=True)
            metadata = {row["number"]:row for row,_ in batch}
            sequences = {row["number"]:seq for row,seq in batch}
            pool = directory / "candidates.fa"
            with pool.open("w") as stream:
                for row,sequence in batch:
                    stream.write(f">tel_{row['number']:012d}\n{sequence}\n")
            out = directory / "alignment"
            delta = directory / "alignment.delta"
            filtered = directory / "alignment.filtered.delta"
            coords = directory / "alignment.coords"
            self.aligner._stage(directory, "nucmer", [self.aligner.tools["nucmer"], *self.thread_options, "-c","90","-l","40",
                "-p",str(out),str(query),str(pool)], [query,pool], delta, generated=delta)
            self.aligner._stage(directory, "delta-filter", [self.aligner.tools["delta-filter"],"-m",str(delta)], [delta], filtered)
            self.aligner._stage(directory, "coords", [self.aligner.tools["show-coords"],"-TrHcl",str(filtered)], [filtered], coords)
            with coords.open() as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    fields = line.rstrip().split("\t")
                    if len(fields) != 13 or fields[11] != "chromosome" or not fields[12].startswith("tel_"):
                        raise ValueError("Malformed batched telomere coordinates")
                    try:
                        number = int(fields[12][4:])
                        a = dict(zip(("s1","e1","s2","e2","len1","len2"), map(int,fields[:6])))
                        a.update(identity=float(fields[6]), ref_len=int(fields[7]), qry_len=int(fields[8]),
                                 ref_id="chromosome", qry_id=metadata[number]["read_id"], end_type=end_type)
                    except (KeyError,ValueError) as error:
                        raise ValueError("Invalid batched telomere alignment") from error
                    if (not math.isfinite(a["identity"]) or not 0 <= a["identity"] <= 100 or
                            a["ref_len"] != len(reference) or a["qry_len"] != metadata[number]["length"] or
                            any(not 1 <= a[k] <= a["ref_len"] for k in ("s1","e1")) or
                            any(not 1 <= a[k] <= a["qry_len"] for k in ("s2","e2")) or
                            a["len1"] != abs(a["e1"]-a["s1"])+1 or a["len2"] != abs(a["e2"]-a["s2"])+1):
                        raise ValueError("Inconsistent batched telomere coordinates")
                    blocks += 1
                    item, reason = _eligible(a, reference, sequences[number], keys, self.edge, self.minimum_length, self.minimum_identity)
                    if item is None:
                        rejections[reason] += 1
                        record_rejections.setdefault(number,set()).add(reason)
                        continue
                    item.update(metadata[number])
                    if number not in eligible or alignment_rank(item) < alignment_rank(eligible[number]):
                        eligible[number] = item
        ranked = sorted(eligible.values(), key=alignment_rank)
        winner = None
        attempted = []
        for item in ranked:
            witnesses = []
            seen = {item["read_id"]}
            for other in ranked:
                support = _support(item,other) if other["read_id"] not in seen else None
                if support:
                    witnesses.append(support)
                    seen.add(other["read_id"])
                    if len(seen) >= POLICY["min_support"]:
                        break
            attempted.append({"read_id":item["read_id"],"number":item["number"],
                              "status":"supported" if len(seen)>=POLICY["min_support"] else "insufficient_support",
                              "supporting_read_ids":sorted(seen),"witnesses":witnesses,"support_is_lower_bound":True})
            if len(seen) >= POLICY["min_support"]:
                winner = item
                break
        statuses = {row["number"]:row["status"] for row in attempted}
        with (root / "candidates.tsv").open("w", newline="") as stream:
            writer = csv.writer(stream,delimiter="\t")
            writer.writerow(["read_id","record","identity","effective_overlap","endpoint_overhang",
                             "anchor_seeds","anchor_span","tel_read_tail_bases","status","reasons"])
            for number in numbers:
                item = eligible.get(number)
                writer.writerow([self.index.metadata(number)["read_id"],number,
                    item["alignment"]["identity"] if item else "",min(item["alignment"]["len1"],item["alignment"]["len2"]) if item else "",
                    item["overhang"] if item else "",*(anchor_stats(item["anchors"]) if item else ("","")),
                    item["novel_bases"] if item else "",statuses.get(number,"ranked_below_winner" if item and winner else "alignment_rejected"),
                    ";".join(sorted(record_rejections.get(number,()))) if not item else ""])
        reason = ("connected" if winner else "insufficient_read_support" if ranked else
                  "no_eligible_alignment" if numbers else "no_sampled_nonrepeat_anchor")
        best_support = (attempted[-1] if winner else max(attempted,
                        key=lambda row:len(row["supporting_read_ids"]),default=None))
        diagnostics = {"schema":"telomere-target-search-v1","strategy":"shared-exact-seed-index-batched-mummer",
            "policy":POLICY,"end_type":end_type,"pool_sha256":self.index.source_hash,"index_identity":self.index.identity,
            "pool_records":self.index.manifest["raw_records"],"indexed_records":self.index.manifest["indexed_records"],
            "distinct_read_ids":self.index.manifest["distinct_read_ids"],"query_bases":len(reference),
            "query_anchor_keys":len(keys),"retrieved_records":len(numbers),"refined_records":len(numbers),
            "alignment_blocks":blocks,"alignment_batches":batches,"eligible_records":len(ranked),"rejection_counts":dict(rejections),
            "candidate_cap":None,"global_grouping":False,"target_extension":False,
            "selection_scope":"all_index_retrieved_records_with_qualifying_anchor_and_read_support",
            "reason":reason,"winner_read_id":winner["read_id"] if winner else None,
            "support_checks":len(attempted),"supporting_read_ids":best_support["supporting_read_ids"] if best_support else [],
            "support_candidate_read_id":best_support["read_id"] if best_support else None,
            "support_count_lower_bound":len(best_support["supporting_read_ids"]) if best_support else 0,
            "selected_tail_bases":winner["novel_bases"] if winner else 0,
            "junction_bases_tested":min(POLICY["support_bases"],winner["novel_bases"]) if winner else 0,
            "support_covers":"common_nonrepeat_anchor_and_junction_proximal_sequence_not_full_telomere_length",
            "chromosome_sequence_retained":True}
        atomic_json(root / "connection-diagnostics.json",diagnostics)
        atomic_json(root / "connection-support.json",{"schema":"telomere-support-v1","attempted":attempted})
        if not winner:
            return None
        _, selected_sequence = self.index.record(winner["number"])
        cut = winner["projected_read_cut"]
        outward = selected_sequence[cut:] if end_type == "R" else selected_sequence[:cut][::-1]
        linked = reference+outward if end_type == "R" else outward[::-1]+reference
        linker = root / "linker.fa"
        linker.write_text(">chromosome_linked\n"+linked+"\n")
        return {"success":True,"read_id":winner["read_id"],"alignment":winner["alignment"],
                "linker_file":str(linker),"checked_reads":len(numbers),"total_reads":self.index.manifest["raw_records"],
                "support_count_lower_bound":diagnostics["support_count_lower_bound"],
                "supporting_read_ids":diagnostics["supporting_read_ids"],"novel_bases":len(outward),
                "diagnostics":diagnostics}


def publish_check(targets, sequence_file, end_type, directory, round_number):
    """Publish portable per-attempt evidence; verify completed copies on resume."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / "telomere-check.json"
    if not receipt_path.exists() and any(directory.glob("*.check.log")):
        raise ValueError("Legacy telomere connection check; use a new output directory")
    root, connection = targets.search(sequence_file, end_type)
    identity = fingerprint([root.name, round_number])
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        body = {k:v for k,v in receipt.items() if k != "payload_sha256"}
        if receipt.get("identity") != identity or receipt.get("payload_sha256") != fingerprint(body):
            raise ValueError("Changed published telomere check contract")
        for name,digest in receipt["files"].items():
            if content_hash(directory/name) != digest:
                raise ValueError(f"Changed published telomere evidence: {name}")
        return receipt["connection"]
    names = ["connection-diagnostics.json","connection-support.json","candidates.tsv"]
    for name in names:
        shutil.copyfile(root/name,directory/name)
    if connection:
        name = "direct.linker.fa" if round_number == 0 else f"round{round_number}.linker.fa"
        shutil.copyfile(root/"linker.fa",directory/name)
        names.append(name)
        connection = dict(connection,linker_file=str(directory/name),
                          diagnostics_file=str(directory/"connection-diagnostics.json"))
    receipt = {"schema":"telomere-check-v1","identity":identity,"connection":connection,
               "files":{name:content_hash(directory/name) for name in names}}
    receipt["payload_sha256"] = fingerprint(receipt)
    atomic_json(receipt_path,receipt)
    return connection


def check_log_lines(diagnostics):
    """Plain-text companion to the machine-readable report, including negatives."""
    d = diagnostics
    return (f"Search Strategy: {d['strategy']}\n"
            f"Pool Records: {d['pool_records']}\n"
            f"Distinct Read IDs: {d['distinct_read_ids']}\n"
            f"Retrieved Records: {d['retrieved_records']}\n"
            f"Refined Records: {d['refined_records']}\n"
            f"Eligible Records: {d['eligible_records']}\n"
            f"Candidate Cap: None\nGlobal Target Grouping: No\nTarget Extension: No\n"
            f"Connection Decision: {d['reason']}\n"
            f"Supporting Reads (at least): {d['support_count_lower_bound']}\n"
            f"Selected Tel-Read Tail: {d['selected_tail_bases']} bp\n"
            f"Outward Junction Bases Tested: {d['junction_bases_tested']} bp\n"
            f"Support Scope: {d['support_covers']}\n"
            f"Chromosome Sequence Retained At Join: Yes\n"
            f"Evidence: connection-diagnostics.json, connection-support.json, candidates.tsv\n")
