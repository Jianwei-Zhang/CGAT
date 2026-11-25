"""Compare the exact D shadow with archived A, including independent ordinary full selection."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import monotonic

from lgz_core import q0_admission as adm
from lgz_core.q0_paths import reconstruct
from lgz_core.q0_threshold_questions import questions
from lgz_core.q0_threshold_acceptance import record
from pilot_fast_group_run import GROUP, REV, REFERENCE, load, save_layout, need, sealed, write
from pilot_exact_group_kernel import exact_kernel


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def geom(rows):
    return [[asdict(k), [asdict(i) for i in v]] for k,v in sorted(rows.items())]


def winners(selection):
    return {chrom: (p.nodes, p.joins, p.slices, p.score) if (p := row.path) else None for chrom,row in selection.paths.items()}


def main(work, base, out, variant="D"):
    need(variant in ("D", "E"), "unknown exact arm")
    if variant == "E":
        from pilot_exact_group_runs import run_kernel as kernel
    else:
        kernel = exact_kernel
    out.mkdir(exist_ok=False)
    a = out.parent.parent / "A/result"
    control = sealed(a/"A.json", "28e8a2a0b6eb2971829a546df11b5385d754957a6e39f7e38b53413f8957eb8e")
    archive = base/("q0-request-ready."+REV[:8])/"qualification"
    historical = sealed(archive/"candidate.json", REFERENCE)["scientific"]
    ref_request = sealed(archive/"4d-first-request.json", "1a51ebcfef103cb8c986ca7e98cb11eb7e86f6d68f9100d057fc3446e9698ec5")
    log = lambda text: print(text, flush=True)
    start = monotonic(); data,meta = load(work,base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json"); loaded=monotonic()
    with kernel() as counts:
        draft=adm.select_request_paths(data,screen_threads=8,progress=log)
        frontier, stats=questions(data,draft,meta["assign"])
        metrics=save_layout(out,variant,[draft.paths[GROUP].path],data); elapsed=monotonic()-start
    need(metrics == control["metrics"] and record(frontier)==ref_request, "A/D draft or request changed")
    layout_hash = sha256((out/(variant+".layout.json")).read_bytes()).hexdigest()
    need(layout_hash=="11cb89c81843a2a76476b1941db6b2ff984c2622a0e9384fd7ed7c8debe58251", "A/D cuts, evidence or ordered source geometry differs")
    common=dict(runtime=REV,group=GROUP,members=meta["n"],source_bp=meta["bp"],pair_rows=len(data.pair_links),
                A_from_input_s=control["from_input_s"],candidate_from_input_s=elapsed,candidate_load_s=loaded-start,variant=variant,
                draft_operation_counts=dict(counts),request_stats=stats,mapper_calls_A=control["mapper_calls"],mapper_calls_candidate=0,
                layout_sha256=layout_hash,sequence_sha256=metrics["record_hashes"][0],request_sources=len(frontier),
                request_spans=sum(map(len,frontier.values())), formal_post_supplement=False)
    write(out/"draft.json",common); log(f"{variant}_DRAFT_VERIFIED {elapsed:.2f} s {dict(counts)}")
    # Independent full route is outside the D/A timing. Do not reuse the draft or its cache.
    before=monotonic()
    with kernel() as full_counts:
        full=adm.select_q0_paths(data,screen_threads=8,progress=log)
        req,_=questions(data,full,meta["assign"])
    need(winners(draft)==winners(full) and draft.admission.placements==full.admission.placements and record(req)==ref_request, "draft/full differ")
    v=full.admission
    scientific=dict(paths={c:digest(r.record()) for c,r in sorted(full.paths.items())}, records=digest(v.records),
                    placements=digest([asdict(p) for p in v.placements]),unplaced=digest(v.unplaced_segment_ids),
                    occupied=digest(geom(full.occupied)),ambiguous=digest(geom(v.ambiguous_intervals)),request=digest(record(req)),
                    has_path=any(r.path for r in full.paths.values()),
                    sequences={c:sha256(reconstruct(r.path,data.sources).encode()).hexdigest() for c,r in full.paths.items() if r.path})
    need(scientific==historical,"changed full fields: "+str([k for k in historical if historical[k]!=scientific.get(k)]))
    write(out/"exact.json",dict(common,full_check_s=monotonic()-before,full_operation_counts=dict(full_counts),
                               matched_full_fields=sorted(scientific),scientific_sha256=digest(scientific),
                               baseline_scientific_artifact_sha256=REFERENCE,checked_path_records=len(full.paths)))
    log(variant+"_FULL_SCIENCE_MATCH")


if __name__=="__main__": main(*map(Path,sys.argv[1:4]),*sys.argv[4:])
