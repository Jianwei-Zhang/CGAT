"""Contig/scaffold linking using primary and candidate extension families.

No legacy roundResult emulation: source membership, strand, endpoint state and
composition are explicit, and a joined sequence is never reconstructed twice.
"""
import copy
from dataclasses import asdict
import fcntl
import os
from pathlib import Path
import tempfile

from Bio import SeqIO
from Bio.Seq import Seq

from ExtensionFamilies import FamilySearch, Version, atomic_json, fingerprint, read_json
from FamilyGap import prepare_context
from FamilyOverlap import MummerOverlap, joined_sequence, read_sequence
from FamilyResult import atomic_text, publish_search
from FamilyRound import SingleRound
from FamilyTools import content_hash
from N50Check import N50Check
from ReportStyle import (
    badge_html,
    bi,
    esc,
    lang_switcher_html,
    lang_switcher_js,
    report_css,
    status_tone,
    summary_strip_html,
)

SCHEMA = "degap-ctg-families-v1"


def reject_legacy_ctg_output(directory):
    root = Path(directory)
    if not (root / "ctg-families.json").exists() and any(
            (root / name).exists() for name in ("used.txt", "project", "DG.project.fa", "DG.scaffold.fa")):
        raise ValueError("Legacy single-sided CtgLinker output detected; use a new output directory")


def reverse_members(members):
    return [{"id": m["id"], "strand": "-" if m["strand"] == "+" else "+"} for m in reversed(members)]


def reverse_segments(segments):
    return [dict(segment, strand="-" if segment["strand"] == "+" else "+") for segment in reversed(segments)]


def clip_segments(segments, start, end):
    """Slice composition in assembly coordinates; source intervals stay forward."""
    total = sum(s["end"] - s["start"] for s in segments)
    if not 0 <= start <= end <= total:
        raise ValueError("Composition slice is outside its sequence")
    result = []
    offset = 0
    for segment in segments:
        length = segment["end"] - segment["start"]
        lo, hi = max(start - offset, 0), min(end - offset, length)
        if lo < hi:
            if segment["strand"] == "+":
                a, b = segment["start"] + lo, segment["start"] + hi
            else:
                a, b = segment["end"] - hi, segment["end"] - lo
            result.append(dict(segment, start=a, end=b))
        offset += length
    return result


def write_fasta(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            for key, sequence in records:
                stream.write(f">{key}\n{sequence}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fasta_source(path, length=None):
    path = str(Path(path).resolve())
    return {"path": path, "sha256": content_hash(path),
            "length": length if length is not None else len(read_sequence(path))}


def verify_source(source):
    if content_hash(source["path"]) != source["sha256"]:
        raise ValueError(f"CtgLinker sequence changed: {source['path']}")


class CtgFamilyPipeline:
    def __init__(self, base, *, overlap=None, extend=None):
        self.base = copy.copy(base)
        self.base.out = str(Path(base.out).resolve())
        self.base.name = "ctglinker"
        self.base.thread = int(base.thread)
        self.base.allow_terminal_backoff = True
        self.root = Path(self.base.out)
        reject_legacy_ctg_output(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoint = self.root / "ctg-families.json"
        self.overlap = overlap or MummerOverlap(self.root / "ctg-overlaps", int(base.edge))
        self.context = prepare_context(self.base, self.overlap.contract)
        self.context.update({
            "driver": SCHEMA, "genome": {"path": str(Path(base.genomeSeq).resolve()), "sha256": content_hash(base.genomeSeq)},
            "max_rounds": getattr(base, "MaximumExtensionRound", None),
            "max_length": getattr(base, "MaximunExtensionLength", None),
            "ctg_code": content_hash(__file__),
            "input_split_code": content_hash(Path(__file__).parent / "N50Check.py"),
        })
        self.contract_id = fingerprint(self.context)
        self.extend = extend or SingleRound(self.base, context=self.context,
                                             shared_cache=self.root / "shared-extension-stages")
        self.pool = {}
        self.sources = {}
        self.original_ids = []
        self.history = []
        self.events = []
        self.current = None
        self.next_end = "left"
        self.pending = None
        self.status = "running"
        self.next_dg = 1

    def _save(self):
        value = {"schema": SCHEMA, "contract_id": self.contract_id, "context": self.context,
                 "pool": list(self.pool.values()), "sources": self.sources,
                 "original_ids": self.original_ids, "history": self.history,
                 "events": self.events, "current": self.current, "next_end": self.next_end,
                 "pending": self.pending, "status": self.status, "next_dg": self.next_dg}
        value["payload_sha256"] = fingerprint(value)
        atomic_json(self.checkpoint, value)

    def _restore(self):
        value = read_json(self.checkpoint)
        payload = {k: v for k, v in value.items() if k != "payload_sha256"}
        if value.get("payload_sha256") != fingerprint(payload):
            raise ValueError("CtgLinker checkpoint content changed")
        if value.get("schema") != SCHEMA or value.get("contract_id") != self.contract_id or value.get("context") != self.context:
            raise ValueError("CtgLinker input, parameters or code changed; use a new directory")
        self.pool = {item["id"]: item for item in value["pool"]}
        if len(self.pool) != len(value["pool"]):
            raise ValueError("Duplicate active assemblies")
        for name in ("sources", "original_ids", "history", "events", "current", "next_end", "pending", "status", "next_dg"):
            setattr(self, name, value[name])
        if self.status not in ("running", "complete") or self.next_end not in ("left", "right"):
            raise ValueError("Invalid CtgLinker state")
        for source in self.sources.values():
            verify_source(source)
        for assembly in self.pool.values():
            verify_source(assembly)
            self._verify_composition(assembly)
        members = [m["id"] for a in self.pool.values() for m in a["members"]]
        if len(members) != len(set(members)) or set(members) != set(self.original_ids):
            raise ValueError("Original contig membership is missing or duplicated")
        if self.current is not None and self.current not in self.pool:
            raise ValueError("Current assembly is absent")
        if self.pending and (self.pending["primary"] != self.current or self.pending["number"] != len(self.events) + 1):
            raise ValueError("Pending endpoint search is inconsistent")

    def _initialize(self):
        ctgs = self.root / "Genome.inputCtg.fa"
        log = self.root / "Genome.inputCtg.log"
        seed_len = (getattr(self.base, "ontSeedLen", None) or self.base.hifiSeedLen) if self.base.data_type == "ont" else self.base.hifiSeedLen
        # Preserve the existing N splitting/filtering behavior, including its
        # fallback to all non-N contigs if none pass the seed-length filter.
        N50Check([self.base.genomeSeq, int(seed_len), str(ctgs), str(log)])
        source_directory = self.root / "ctg-sources"
        source_directory.mkdir(exist_ok=True)
        with ctgs.open() as stream:
            for order, record in enumerate(SeqIO.parse(stream, "fasta")):
                path = source_directory / f"contig-{order}.fa"
                write_fasta(path, [(record.id, str(record.seq))])
                source = fasta_source(path, len(record.seq))
                source.update({"origin": record.description, "kind": "input"})
                self.sources[record.id] = source
                self.original_ids.append(record.id)
                assembly = dict(source, id=record.id, members=[{"id": record.id, "strand": "+"}],
                                segments=[{"component": record.id, "start": 0, "end": len(record.seq), "strand": "+"}],
                                open={"left": True, "right": True}, order=order, kind="input")
                self.pool[record.id] = assembly
        if not self.pool:
            raise ValueError("No non-N contigs are available for CtgLinker")
        self._save()

    def _sequence(self, segments):
        pieces = []
        for segment in segments:
            source = self.sources[segment["component"]]
            verify_source(source)
            if not 0 <= segment["start"] < segment["end"] <= source["length"] or segment["strand"] not in ("+", "-"):
                raise ValueError("Invalid component interval")
            sequence = read_sequence(source["path"])[segment["start"]:segment["end"]]
            pieces.append(sequence if segment["strand"] == "+" else str(Seq(sequence).reverse_complement()))
        return "".join(pieces)

    def _verify_composition(self, assembly):
        if self._sequence(assembly["segments"]) != read_sequence(assembly["path"]):
            raise ValueError(f"Composition does not reconstruct {assembly['id']}")

    def _choose_work(self):
        if self.current is not None and not any(self.pool[self.current]["open"].values()):
            self.current = None
        if self.current is None:
            available = [a for a in self.pool.values() if any(a["open"].values())]
            if not available:
                self.status = "complete"
                self._save()
                return
            # Resume unfinished joined assemblies before starting a new longest
            # input contig, matching the previous CtgLinker selection principle.
            current = min(available, key=lambda a: (a["kind"] == "input", -a["length"], a["order"]))
            self.current = current["id"]
            self.next_end = "left"
        current = self.pool[self.current]
        direction = self.next_end if current["open"][self.next_end] else ("right" if self.next_end == "left" else "left")
        own_members = {m["id"] for m in current["members"]}
        candidates = []
        for assembly in self.pool.values():
            if assembly["id"] == current["id"] or own_members.intersection(m["id"] for m in assembly["members"]):
                continue
            for strand in ("+", "-"):
                candidates.append({"family": f"candidate{len(candidates)}", "assembly": assembly["id"], "strand": strand})
        self.pending = {"number": len(self.events) + 1, "primary": current["id"], "direction": direction,
                        "candidates": candidates}
        self._save()

    def _candidate_path(self, item):
        assembly = self.pool[item["assembly"]]
        if item["strand"] == "+":
            return assembly["path"]
        path = self.root / "ctg-sources" / (assembly["id"] + ".rc.fa")
        sequence = str(Seq(read_sequence(assembly["path"])).reverse_complement())
        if path.exists():
            if read_sequence(path) != sequence:
                raise ValueError(f"Reverse-complement candidate changed: {path}")
        else:
            write_fasta(path, [(assembly["id"] + "_rc", sequence)])
        return str(path.resolve())

    def _segments_for_version(self, search, version, assembly, strand):
        if version.number == 0:
            return copy.deepcopy(assembly["segments"]) if strand == "+" else reverse_segments(assembly["segments"])
        key = f"E{self.pending['number']}F{search.order[version.family]}V{version.number}"
        self.sources[key] = dict(fasta_source(version.path, version.length), kind="extension",
                                 event=self.pending["number"], family=version.family, version=version.number,
                                 initial_assembly=assembly["id"], initial_strand=strand)
        return [{"component": key, "start": 0, "end": version.length, "strand": "+"}]

    def _apply_connection(self, search, candidate_map):
        winner = search.winner
        current = self.pool[self.current]
        candidate_key = winner.right_family if winner.left_family == "primary" else winner.left_family
        item = candidate_map[candidate_key]
        other = self.pool[item["assembly"]]
        strand = item["strand"]
        members = copy.deepcopy(other["members"]) if strand == "+" else reverse_members(other["members"])
        direction = self.pending["direction"]
        left_version = search.families[winner.left_family].versions[winner.left_version]
        right_version = search.families[winner.right_family].versions[winner.right_version]
        if direction == "right":
            left_segments = self._segments_for_version(search, left_version, current, "+")
            right_segments = self._segments_for_version(search, right_version, other, strand)
            joined_members = current["members"] + members
            ends = {"left": current["open"]["left"], "right": other["open"]["right" if strand == "+" else "left"]}
        else:
            left_segments = self._segments_for_version(search, left_version, other, strand)
            right_segments = self._segments_for_version(search, right_version, current, "+")
            joined_members = members + current["members"]
            ends = {"left": other["open"]["left" if strand == "+" else "right"], "right": current["open"]["right"]}
        member_ids = [m["id"] for m in joined_members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Connection would reuse an already incorporated contig")
        sequence = joined_sequence(winner, left_version, right_version)
        if (winner.evidence or {}).get("plan_path"):
            from JunctionRepair import load_plan
            plan = load_plan(winner.evidence)
            # Original assemblies keep their existing component provenance.
            if direction == "right":
                origins = {winner.left_family: (current, "+"), winner.right_family: (other, strand)}
            else:
                origins = {winner.left_family: (other, strand), winner.right_family: (current, "+")}
            segments = []
            for number, piece in enumerate(plan["pieces"]):
                if piece["kind"] == "original":
                    assembly, orientation = origins[piece["family"]]
                    source_segments = copy.deepcopy(assembly["segments"]) if orientation == "+" else reverse_segments(assembly["segments"])
                    segments += clip_segments(source_segments, piece["start"], piece["end"])
                else:
                    source_id = f"J{self.pending['number']}P{number}"
                    self.sources[source_id] = dict(fasta_source(piece["path"], piece["end"]), kind=piece["kind"], event=self.pending["number"])
                    segments.append({"component": source_id, "start": piece["start"], "end": piece["end"], "strand": "+"})
        else:
            segments = clip_segments(left_segments, 0, winner.left_end) + clip_segments(right_segments, winner.right_end, right_version.length)
        if self._sequence(segments) != sequence:
            raise ValueError("Connection composition does not reconstruct its sequence")
        key = f"DG{self.next_dg}"
        path = self.root / "ctg-assemblies" / (key + ".fa")
        if path.exists() and read_sequence(path) != sequence:
            raise ValueError(f"Previously generated assembly changed: {path}")
        write_fasta(path, [(key, sequence)])
        assembly = dict(fasta_source(path, len(sequence)), id=key, kind="joined", members=joined_members,
                        segments=segments, open=ends, order=min(current["order"], other["order"]))
        del self.pool[current["id"]]
        del self.pool[other["id"]]
        self.pool[key] = assembly
        self.history.append(copy.deepcopy(assembly))
        self.current = key
        self.next_dg += 1
        return {"assembly": other["id"], "strand": strand, "members": members, "result_assembly": key}

    def _finish_endpoint(self):
        pending = self.pending
        current = self.pool[pending["primary"]]
        direction = pending["direction"]
        event = {"number": pending["number"], "primary": current["id"], "direction": direction,
                 "candidate_count": len(pending["candidates"]), "selected": None,
                 "total_rounds": 0, "total_extension_length": 0, "result_dir": None}
        if not pending["candidates"]:
            event["status"] = "no_candidates"
            current["open"][direction] = False
        else:
            directory = self.root / "project" / f"endpoint-{pending['number']:06d}"
            primary_direction = "rightward" if direction == "right" else "leftward"
            peer_direction = "leftward" if direction == "right" else "rightward"
            seeds = [("primary", primary_direction, current["path"])]
            mapping = {item["family"]: item for item in pending["candidates"]}
            for item in pending["candidates"]:
                seeds.append((item["family"], peer_direction, self._candidate_path(item)))
            context = {"project": self.context, "endpoint": pending}
            search = FamilySearch(directory, seeds, primary="primary", context=context,
                                  max_rounds=self.context["max_rounds"], max_length=self.context["max_length"])
            if hasattr(self.overlap, "configure_boundaries"):
                self.overlap.configure_boundaries(self.base, seeds)
            search.run(self.extend, self.overlap)
            published = publish_search(search, unclosed_families=["primary"])
            event["junction"] = published.get("junction")
            event["anchor_retries"] = published.get("anchor_retries", [])
            event["connection_diagnostics"] = published.get("connection_diagnostics", [])
            event.update(status=search.status, total_rounds=search.total_rounds,
                         total_extension_length=search.total_length,
                         result_dir=str(directory.relative_to(self.root)))
            if search.winner:
                event["winner"] = asdict(search.winner)
                event["selected"] = self._apply_connection(search, mapping)
            else:
                # Preserve all attempted versions in the endpoint search, but do
                # not insert an unconfirmed connection/extension into a scaffold.
                current["open"][direction] = False
        self.next_end = "right" if direction == "left" else "left"
        self.events.append(event)
        self.pending = None
        self._save()

    def run(self):
        with (self.root / "ctg-families.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("This CtgLinker project is already running") from error
            if self.checkpoint.exists():
                self._restore()
            else:
                self._initialize()
            while self.status == "running":
                if self.pending is None:
                    self._choose_work()
                if self.pending is not None:
                    self._finish_endpoint()
            return self._publish()

    def _publish(self):
        result_file = self.root / "ctglinker-result.json"
        if result_file.exists():
            result = load_ctg_result(self.root)
            if result["contract_id"] != self.contract_id:
                raise ValueError("CtgLinker result belongs to a different project")
            return result
        scaffolds = []
        for number, assembly in enumerate(sorted(self.pool.values(), key=lambda a: a["order"]), 1):
            self._verify_composition(assembly)
            scaffolds.append(dict(assembly, scaffold_id=f"Scaffold_{number}"))
        write_fasta(self.root / "DG.scaffold.fa", ((a["scaffold_id"] + "\t" + a["id"], read_sequence(a["path"])) for a in scaffolds))
        write_fasta(self.root / "DG.project.fa", ((a["id"], read_sequence(a["path"])) for a in self.history))
        component_ids = sorted({s["component"] for a in scaffolds for s in a["segments"]})
        write_fasta(self.root / "DG.scaffold.components.fa", ((key, read_sequence(self.sources[key]["path"])) for key in component_ids))
        agp = []
        for assembly in scaffolds:
            offset = 0
            for part, segment in enumerate(assembly["segments"], 1):
                length = segment["end"] - segment["start"]
                agp.append("\t".join(map(str, (assembly["scaffold_id"], offset + 1, offset + length, part, "W",
                                               segment["component"], segment["start"] + 1, segment["end"], segment["strand"]))))
                offset += length
        atomic_text(self.root / "DG.scaffold.agp", "\n".join(agp) + "\n")
        N50Check([str(self.root / "DG.scaffold.fa"), str(self.root / "DG.scaffold.log")])
        atomic_text(self.root / "unplaced.txt", "")
        atomic_text(self.root / "used.txt", "#assembly\tright-end\tleft-end\toriginal-contigs\n" +
                    "".join(a["id"] + "\t**\t**\t" + ";".join(m["id"] for m in a["members"]) + "\n" for a in scaffolds))
        result = {"schema": SCHEMA, "contract_id": self.contract_id, "status": "complete",
                  "input_contigs": self.original_ids, "sources": self.sources, "scaffolds": scaffolds,
                  "assembly_history": self.history,
                  "events": self.events, "total_rounds": sum(e["total_rounds"] for e in self.events),
                  "total_extension_length": sum(e["total_extension_length"] for e in self.events), "artifacts": {}}
        atomic_text(self.root / "ctglinker-family-report.html", render_ctg_report(result))
        for name in ("DG.scaffold.fa", "DG.project.fa", "DG.scaffold.components.fa", "DG.scaffold.agp", "DG.scaffold.log",
                     "Genome.inputCtg.fa", "Genome.inputCtg.log", "unplaced.txt", "used.txt", "ctg-families.json", "ctglinker-family-report.html"):
            result["artifacts"][name] = content_hash(self.root / name)
        result["payload_sha256"] = fingerprint(result)
        atomic_json(result_file, result)
        return load_ctg_result(self.root)


def load_ctg_result(directory):
    root = Path(directory).resolve()
    result = read_json(root / "ctglinker-result.json")
    payload = {k: v for k, v in result.items() if k != "payload_sha256"}
    if result.get("schema") != SCHEMA or result.get("status") != "complete" or result.get("payload_sha256") != fingerprint(payload):
        raise ValueError("Invalid CtgLinker result manifest")
    required = {"DG.scaffold.fa", "DG.scaffold.agp", "DG.scaffold.components.fa", "Genome.inputCtg.fa", "ctg-families.json", "ctglinker-family-report.html"}
    if not required.issubset(result["artifacts"]):
        raise ValueError("Incomplete CtgLinker publication")
    for name, digest in result["artifacts"].items():
        path = root / name
        if path.resolve().parent != root or content_hash(path) != digest:
            raise ValueError(f"CtgLinker result artifact changed: {path}")
    members = [m["id"] for a in result["scaffolds"] for m in a["members"]]
    if len(members) != len(set(members)) or set(members) != set(result["input_contigs"]):
        raise ValueError("Missing or duplicated original contigs in final scaffolds")
    input_index = SeqIO.index(str(root / "Genome.inputCtg.fa"), "fasta")
    components = SeqIO.index(str(root / "DG.scaffold.components.fa"), "fasta")
    sequences = SeqIO.index(str(root / "DG.scaffold.fa"), "fasta")
    try:
        if set(input_index) != set(result["input_contigs"]) or set(sequences) != {a["scaffold_id"] for a in result["scaffolds"]}:
            raise ValueError("FASTA identifiers disagree with CtgLinker membership")
        definitions = {}
        with (root / "DG.scaffold.agp").open() as stream:
            for line in stream:
                fields = line.rstrip().split("\t")
                if len(fields) != 9 or fields[4] != "W" or fields[8] not in ("+", "-"):
                    raise ValueError("Invalid CtgLinker AGP row")
                definitions.setdefault(fields[0], []).append(fields)
        if set(definitions) != set(sequences):
            raise ValueError("AGP objects do not match scaffold FASTA")
        for scaffold, rows in definitions.items():
            parts = []
            offset = 0
            for number, fields in enumerate(rows, 1):
                start, end, part = map(int, fields[1:4])
                first, last = map(int, fields[6:8])
                component = components[fields[5]].seq
                if start != offset + 1 or part != number or not 1 <= first <= last <= len(component) or last-first != end-start:
                    raise ValueError("Invalid AGP component coordinates")
                sequence = component[first-1:last]
                parts.append(str(sequence if fields[8] == "+" else sequence.reverse_complement()))
                offset = end
            if "".join(parts) != str(sequences[scaffold].seq):
                raise ValueError("AGP does not reconstruct the scaffold FASTA")
    finally:
        input_index.close()
        components.close()
        sequences.close()
    return result


def render_ctg_report(result):
    scaffolds = result["scaffolds"]
    events_data = result["events"]
    input_contigs = result["input_contigs"]

    rows = []
    for assembly in scaffolds:
        members = "; ".join(f'{m["id"]}({m["strand"]})' for m in assembly["members"])
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(assembly["scaffold_id"])}</td>'
            f'<td class="num">{assembly["length"]:,} bp</td>'
            f'<td class="num">{len(assembly["members"])}</td>'
            f'<td class="mono">{esc(members)}</td>'
            "</tr>"
        )
    if not rows:
        rows.append(f'<tr><td colspan="4" class="empty-state">{bi("No scaffolds recorded", "暂无组装结果")}</td></tr>')

    events = []
    closed_events = 0
    for event in events_data:
        event_status = event["status"]
        if event_status == "closed":
            closed_events += 1
        tone = status_tone(event_status)
        if event_status != "closed" and tone == "info":
            tone = "warn"
        link = (
            f'<a class="artifact-link" href="{esc(event["result_dir"])}/family-report.html">{bi("Report", "报告")}</a>'
            if event["result_dir"] else f'<span class="muted">{bi("No candidates", "无候选")}</span>'
        )
        selected = event["selected"]
        target = f'{selected["assembly"]}({selected["strand"]})' if selected else "—"
        target_html = f'<span class="mono">{esc(target)}</span>' if selected else '<span class="muted">—</span>'
        events.append(
            "<tr>"
            f'<td class="num">{esc(event["number"])}</td>'
            f'<td class="mono">{esc(event["primary"])}</td>'
            f'<td>{esc(event["direction"])}</td>'
            f'<td>{badge_html(event_status, tone)}</td>'
            f'<td>{target_html}</td>'
            f'<td class="num">{esc(event["total_rounds"])}</td>'
            f'<td>{link}</td>'
            "</tr>"
        )
    if not events:
        events.append(f'<tr><td colspan="7" class="empty-state">{bi("No endpoint searches recorded", "暂无端点搜索记录")}</td></tr>')

    total_rounds = result.get("total_rounds", sum(e.get("total_rounds", 0) for e in events_data))
    strip_items = [
        (bi("Contigs", "输入"), str(len(input_contigs)), "", ""),
        (bi("Scaffolds", "Scaffold"), str(len(scaffolds)), "accent", ""),
        (bi("Closed / Searches", "连接 / 搜索"), f"{closed_events}/{len(events_data)}", "ok" if closed_events else "", ""),
        (bi("Attempts", "轮数"), f"{total_rounds:,}", "", ""),
    ]
    if "total_extension_length" in result:
        strip_items.append((bi("Extension", "总延伸"), f'{result["total_extension_length"]:,} bp', "", ""))

    header_badge = badge_html(result["status"], status_tone(result["status"])) if result.get("status") else ""

    from JunctionReport import render_project_junctions
    junction_html = render_project_junctions(
        dict(result, events=events_data),
        include_event_details=False,
        event_href_fn=lambda ev: f'{ev["result_dir"]}/family-report.html' if ev.get("result_dir") else None,
    )
    junction_drawer = ""
    if junction_html:
        junction_drawer = (
            '<details class="fold">'
            f'<summary><span class="fold-title">{bi("Junction & Connection Summary", "连接边界与诊断汇总")}</span></summary>'
            f'<div class="fold-body">{junction_html}</div>'
            '</details>'
        )

    css = report_css(".fold-body > .jr-root { border: 0; margin: 0; } .fold-body > .jr-root > .section-header { display: none; } .fold-body > .jr-root > .section-body { padding: 4px 0 0; }")
    return f'''<!doctype html>
<html lang="en" data-lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DEGAP · CtgLinker</title>
<style>
{css}
</style>
</head>
<body>
<main class="report-shell">
  <header class="report-header">
    <div class="header-top">
      <div class="header-info">
        <div class="report-eyebrow">DEGAP · CtgLinker</div>
        <h1>{bi("CtgLinker Families", "候选家族连接")}</h1>
      </div>
      <div class="header-actions">{header_badge}{lang_switcher_html("en")}</div>
    </div>
    {summary_strip_html(strip_items)}
  </header>

  <section class="section">
    <div class="section-header"><h2>{bi("Scaffolds", "组装结果")}</h2></div>
    <div class="section-body">
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Scaffold</th>
              <th>{bi("Length", "长度")}</th>
              <th>{bi("Members", "成员数")}</th>
              <th>{bi("Original contigs & strands", "原始 contig 及方向")}</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="section-header"><h2>{bi("Endpoint Searches", "端点搜索")}</h2></div>
    <div class="section-body">
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{bi("Primary", "主序列")}</th>
              <th>{bi("End", "端点")}</th>
              <th>{bi("Status", "状态")}</th>
              <th>{bi("Selected", "选用候选")}</th>
              <th>{bi("Attempts", "轮数")}</th>
              <th>{bi("Evidence", "证据")}</th>
            </tr>
          </thead>
          <tbody>{''.join(events)}</tbody>
        </table>
      </div>
    </div>
  </section>

  <div class="fold-panel">
    {junction_drawer}
    <details class="fold">
      <summary><span class="fold-title">{bi("Files & Provenance", "输出与溯源文件")}</span></summary>
      <div class="fold-body">
        <nav aria-label="Downloadable artifacts">
          <ul class="artifact-list">
            <li><a class="artifact-link" href="DG.scaffold.fa">Scaffold FASTA</a></li>
            <li><a class="artifact-link" href="DG.scaffold.agp">AGP</a></li>
            <li><a class="artifact-link" href="DG.scaffold.components.fa">{bi("AGP components", "组成序列")}</a></li>
            <li><a class="artifact-link" href="ctglinker-result.json">{bi("Provenance", "溯源清单")}</a></li>
            <li><a class="artifact-link" href="ctg-families.json">{bi("Assembly history", "组装历史")}</a></li>
          </ul>
        </nav>
      </div>
    </details>
  </div>
</main>
<script>{lang_switcher_js()}</script>
</body>
</html>'''
