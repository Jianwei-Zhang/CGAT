"""Can completed native searches test the 38,267 -> 3,755 wheat target change?

Read-only eligibility and old-PAF loss screen. This does NOT run a smaller search,
call Q0 cuts on new data, or certify that either of the retired parents is safe.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

from bound_regional_scope_from_native_receipts import EXPECTED, LOOKUP_SHA
from measure_wheat_junction_bound import frozen
from probe_wheat_native_pair_scope import checked
from wheat_selection_checkpoint import need

PANEL = "q0-map-a2e519761e94eff6ca09e121"  # all nine, not queries chosen by the outcome


def scan_old(paf, output, queries, targets, keep, lookup):
    need(paf.stat().st_size == output["size"], "wrong PAF size")
    digest = sha256(); rows = Counter(); strong = Counter(); strands = Counter(); hits = {q: set() for q in queries}
    with paf.open("rb") as f:
        for raw in f:
            digest.update(raw); a = raw.decode("ascii").split(); q,t = a[0],a[5]
            need(q in queries and t in targets and a[4] in {"+", "-"} and
                 int(a[1]) == lookup[q]["length"] and int(a[6]) == lookup[t]["length"] and
                 any(x.startswith("cg:Z:") for x in a[12:]), "unexpected old PAF row")
            side = "kept" if t in keep else "excluded"
            rows[side] += 1; strands[f"{side}:{a[4]}"] += 1; hits[q].add(side)
            # Descriptive only; not thresholds for Q0 admission or junctions.
            if 10*(int(a[3])-int(a[2])) >= 9*int(a[1]) and 100*int(a[9]) >= 98*int(a[10]):
                strong[side] += 1
    need(digest.hexdigest() == output["sha256"], "original PAF changed")
    return dict(task=PANEL, original_paf_sha256=output["sha256"], rows=rows, strand_rows=strands,
                query_coverage_ge_90pct_identity_ge_98pct_rows=strong,
                queries_with_any_original_hit=sum(bool(v) for v in hits.values()),
                queries_with_hits_only_to_excluded_targets=sum(v == {"excluded"} for v in hits.values()))


def evaluate(folder, result, lookup_file, matrices):
    summary, detail, _, paths = frozen(folder, result)
    lookup = checked(lookup_file, LOOKUP_SHA)
    by_source = {(x["dataset"], x["contig"]): k for k, x in lookup.items()}
    need(len(lookup) == len(by_source) == 38267, "part is not a whole source")
    retained = {by_source[s["dataset"], s["contig"]] for s, spans in detail["source_intervals"] if spans}
    bases = lambda ids: sum(lookup[k]["length"] for k in ids)
    original_bp, retained_bp = bases(lookup), bases(retained)
    need((original_bp, len(retained), retained_bp) == (31706122489, 3755, 2302475263), "wrong library")
    former = {by_source["JM19_flye_ABD", "JM19flyeA_contig_4549"], by_source["JM19_hifiasm", "ptg000010l"]}
    rows = []; scan = None; selected = Counter(); panel = {}; chosen = set()
    for path in paths:
        parts = [by_source[s.source.dataset, s.source.contig] for s in path.slices]; selected.update(parts)
        for i,j in enumerate(path.joins):
            if j.kind != "sequence_overlap": continue
            left, right = parts[i:i+2]; ls, rs = path.slices[i:i+2]
            for q,t in [(left,right),(right,left)]:
                if q == t or q in former or lookup[q]["length"] > 500000 or t not in retained: continue
                strand = "+" if ls.orientation == rs.orientation else "-"
                chosen.add(j.join_id); panel.setdefault(strand,set()).add(q)
    for task,pin in sorted(EXPECTED.items()):
        rec = checked(matrices/task/"success.json", pin); spec = rec["spec"]
        q,t = set(spec["query_ids"]),set(spec["target_ids"])
        need(rec["status"] == "success" and spec["members"] == [[k,lookup[k]["sequence_sha256"]] for k in sorted(q|t)],
             "wrong source or receipt")
        rows.append(dict(task=task, receipt_sha256=pin, queries=len(q), targets=len(t), target_bases=bases(t),
                         retained_targets_present=len(retained&t), retired_parents_as_queries=len(q&former),
                         selected_slices_from_queries=sum(selected[k] for k in q), flags=spec["alignment_flags"]))
        if task == PANEL:
            output, = (r for r in rec["outputs"] if r["path"].endswith("/result.paf"))
            scan = scan_old(matrices/task/"result.paf", output, q, t, retained, lookup)
    return dict(schema="wheat_shortlist_control_eligibility_v1", questions=summary["questions"],
                selection_chain=summary["selection_chain"], original_targets=len(lookup), original_bp=original_bp,
                retained_targets=len(retained), retained_bp=retained_bp, native_receipts=rows, nine_query_original_paf=scan,
                prospective_short_controls=dict(maximum_query_bp=500000, distinct_selected_sequence_joins=len(chosen),
                    distinct_query_sources_by_relative_strand={k:len(v) for k,v in sorted(panel.items())}),
                mapper_starts=0, new_selector_replays=0,
                limits="Old PAF rows on retained/excluded targets, not results of re-mapping. Short control candidates are selected overlap endpoints with retained partners, not independently reproduced joins or a matched validation of the retired parents.")


if __name__ == "__main__":
    print(json.dumps(evaluate(*map(Path, sys.argv[1:])), indent=2, sort_keys=True))
