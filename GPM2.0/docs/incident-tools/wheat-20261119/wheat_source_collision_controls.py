"""Fresh full-cohort admission and production paths with either a diagnostic prefix or a full 22-group release audit."""
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import wheat_production22_cached as whole
from wheat_selection_checkpoint import Store
from lgz_core.q0_admission import validate_admission_occupancy

GROUPS = ('1A','1B','1D','2A','2B','2D','3A','3B','3D')
CONTROLS = ('1A','3B','3D')
OLD_KIT = '913cb78bba0b14904d5b15f58806f4ea69858d91a98e95237b6430d48e547b2b'
EVIDENCE = '1b5e38e865c6a346054b5a45cc6ead4f6a1f7c012c4ba047a8077ab8d2de694d'

class ControlsSaved(Exception):
    pass

class FreshStore(Store):
    def load_admission(self):
        if (self.folder/'admission.jsonl').exists(): raise ValueError('fresh generation required')
        return None

    def save_group(self,index,chromosome,search):
        whole.require(chromosome == GROUPS[index-1], 'unexpected control group order')
        super().save_group(index,chromosome,search)
        if chromosome == GROUPS[-1]: raise ControlsSaved()

def metrics(owner, kit, geometry=False):
    from refresh_whole_wheat_cached_demand import SN, REQ, FINAL
    sel=owner/'selection'; sha=whole.sha256_file(owner/'kit.sha256'); whole.require(sha==kit,'wrong kit')
    binding=['whole-wheat-local-supplement-v1',SN,REQ,FINAL,sha,EVIDENCE,32]
    store=Store(sel,binding,False); rows=store.load_admission().placements
    by_chr=defaultdict(dict)
    for p in rows: by_chr[p.chromosome][p.placement_id]=p
    if kit != OLD_KIT:
        validate_admission_occupancy(rows)
    out={}
    for i,k in enumerate(GROUPS,1):
        path=store.load_group(i,k).path
        if k in CONTROLS:
            out[k]=whole.group_metrics(by_chr[k],path)
            if geometry:
                from wheat_reference_release_gate import slices
                out[k]["geometry"]=slices(path)
    if kit == OLD_KIT:
        whole.require(store.previous == OLD_GROUP_009, "changed baseline through 3D")
    return dict(placements=len(rows),counts=dict(Counter(p.chromosome for p in rows)),groups=out)

def seed_readonly_inputs(base, stage, owner):
    """Link only immutable snapshot inputs; staging still hashes each before use."""
    from fork_wheat_q0 import draft_stage_plan, member
    from refresh_whole_wheat_cached_demand import SN, get
    old=Path((owner/'baseline-owner').read_text().strip())
    whole.require(old.parent==base and whole.sha256_file(old/'kit.sha256')==OLD_KIT,'wrong old owner')
    prior=Path('/tmp')/(old.name+'-'+OLD_KIT[:12])
    whole.require(owner.parent==base and stage==Path('/tmp')/(owner.name+'-'+whole.sha256_file(owner/'kit.sha256')[:12]),'wrong new stage')
    if not prior.is_dir():return  # frozen staging will fetch and hash the original input
    whole.require(prior.resolve()==prior and json.loads((prior/'owner.json').read_text())==dict(owner=str(old),kit=OLD_KIT),'wrong cache')
    snapshot=get(base/'q0-latest-fork-20261123-1435/control/snapshot.json',SN)
    rows,_=draft_stage_plan(Path(snapshot['source']),snapshot);stage.mkdir(mode=0o700)
    linked=0
    for row in rows:
        source=member(prior,row['path']);dest=member(stage,row['path'])
        if not source.is_file():continue
        dest.parent.mkdir(parents=True,exist_ok=True);os.link(source,dest);linked+=1
    print('REUSED_READONLY_BASE_INPUTS',linked,flush=True)

OLD_GROUP_009 = "4526c992c919a4d9a49d62add2d2c60a86f74d8be13e2053fb054683971f56d5"
OLD_OWNER = "q0-whole-local-maps.production22-owner.Jww3W4bC"
FIELDS = ("selected_reference_bp", "source_slice_n50", "slices")


def compare(baseline, candidate):
    """No degradation per control; do not average across chromosomes."""
    by_group = {}
    for group in CONTROLS:
        a, b = baseline[group], candidate[group]
        for row in (a, b):
            whole.require(row["has_path"] is True and all(type(row[k]) is int and row[k] > 0 for k in FIELDS),
                          "invalid control data: " + group)
        by_group[group] = {"baseline": {k: a[k] for k in FIELDS}, "candidate": {k: b[k] for k in FIELDS},
                           "passed": all(b[k] >= a[k] for k in FIELDS[:2]) and b["slices"] <= a["slices"]}
    return {"baseline_job": 43225037, "baseline_group_009": OLD_GROUP_009, "groups": by_group,
            "passed": all(row["passed"] for row in by_group.values())}


def control_audit(owner, candidate):
    old = Path((owner/"baseline-owner").read_text().strip())
    whole.require(old == owner.parent/OLD_OWNER and old.resolve() == old and old != owner, "wrong control owner")
    return compare(metrics(old, OLD_KIT)["groups"], candidate)


def calibrated_controls(owner, candidate, paths):
    from wheat_reference_release_gate import slices, control_group, POLICY
    old = Path((owner/"baseline-owner").read_text().strip())
    whole.require(old == owner.parent/OLD_OWNER and old.resolve() == old, "wrong control owner")
    before = metrics(old, OLD_KIT, geometry=True)["groups"]
    # Read the same pinned reference FAI in the validator and independent relay.
    base = owner.parent
    snap, root, _, _, _ = whole.frozen.bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json")
    ref, = whole.frozen.prep.table(root, "metadata/reference.tsv", ("fai_relpath",))
    f, = [r for r in snap["files"] if r["path"] == ref["fai_relpath"]]
    lengths = {k:int(n) for k,n,*_ in (l.split("\t") for l in whole.frozen.bounded(root/f["path"], 16<<20, f["sha256"]).decode().splitlines())}
    groups = {k:control_group(before[k]["geometry"], slices(paths[k]), before[k], candidate[k], lengths[k]) for k in CONTROLS}
    return dict(policy=POLICY,baseline_job=43225037, baseline_group_009=OLD_GROUP_009, groups=groups, passed=all(r["passed"] for r in groups.values()))


def full():
    del sys.argv[1]
    base, stage, owner = map(Path, sys.argv[1:])
    whole.require(not (owner/"selection").exists() and not (owner/"result").exists(), "fresh selection required")
    seed_readonly_inputs(base, stage, owner)
    whole.main()  # No FreshStore patch: select through Un and audit all 22 groups.
    report = json.loads((owner/"result/production22-audit.json").read_text())
    if report["selector_identity"] == "q0-selector-fff8b28ccba5244af193d4bb":
        _, paths, _ = whole.read_selection(owner, sorted(report["groups"]))
        result = calibrated_controls(owner, report["groups"], paths)
    else:
        result = control_audit(owner, report["groups"])
    with (owner/"result/source-control-audit.json").open("x") as stream:
        json.dump(result, stream, indent=2)
    print("SOURCE_CONTROL_AUDIT", json.dumps(result), flush=True)


if __name__=='__main__':
    if sys.argv[1] == 'full':
        full()
    elif sys.argv[1]=='compare':
        owner=Path.cwd(); old=Path((owner/'baseline-owner').read_text().strip()); old_metrics=metrics(old,OLD_KIT)
        new_metrics=metrics(owner,whole.sha256_file(owner/'kit.sha256'))
        stable=all(old_metrics['groups'][k]==new_metrics['groups'][k] for k in CONTROLS)
        with (owner/'control-comparison.json').open('x') as f:
            json.dump(dict(baseline=old_metrics,candidate=new_metrics,exact_group_metrics=stable,
                           cross_chromosome_admission_overlaps=0,mapper_calls=0),f,indent=2)
        whole.require(stable,'control metrics differ: inspect actual values, do not release')
    else:
        seed_readonly_inputs(*map(Path,sys.argv[1:]))
        with patch.object(whole.frozen,'Store',FreshStore):
            try: whole.main()
            except ControlsSaved: print('CONTROL_PREFIX_SAVED',flush=True)
            else: raise ValueError('expected isolated control prefix')
