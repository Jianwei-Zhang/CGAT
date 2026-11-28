"""Complete the cache accounting under the current pinned verifier; reuse the audited 176 rows."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from census_wheat_q0_fork import bounded,bind,require,write
from pilot_exact_group_inventory import audit
from pilot_exact_group_windows import REQUEST,AXES,TOOL
from lgz_core import q0_regional_mapping as m


def main(base,out):
    _,root,lookup,_,_=bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json");planraw=bounded(out/"planned.json",8<<20);plan=json.loads(planraw)
    prior=out.parent.parent/"inventory/result/inventory.json";pin="3f4832fa0253841e5674cda0358f4344f514b4f9cab648a5e368fb8c60c7e794";prev=json.loads(bounded(prior,1<<20,pin));require(prev["request_sha256"]==REQUEST and prev["axes_sha256"]==AXES and prev["status_counts"]=={"verified":176} and plan["all_queries"]==len(plan["all_rows"])==754,"wrong provenance");raw={r["context"]:r for r in prev["contexts"]};tool=m._ops().executable_identity("minimap2");require(tool["sha256"]==TOOL,"wrong current binary");ans=[]
    for v in plan["eligible_regions"]:
        name=v["context"];cat=v["category"]
        if name in raw:
            row=raw[name];require(row["category"]==cat,"wrong audited input")
        elif not (root/"grt/evidence/q0_prepare/regional"/name/"context.json").is_file():row=dict(context=name,category=cat,status="no_stored_context")
        else:row=audit(root,lookup,tool,prev["reference_bases"],cat,name,v["axis_hash"])
        ans.append(row)
    scopes=plan["partial_after_parent_rule"];require(len({r["context"] for r in ans})==len(ans)==scopes.get("observed_touched",0)+scopes.get("reconstructed_touched",0) and sum(scopes.values())==754,"incomplete parent-aware accounting")
    report=dict(group="4D",query_members=766,all_planned_4D_queries=754,demand_sources=181,demand_spans=300,requested_by_axis_before_parent_fallback=plan["categories_before_parent_fallback"],fallback_parents=plan["fallback_parents"],scope_after_parent_rule=scopes,selected_regions=len(ans),matching_original_raw_status=Counter(r["status"] for r in ans),raw_rows_verified=sum(r.get("raw_rows",0) for r in ans),raw_bytes_verified=sum(r.get("raw_bytes",0) for r in ans),mapper_calls_during_audit=0,prior_inventory_sha256=pin,plan_sha256=sha256(planraw).hexdigest(),scope="All 754 original partial-plan windows with a query in the frozen 4D group and its first questions. Includes target contexts outside 4D. Does not include other query groups pointing into 4D, subsequent questions, native or repair tasks. Missing regional receipts are not negative alignments. No formal Q0 published.")
    write(out/"all-4d.json",report);print(report,flush=True)


if __name__=="__main__":main(*map(Path,sys.argv[1:]))
