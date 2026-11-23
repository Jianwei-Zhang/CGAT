"""Boundary-aware junction composition and conservative read-backed end edits.

Assembly overlap is connection evidence, not authority to replace an original
contig. Map the original boundaries, retain original cores, and record every
proposed end edit separately from newly recovered gap sequence.
"""
from dataclasses import replace
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

from ExtensionFamilies import Version, atomic_json, fingerprint, read_json

POLICY = {"repair_window": 2000, "min_support": 5, "min_fraction": 0.8,
          "min_mapq": 20, "anchor": 500, "read_margin": 200,
          "min_boundary_identity": 95.0, "projection_padding": 32,
          "projection_max_context_edits": 4,
          "version": "bounded-read-backed-v4"}
CS = re.compile(r"(:[0-9]+|=[A-Za-z]+|\*[A-Za-z]{2}|\+[A-Za-z]+|-[A-Za-z]+)")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sequence(path):
    from FamilyOverlap import read_sequence
    return read_sequence(path)


def operations(cs):
    """Yield target/query consumption, preserving alleles from a long cs tag."""
    tokens = CS.findall(cs)
    if "".join(tokens) != cs:
        raise ValueError("Unsupported or malformed cs alignment")
    for token in tokens:
        op, text = token[0], token[1:].upper()
        if op == ":":
            yield "=", int(text), int(text), "", ""
        elif op == "=":
            yield "=", len(text), len(text), text, text
        elif op == "*":
            yield "X", 1, 1, text[0], text[1]
        elif op == "+":
            yield "I", 0, len(text), "", text
        else:
            yield "D", len(text), 0, text, ""


def paf_records(path):
    with open(path) as stream:
        for line in stream:
            if not line.strip():
                continue
            row = line.rstrip().split("\t")
            if len(row) < 12:
                raise ValueError("Malformed junction PAF")
            tags = {item.split(":", 2)[0]: item.split(":", 2)[2]
                    for item in row[12:] if item.count(":") >= 2}
            qlen, qs, qe = map(int, row[1:4])
            tlen, ts, te, matches, block, mapq = map(int, row[6:12])
            if not (0 <= qs < qe <= qlen and 0 <= ts < te <= tlen and
                    0 <= matches <= block and row[4] in ("+", "-")):
                raise ValueError("Inconsistent junction PAF coordinates")
            cs = tags.get("cs")
            if not cs:
                raise ValueError("Junction PAF lacks its required cs alignment")
            ops = list(operations(cs))
            if sum(x[1] for x in ops) != te-ts or sum(x[2] for x in ops) != qe-qs:
                raise ValueError("Junction cs does not reconstruct PAF spans")
            yield {"name": row[0], "qlen": qlen, "qs": qs, "qe": qe,
                   "strand": row[4], "target": row[5], "tlen": tlen, "ts": ts, "te": te,
                   "mapq": mapq, "identity": matches / block if block else 0,
                   "primary": tags.get("tp", "P") == "P", "ops": ops}


def query_boundary(record, position, *, after=False):
    """Project an original query boundary through indels into the draft target."""
    q, t = record["qs"], record["ts"]
    found = []
    for op, tn, qn, _, _ in record["ops"]:
        if qn and q <= position <= q+qn:
            found.append(t + (position-q if op in ("=", "X") else 0))
        elif not qn and q == position:
            found.extend((t, t+tn))
        q += qn; t += tn
    if not found:
        raise ValueError("Original boundary is outside its alignment")
    return max(found) if after else min(found)


def target_boundary(record, position):
    q, t = record["qs"], record["ts"]
    for op, tn, qn, _, _ in record["ops"]:
        if tn and t <= position <= t+tn:
            return q + (position-t if op in ("=", "X") else 0)
        q += qn; t += tn
    raise ValueError("Overlap cut is outside the original flank alignment")


def original_edits(record):
    """Invert draft-target/original-query differences into proposed flank edits."""
    q = record["qs"]
    out = []
    for op, tn, qn, target, query in record["ops"]:
        if op != "=":
            out.append({"start0": q, "end0": q+qn, "original": query,
                        "proposed": target})
        q += qn
    return out


def normalize_edit(ref, start, end, original, proposed):
    """Left-normalize pure indels so homopolymer placement is not a new allele."""
    if not original and proposed:
        while start > 0 and ref[start-1].upper() == proposed[-1].upper():
            proposed = proposed[-1] + proposed[:-1]; start -= 1; end -= 1
    elif original and not proposed:
        while start > 0 and ref[start-1].upper() == original[-1].upper():
            original = original[-1] + original[:-1]; start -= 1; end -= 1
    return start, end, original.upper(), proposed.upper()


def read_edits(record, ref):
    t = record["ts"]
    out = set()
    for op, tn, _, target, query in record["ops"]:
        if op != "=":
            out.add(normalize_edit(ref, t, t+tn, target, query))
        t += tn
    return out


def projected_allele(record, ref, start, end):
    """Extract read sequence between outer target coordinates, in target orientation."""
    t = record["ts"]
    parts = []
    for op, tn, _, _, query in record["ops"]:
        if op == "I" and start <= t <= end:
            parts.append(query)
        elif op in ("=", "X") and t < end and t+tn > start:
            lo, hi = max(start, t), min(end, t+tn)
            parts.append(query[lo-t:hi-t] if query else ref[lo:hi].upper())
        t += tn
    return "".join(parts)


def unique_context_cut(context, read, max_edits):
    """Align context to the start of a read slice and return its unique best cut.

    Fix the outer start. Leave the inner end free, without scoring any proposed
    allele. Track equally good end coordinates, not equivalent paths to one end.
    """
    size = len(context)
    if not size:
        return None
    if read.startswith(context):  # The sole edit-distance-zero cut.
        return size
    # A prefix outside this length band costs more than max_edits by length alone.
    prefix = read[:size+max_edits]
    first = max(1, size-max_edits)
    if len(prefix) < first:
        return None
    row = list(range(len(prefix)+1))
    for i, base in enumerate(context, 1):
        next_row = [i]
        for j, other in enumerate(prefix, 1):
            next_row.append(min(next_row[-1]+1, row[j]+1, row[j-1]+(base != other)))
        row = next_row
    best = min(row[first:])
    if best > max_edits:
        return None
    cuts = [j for j in range(first, len(row)) if row[j] == best]
    return cuts[0] if len(cuts) == 1 else None


def terminal_projection_allele(record, ref, start, end, pad, max_edits):
    """Locate both cuts with their own contexts before examining the edit itself."""
    lo, hi = start-pad, end+pad
    if not record["ts"] <= lo < start < end < hi <= record["te"]:
        return None
    read = projected_allele(record, ref, lo, hi)
    left = unique_context_cut(ref[lo:start].upper(), read, max_edits)
    right = unique_context_cut(ref[end:hi].upper()[::-1], read[::-1], max_edits)
    if left is None or right is None or left+right > len(read):
        return None
    return read[left:len(read)-right]


def clip_at_boundary(record, side):
    return record["qlen"]-record["qe"] if side == "L" else record["qs"]


def has_interior_anchor(record, side, length, policy):
    # Check aligned query coverage *inside* the protected core, not just the
    # total alignment span (which could mostly be within the repair window).
    start, end = (0, length-policy["repair_window"]) if side == "L" else (policy["repair_window"], length)
    q = record["qs"]
    matched = 0
    for op, _, qn, _, _ in record["ops"]:
        if op == "=":
            matched += max(0, min(end, q+qn)-max(start, q))
        q += qn
    return matched >= policy["anchor"]


def read_support(ref, edits, records, *, side, left_length, gap_length, policy=POLICY):
    """One vote per distinct primary read, including non-proposed alleles."""
    unique = {}
    duplicates = set()
    for platform, record in records:
        key = (platform, record["name"])
        if not record["primary"] or record["mapq"] < policy["min_mapq"] or record["identity"] < .90:
            continue
        if key in unique:
            duplicates.add(key)
        unique[key] = record
    for key in duplicates:
        unique.pop(key, None)
    parsed = {}
    results = []
    offset = 0 if side == "L" else left_length + gap_length
    for edit in edits:
        projected = edit.get("candidate_source") == "terminal_projection"
        key = normalize_edit(ref, edit["start0"]+offset, edit["end0"]+offset,
                             edit["original"], edit["proposed"])
        start, end = key[:2]
        alt, original, other = set(), set(), set()
        strands = set()
        unresolved = 0
        pad = min(policy["projection_padding"], policy["read_margin"]) if projected else 0
        for rid, record in unique.items():
            if record["ts"] > start-policy["read_margin"] or record["te"] < end+policy["read_margin"]:
                continue
            # Require an interior original anchor, not only reads of the draft extension.
            if side == "L" and record["ts"] > left_length-policy["repair_window"]-policy["anchor"]:
                continue
            if side == "R" and record["te"] < left_length+gap_length+policy["repair_window"]+policy["anchor"]:
                continue
            if projected:
                allele = terminal_projection_allele(record, ref, start, end, pad,
                                                    policy["projection_max_context_edits"])
                if allele is None:
                    unresolved += 1
                    other.add(rid)
                elif allele == key[3]:
                    alt.add(rid); strands.add(record["strand"])
                elif allele == key[2]:
                    original.add(rid)
                else:
                    other.add(rid)
                continue
            if rid not in parsed:
                parsed[rid] = read_edits(record, ref)
            changes = parsed[rid]
            if key in changes:
                alt.add(rid); strands.add(record["strand"])
            elif any(a <= end and b >= start for a, b, _, _ in changes):
                other.add(rid)
            else:
                original.add(rid)
        total = len(alt)+len(original)+len(other)
        fraction = len(alt)/total if total else 0.0
        accepted = (len(alt) >= policy["min_support"] and fraction >= policy["min_fraction"]
                    and strands == {"+", "-"})
        results.append(dict(edit, side=side, status="accepted" if accepted else "retained",
                            reason=("read_confirmed_terminal_projection" if projected else "independent_spanning_reads")
                            if accepted else "insufficient_or_conflicting_read_support",
                            alt_reads=len(alt), ref_reads=len(original), other_reads=len(other),
                            spanning_reads=total, alt_fraction=fraction, strands=sorted(strands),
                            _alt_ids=alt))
        if projected:
            results[-1]["unresolved_context_reads"] = unresolved  # Subset of other_reads.
    selected = [item for item in results if item["status"] == "accepted"]
    if selected:
        shared = set.intersection(*(item["_alt_ids"] for item in selected))
        shared_strands = {unique[rid]["strand"] for rid in shared}
        if (len(shared) < policy["min_support"] or
                (any(item.get("candidate_source") == "terminal_projection" for item in selected)
                 and shared_strands != {"+", "-"})):
            for item in selected:
                item.update(status="retained", reason="inconsistent_read_support_across_end_edits")
    for item in results:
        item.pop("_alt_ids", None)
    return results



def consensus_proposals(ref, records, *, side, left_length, gap_length, policy=POLICY):
    """Discover end alleles even if the seed error survives in every assembly.

    Discovery is deliberately not an acceptance vote: read_support still requires
    spanning interior anchors, both strands, allele fraction and shared phase.
    Boundary-touching indels are excluded here because gap/flank attribution
    cannot be inferred from a read indel alone; substitutions retain coordinates.
    """
    offset = 0 if side == "L" else left_length+gap_length
    length = left_length if side == "L" else len(ref)-offset
    window = min(policy["repair_window"], max(0, length-1000))
    lo, hi = (length-window, length) if side == "L" else (offset, offset+window)
    alleles = {}
    for platform, record in records:
        if not record["primary"] or record["mapq"] < policy["min_mapq"] or record["identity"] < .90:
            continue
        for allele in read_edits(record, ref):
            start, end, original, proposed = allele
            if start < lo or end > hi:
                continue
            touches_gap = (side == "L" and end >= left_length) or (side == "R" and start <= offset)
            if touches_gap and len(original) != len(proposed):
                continue
            alleles.setdefault(allele,set()).add((platform,record["name"]))
    return [{"start0":a-offset,"end0":b-offset,"original":old,"proposed":new,
             "candidate_source":"read_consensus"}
            for (a,b,old,new),ids in sorted(alleles.items()) if len(ids)>=policy["min_support"]]


def load_plan(evidence):
    path = Path(evidence["plan_path"])
    if digest(path) != evidence["plan_sha256"]:
        raise ValueError("Junction composition receipt changed")
    plan = read_json(path)
    for piece in plan["pieces"]:
        if digest(piece["path"]) != piece["sha256"]:
            raise ValueError("Junction component changed")
        if not 0 <= piece["start"] < piece["end"] <= len(sequence(piece["path"])):
            raise ValueError("Junction component coordinates changed")
    return plan


def plan_sequence(plan):
    return "".join(sequence(p["path"])[p["start"]:p["end"]] for p in plan["pieces"])


class BoundaryVerifier:
    def __init__(self, base, seeds, directory, *, policy=None):
        self.base = base
        self.origins = {key: Version.capture(key, 0, path) for key, _, path in seeds}
        self.directory = Path(directory)
        self.policy = dict(POLICY, **(policy or {}))
        self.tool = shutil.which("minimap2")
        self.tool_hash = digest(self.tool) if self.tool else None
        self.sources = []
        for platform in ("hifi", "ont"):
            path = (getattr(base, "reads_info", {}) or {}).get("working_"+platform)
            if path:
                cache = getattr(base, "_junction_source_hashes", {})
                if path not in cache:
                    cache[path] = digest(path)
                base._junction_source_hashes = cache
                self.sources.append((platform, str(Path(path).resolve()), cache[path]))

    def _align(self, root, name, reference, queries, preset, source_hash=None):
        if not self.tool:
            raise FileNotFoundError("minimap2 is required for checked junction boundaries")
        path, receipt = root/(name+".paf"), root/(name+".json")
        command = [self.tool, "-x", preset, "-c", "--cs=long", "--secondary=no",
                   "-t", str(getattr(self.base, "thread", 1)), str(reference), str(queries)]
        from FamilyTools import content_hash
        current_source = content_hash(queries)
        if source_hash and current_source != source_hash:
            raise ValueError("Original reads changed during junction validation")
        identity = fingerprint([command, digest(reference), current_source, self.tool_hash])
        if receipt.exists():
            saved = read_json(receipt)
            if saved != {"identity": identity, "sha256": digest(path)}:
                raise ValueError("Completed junction alignment changed")
            return path
        pending = path.with_suffix(".paf.pending")
        with pending.open("wb") as output, (root/(name+".stderr.log")).open("wb") as errors:
            subprocess.run(command, stdout=output, stderr=errors, check=True)
        if "[ERROR]" in (root/(name+".stderr.log")).read_text(errors="replace"):
            raise RuntimeError("minimap2 reported a junction alignment error")
        # Validate before publishing a completion receipt. Empty PAF is valid absence of evidence.
        list(paf_records(pending))
        pending.replace(path)
        atomic_json(receipt, {"identity": identity, "sha256": digest(path)})
        return path

    def __call__(self, candidate, left, right, comparison_directory):
        from FamilyOverlap import joined_sequence
        a, b = self.origins[left.family], self.origins[right.family]
        a.verify(); b.verify()
        identity = fingerprint([candidate.__dict__, left.__dict__, right.__dict__, a.__dict__, b.__dict__, self.policy,
                                self.sources, self.tool_hash])
        root = self.directory/identity
        root.mkdir(parents=True, exist_ok=True)
        plan_path = root/"composition.json"
        plan_receipt = root/"composition.receipt.json"
        if plan_receipt.exists():
            receipt = read_json(plan_receipt)
            if receipt.get("identity") != identity or receipt.get("sha256") != digest(plan_path):
                raise ValueError("Completed junction composition changed")
            evidence = dict(candidate.evidence or {}, plan_path=str(plan_path.resolve()), plan_sha256=receipt["sha256"])
            load_plan(evidence)
            return replace(candidate, evidence=evidence), "eligible_connection"
        draft = joined_sequence(candidate, left, right)
        target = root/"draft.fa"
        target.write_text(">draft\n"+draft+"\n")
        queries = root/"originals.fa"
        original = {"L": sequence(a.path), "R": sequence(b.path)}
        queries.write_text(">L\n"+original["L"]+"\n>R\n"+original["R"]+"\n")
        mapped = list(paf_records(self._align(root, "boundaries", target, queries, "asm20")))
        anchors = {}
        for side in ("L", "R"):
            length = len(original[side])
            window = min(self.policy["repair_window"], max(0, length-1000))
            hits = [r for r in mapped if r["name"] == side and r["primary"] and r["strand"] == "+"
                    and r["qlen"] == length and r["tlen"] == len(draft)
                    and r["mapq"] >= self.policy["min_mapq"]
                    and r["identity"]*100 >= self.policy["min_boundary_identity"]
                    and r["qe"]-r["qs"] >= min(1000, length)
                    and (clip_at_boundary(r, side) == 0 or
                         (clip_at_boundary(r, side) <= window and has_interior_anchor(r, side, length, self.policy)))]
            if len(hits) != 1:
                return None, "ambiguous_or_unmapped_original_"+side+"_boundary"
            anchors[side] = hits[0]
        left_clip, right_clip = (clip_at_boundary(anchors[side], side) for side in ("L", "R"))
        left_cut = query_boundary(anchors["L"], len(original["L"]), after=True) if not left_clip else anchors["L"]["te"]+left_clip
        right_cut = query_boundary(anchors["R"], 0) if not right_clip else anchors["R"]["ts"]-right_clip
        projected = {}
        if left_clip or right_clip:
            if not 0 <= left_cut <= right_cut <= len(draft):
                return None, "unresolved_clipped_original_boundaries"
            # Only a length-preserving projection is attempted. Reads must
            # validate this exact terminal allele before it can define a cut.
            for side, clip, start, end, proposed in (
                    ("L", left_clip, len(original["L"])-left_clip, len(original["L"]), draft[left_cut-left_clip:left_cut]),
                    ("R", right_clip, 0, right_clip, draft[right_cut:right_cut+right_clip])):
                if clip:
                    old = original[side][start:end].upper()
                    if old == proposed.upper() or not re.fullmatch(r"[ACGT]+", proposed, re.IGNORECASE):
                        return None, "unresolved_clipped_original_"+side+"_boundary"
                    projected[side] = {"start0": start, "end0": end, "original": old,
                                       "proposed": proposed.upper(), "candidate_source": "terminal_projection"}
        summary = {"mode": "gap", "gap_length": max(0, right_cut-left_cut),
                   "flank_length_delta": 0, "overlap_trim": 0,
                   "policy": self.policy, "flanks": {}, "repairs": [], "warnings": []}
        if projected:
            summary["warnings"].append("Soft-clipped original tail projected at unchanged length; accepted only with independent spanning reads")
        pieces = []
        def origin_piece(side, start, end):
            if end > start:
                v = a if side == "L" else b
                pieces.append({"kind": "original", "family": v.family, "path": v.path,
                               "sha256": v.sha256, "start": start, "end": end})
        def new_piece(text, kind):
            if text:
                path = root/(f"part-{len(pieces)}-{kind}.fa")
                path.write_text(f">{kind}\n{text}\n")
                pieces.append({"kind": kind, "path": str(path.resolve()), "sha256": digest(path),
                               "start": 0, "end": len(text)})
        if left_cut > right_cut:
            trim = target_boundary(anchors["R"], left_cut)
            if not 0 < trim <= len(original["R"]):
                return None, "unresolved_original_overlap_cut"
            summary.update(mode="overlap", gap_length=-trim, overlap_trim=trim)
            summary["warnings"].append("Original overlap deduplicated; left original copy retained, not polished")
            origin_piece("L", 0, len(original["L"])); origin_piece("R", trim, len(original["R"]))
            for side in ("L", "R"):
                summary["flanks"][side] = {"status": "preserved", "proposed_variants": 0,
                                            "accepted_variants": 0, "protected_variants": 0}
        else:
            gap = draft[left_cut:right_cut]
            protected = original["L"]+gap+original["R"]
            proposals = {}
            for side in ("L", "R"):
                proposed = original_edits(anchors[side])
                window = min(self.policy["repair_window"], max(0, len(original[side])-1000))
                proposals[side] = []
                for edit in proposed:
                    # A normalized event must also remain inside its permitted end.
                    norm = normalize_edit(original[side], edit["start0"], edit["end0"], edit["original"], edit["proposed"])
                    edit = dict(edit, start0=norm[0], end0=norm[1], original=norm[2], proposed=norm[3], candidate_source="assembly")
                    inside = (edit["start0"] >= len(original[side])-window if side == "L" else edit["end0"] <= window)
                    if inside and window:
                        proposals[side].append(edit)
                    else:
                        summary["repairs"].append(dict(edit, side=side, status="protected", reason="outside_bounded_terminal_window"))
            support_records = []
            if self.sources and any(len(original[side]) >= self.policy["repair_window"]+self.policy["anchor"] for side in ("L", "R")):
                reference = root/"protected.fa"
                reference.write_text(">protected\n"+protected+"\n")
                for platform, path, checksum in self.sources:
                    paf = self._align(root, "support-"+platform, reference, path,
                                      "map-hifi" if platform == "hifi" else "map-ont", checksum)
                    support_records.extend((platform, r) for r in paf_records(paf))
            for side in ("L", "R"):
                projection = projected.get(side)
                discovered = consensus_proposals(protected, support_records, side=side,
                                                 left_length=len(original["L"]), gap_length=len(gap), policy=self.policy)
                merged = {(e["start0"],e["end0"],e["original"],e["proposed"]):e for e in proposals[side]}
                for edit in discovered:
                    key = (edit["start0"],edit["end0"],edit["original"],edit["proposed"])
                    if key in merged:
                        merged[key]["candidate_source"] = "assembly_and_reads"
                    else:
                        merged[key] = edit
                if projection:
                    # Protect the exact context used to vote on the projected
                    # haplotype. A normalized equivalent indel can land just
                    # outside the clipped interval; applying both duplicates it.
                    start, end = projection["start0"], projection["end0"]
                    pad = min(self.policy["projection_padding"], self.policy["read_margin"])
                    merged = {key: edit for key, edit in merged.items()
                              if edit["end0"] < start-pad or edit["start0"] > end+pad}
                    merged[(start,end,projection["original"],projection["proposed"])] = projection
                proposals[side] = sorted(merged.values(), key=lambda e:(e["start0"],e["end0"],e["proposed"]))
                summary["repairs"].extend(read_support(protected, proposals[side], support_records, side=side,
                                                       left_length=len(original["L"]), gap_length=len(gap), policy=self.policy))
                events = [r for r in summary["repairs"] if r["side"] == side]
                accepted = sorted((r for r in events if r["status"] == "accepted"), key=lambda r:(r["start0"],r["end0"]))
                # Conflicting/overlapping proposed changes are not a composable correction.
                if any(y["start0"] < x["end0"] for x,y in zip(accepted, accepted[1:])):
                    for item in accepted:
                        item.update(status="retained", reason="overlapping_proposed_edits")
                    accepted = []
                if projection and not any(e.get("candidate_source") == "terminal_projection" for e in accepted):
                    atomic_json(root/"terminal-projection-rejected.json", {
                        "policy": self.policy, "repairs": [e for e in events
                            if e.get("candidate_source") == "terminal_projection"]})
                    return None, "insufficient_read_support_for_clipped_original_"+side+"_boundary"
                cursor = 0
                for edit in accepted:
                    if original[side][edit["start0"]:edit["end0"]].upper() != edit["original"]:
                        raise ValueError("Proposed repair does not match its original flank")
                    origin_piece(side, cursor, edit["start0"])
                    new_piece(edit["proposed"], "repair")
                    cursor = edit["end0"]
                    summary["flank_length_delta"] += len(edit["proposed"])-len(edit["original"])
                origin_piece(side, cursor, len(original[side]))
                if side == "L":
                    new_piece(gap, "gap")
                summary["flanks"][side] = {
                    "status": "repaired" if accepted else ("conflict" if proposals[side] else "preserved"),
                    "proposed_variants": len(events), "accepted_variants": len(accepted),
                    "protected_variants": sum(r["status"] == "protected" for r in events)}
            if any(r["status"] == "retained" for r in summary["repairs"]):
                summary["warnings"].append("Unconfirmed end differences retained as original sequence; not proven corrections")
        accepted = [r for r in summary["repairs"] if r["status"] == "accepted"]
        summary["left_replace_bases"] = max([len(original["L"])-r["start0"] for r in accepted if r["side"] == "L"] or [0])
        summary["right_replace_bases"] = (summary["overlap_trim"] if summary["mode"] == "overlap" else
            max([r["end0"] for r in accepted if r["side"] == "R"] or [0]))
        plan = {"schema": 1, "identity": identity, "summary": summary, "pieces": pieces,
                "originals": {"L": a.__dict__, "R": b.__dict__}}
        atomic_json(plan_path, plan)
        atomic_json(plan_receipt, {"identity": identity, "sha256": digest(plan_path)})
        evidence = dict(candidate.evidence or {}, plan_path=str(plan_path.resolve()), plan_sha256=digest(plan_path))
        return replace(candidate, evidence=evidence), "eligible_connection"
