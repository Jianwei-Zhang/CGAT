"""Retained q0 provenance; no synthetic repair events or assignment rows.

Callers must validate the frozen q0 before using this index. Coordinates here
are the existing TSV/Final Path 1-based inclusive coordinates.
"""
import json
from collections import defaultdict


class Q0Lineage:
    def __init__(self, rows):
        self.roots = defaultdict(list)
        for row in rows:
            if row["q_version"] == "q0" and row["segment_kind"] != "gap":
                key = (row["chr"], row["dataset_name"], row["contig_name"], row["orientation"])
                self.roots[key].append((int(row["source_start"]), int(row["source_end"]),
                                        set(json.loads(row["evidence_ids_json"]))))

    def covers(self, chromosome, source, evidence_ids):
        """Every retained source base must be covered by linked frozen roots."""
        start, end = int(source["start"]), int(source["end"])
        if start < 1 or end < start or source["orientation"] not in {"+", "-"}:
            return False
        key = (chromosome, source["dataset"], source["contig"], source["orientation"])
        links = set(evidence_ids)
        cursor = start
        for left, right, root_links in sorted(self.roots.get(key, []), key=lambda row: row[:2]):
            if not root_links or not root_links.issubset(links) or right < cursor:
                continue
            if left > cursor:
                return False
            cursor = max(cursor, right + 1)
            if cursor > end:
                return True
        return False


def display_peer_keys(card, assignments, cards):
    """The actual comparison domain, not the presence of output files.

    Normal cards reuse coarse-assignment main-view comparisons. Promoted cards
    additionally compare against the retained promoted placements in that chr.
    """
    chromosome = card["target_chr"]
    peers = {key for key, chromosomes in assignments.items() if chromosome in chromosomes}
    if card["placement_mode"] != "normal":
        peers.update((other["dataset_name"], other["contig_name"])
                     for other in cards if other["target_chr"] == chromosome)
    return peers - {(card["dataset_name"], card["contig_name"])}
