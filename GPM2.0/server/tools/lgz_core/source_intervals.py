"""Frozen donor context and live, global source-interval authorization.

Alignments may use the complete member. New DNA cannot repeat a live source
interval. Replacements release only the portions actually removed by that edit;
subsequent rounds derive their state from the resulting paths, not a monotone
historical "consumed" list. Coordinates here are zero-based, half-open.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .common import canonical_json, read_tsv, sha256_file, stable_id
from .q0_publication import FREEZE, FREEZE_SCHEMA, validate_prepared_q0
from .q0_sources import Interval, Q0EvidenceError, SourceKey, merged_intervals, split_source, subtract_intervals

POLICY_VERSION = "live_source_intervals_v1"


def overlaps(a, b):
    """Half-open edit collision, including insertions inside removed windows."""
    if a[0] == a[1]:
        return a == b or b[0] < a[0] < b[1]
    if b[0] == b[1]:
        return a[0] < b[0] < a[1]
    return max(a[0], b[0]) < min(a[1], b[1])


@dataclass(frozen=True)
class SourceSpan:
    chromosome: str
    query: Interval
    source: SourceKey
    interval: Interval
    orientation: str

    def project(self, query):
        if self.orientation == "+":
            return Interval(self.interval.start + query.start - self.query.start,
                            self.interval.start + query.end - self.query.start)
        return Interval(self.interval.end - (query.end - self.query.start),
                        self.interval.end - (query.start - self.query.start))


def source_spans(paths):
    spans, lengths, occupied = [], {}, defaultdict(list)
    for chromosome, path in paths.items():
        cursor = 0
        for item in path:
            length = int(item["length"])
            if length < 1:
                raise Q0EvidenceError("source ledger path has an empty segment")
            if item["segment_kind"] == "source":
                source = SourceKey(str(item["dataset_name"]), str(item["contig_name"]))
                interval = Interval(int(item["source_start"]) - 1, int(item["source_end"]))
                if interval.length != length or item["orientation"] not in {"+", "-"}:
                    raise Q0EvidenceError("source ledger coordinates disagree with path length/orientation")
                occupied[source].append(interval)
                spans.append(SourceSpan(str(chromosome), Interval(cursor, cursor + length), source, interval, item["orientation"]))
            elif item["segment_kind"] != "gap":
                raise Q0EvidenceError("source ledger path has an unsupported segment kind")
            cursor += length
        lengths[str(chromosome)] = cursor
    for source, intervals in occupied.items():
        ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
        if any(left.end > right.start for left, right in zip(ordered, ordered[1:])):
            raise Q0EvidenceError(f"live path repeats source interval: {source.dataset}:{source.contig}")
    return spans, lengths


class SourceAuthorization:
    def __init__(self, source_lengths, members, informative, *, fingerprint, chromosomes=None):
        self.source_lengths = source_lengths
        self.members = members
        self.informative = informative
        self.fingerprint = stable_id(POLICY_VERSION, [fingerprint, sha256_file(Path(__file__))])
        self.chromosomes = frozenset(chromosomes) if chromosomes is not None else None

    @classmethod
    def load(cls, root: Path, sources, *, frozen=None):
        package = read_tsv(root / "metadata/package.tsv")[0]
        members = read_tsv(root / "metadata/grt_donor_members.tsv")
        source_lengths = {SourceKey(*key): len(sequence) for key, sequence in sources.items()}
        member_map = {}
        for row in members:
            key = (row["donor_set_id"], row["member_id"])
            source = SourceKey(row["dataset_name"], row["contig_name"])
            domain = Interval(int(row["source_start"]) - 1, int(row["source_end"]))
            if key in member_map or source not in source_lengths or domain.end > source_lengths[source]:
                raise Q0EvidenceError("invalid frozen donor source membership")
            member_map[key] = (source, domain)
        if package["schema_version"] == "3":
            if frozen is None:
                frozen = validate_prepared_q0(root)
            if frozen.get("schema") != FREEZE_SCHEMA:
                raise Q0EvidenceError("unsupported donor freeze; rerun prepare_lgz_inputs.sh")
            informative = {SourceKey(**row["source"]): tuple(Interval(**i) for i in row["informative_intervals"])
                           for row in frozen["sources"]}
            selection = json.loads((root / frozen["selection"]).read_text())["construction"]
            chromosomes = {chr_name for chr_name, search in selection["searches"].items() if search["path"] is not None}
            fingerprint = stable_id(POLICY_VERSION, [sha256_file(root / FREEZE), sorted(chromosomes)])
        elif package["schema_version"] == "2":
            # Historical input decoding, not the removed first-dataset q0
            # builder. Mutable processing still enforces the live-path rule.
            informative = {}
            for key, sequence in sources.items():
                source = SourceKey(*key)
                try:
                    informative[source] = tuple(part.interval for part in split_source(source, sequence).segments)
                except Q0EvidenceError:
                    informative[source] = ()
            chromosomes = None
            fingerprint = stable_id(POLICY_VERSION, [members, [(asdict(k), [asdict(i) for i in v]) for k, v in sorted(informative.items())]])
        else:
            raise Q0EvidenceError("unsupported source interval authorization package")
        return cls(source_lengths, member_map, informative, fingerprint=fingerprint, chromosomes=chromosomes)

    def validate_paths(self, paths):
        spans, lengths = source_spans(paths)
        if self.chromosomes is not None and set(lengths) != self.chromosomes:
            raise Q0EvidenceError("source authorization requires all live chromosome paths")
        for span in spans:
            if span.source not in self.source_lengths or span.interval.end > self.source_lengths[span.source]:
                raise Q0EvidenceError("live path source exceeds original sequence")
        return spans, lengths

    def frame(self, paths, donor_set_id, working_version):
        return EditFrame(self, paths, donor_set_id, working_version)


class EditFrame:
    def __init__(self, authorization, paths, donor_set_id, working_version):
        self.authorization = authorization
        self.spans, self.lengths = authorization.validate_paths(paths)
        self.donor_set_id = donor_set_id
        self.working_version = working_version
        self.snapshot = stable_id("source-state", [working_version, [asdict(span) for span in self.spans], self.lengths])
        self.removals = defaultdict(list)
        self.targets = defaultdict(list)
        self.additions = defaultdict(list)

    def _target(self, candidate):
        chromosome = str(candidate["chr"])
        if chromosome not in self.lengths:
            raise Q0EvidenceError("candidate targets a chromosome absent from the live paths")
        if candidate.get("terminal") in {"5prime", "3prime"}:
            cut = int(candidate["target_end"])
            start, end = (0, cut) if candidate["terminal"] == "5prime" else (cut, self.lengths[chromosome])
        else:
            start, end = int(candidate["input_start"]) - 1, int(candidate["input_end"])
        if not 0 <= start <= end <= self.lengths[chromosome]:
            raise Q0EvidenceError("candidate edit exceeds its live chromosome")
        return chromosome, (start, end)

    def try_accept(self, candidate):
        chromosome, target = self._target(candidate)
        decision = {"schema": POLICY_VERSION, "authorization_id": self.authorization.fingerprint,
                    "working_version": self.working_version, "input_source_state": self.snapshot,
                    "target_chr": chromosome, "target_interval": list(target),
                    "donor_set_id": self.donor_set_id, "member_id": str(candidate.get("member_id", ""))}
        candidate["source_interval_authorization"] = decision
        def reject(reason):
            decision.update(status="rejected", reason=reason)
            return reason
        if any(overlaps(target, other) for other in self.targets[chromosome]):
            return reject("source_guard_target_overlap")
        source = SourceKey(str(candidate["source_dataset"]), str(candidate["source_contig"]))
        removing_only = candidate.get("interval_edit_kind") == "remove"
        if candidate.get("source_consumable") is False and not removing_only:
            raise Q0EvidenceError("source-free edit must declare its actual removal semantics")
        addition = None
        if not removing_only:
            member = self.authorization.members.get((self.donor_set_id, str(candidate.get("member_id", ""))))
            if member is None or member[0] != source:
                return reject("donor_member_not_in_frozen_context")
            start = candidate["used_source_start"] if "used_source_start" in candidate else candidate["source_start"]
            end = candidate["used_source_end"] if "used_source_end" in candidate else candidate["source_end"]
            addition = Interval(int(start) - 1, int(end))
            decision.update(source=asdict(source), added_source_interval=asdict(addition))
            if not member[1].contains(addition) or subtract_intervals(addition, self.authorization.informative[source]):
                return reject("donor_interval_outside_frozen_informative_context")
        # A structural correction inserts only N/deletes DNA. Its alignment
        # guide can be the reference, not a frozen donor; it authorizes no new
        # source DNA. The correction engine must validate that guide evidence.
        removed, remaining = defaultdict(list), defaultdict(list)
        for span in self.spans:
            previous_cuts = [Interval(*window) for window in self.removals[span.chromosome] if window[0] < window[1]]
            live = subtract_intervals(span.query, previous_cuts)
            for interval in live:
                if span.chromosome == chromosome and target[0] < target[1]:
                    overlap = interval.intersection(Interval(*target))
                    if overlap:
                        removed[span.source].append(span.project(overlap))
                        remaining[span.source].extend(span.project(i) for i in subtract_intervals(interval, (overlap,)))
                        continue
                remaining[span.source].append(span.project(interval))
        if addition is not None:
            if any(addition.intersection(i) for i in (*remaining[source], *self.additions[source])):
                return reject("donor_interval_still_present_in_live_path")
        reused = merged_intervals(overlap for interval in removed[source]
                                  if addition is not None and (overlap := interval.intersection(addition)) is not None)
        decision.update(status="accepted", operation="remove" if removing_only else "replace",
                        source=asdict(source), added_source_interval=asdict(addition) if addition else None,
                        reused_within_replacement=[asdict(i) for i in reused],
                        released_source_intervals=[{"source": asdict(key), "intervals": [asdict(i) for interval in merged_intervals(intervals)
                            for i in subtract_intervals(interval, (addition,) if key == source and addition else ())]}
                            for key, intervals in sorted(removed.items())])
        self.targets[chromosome].append(target)
        self.removals[chromosome].append(target)
        if addition is not None:
            self.additions[source].append(addition)
        return None


def attach_authorizations(evidence_rows, candidates):
    by_evidence = {}
    for candidate in candidates:
        decision = candidate.get("source_interval_authorization")
        if decision is None:
            continue
        identifiers = [*candidate.get("evidence_ids", []),
                       *(candidate.get(field, "") for field in
                         ("evidence_id", "mummer_evidence_id", "minimap_evidence_id"))]
        for identifier in filter(None, identifiers):
            key = str(identifier)
            if key in by_evidence and by_evidence[key] != decision:
                raise Q0EvidenceError("an evidence identifier has conflicting interval authorizations")
            by_evidence[key] = decision
    for row in evidence_rows:
        if str(row["evidence_id"]) in by_evidence:
            parameters = json.loads(str(row["parameters_json"]))
            parameters["source_interval_authorization"] = by_evidence[str(row["evidence_id"])]
            row["parameters_json"] = canonical_json(parameters)
