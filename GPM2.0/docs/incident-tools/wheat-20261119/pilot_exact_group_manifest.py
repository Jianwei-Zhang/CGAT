"""Publish only a portable raw-cache locator list. The consumer must revalidate before using any row."""
import json
from pathlib import Path
import sys
from time import monotonic
from census_wheat_q0_fork import bounded,bind,require,write,SNAP,LOOK
from pilot_exact_group_inventory import audit
from pilot_exact_group_windows import REQUEST,TOOL
from lgz_core import q0_regional_mapping as m

PLAN="0c7e45935500147f51fe5616f73d6dff44a93af12d0a3b1853199b72d836ef73"
SUMMARY="866ebaa039e47f152a26499db83b92161ca7c73cdd62bea2b2dd75bb55fa9693"


def main(base,out):
    _,root,lookup,_,_=bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json");prior=out.parent.parent/"all-plan/result";plan=json.loads(bounded(prior/"planned.json",2<<20,PLAN));summary=json.loads(bounded(prior/"all-4d.json",1<<20,SUMMARY));inventory=json.loads(bounded(out.parent.parent/"inventory/result/inventory.json",1<<20,summary["prior_inventory_sha256"]));tool=m._ops().executable_identity("minimap2");require(tool["sha256"]==TOOL and set(summary["matching_original_raw_status"])=={"verified"},"wrong tool or incomplete cache")
    rows=[];start=monotonic()
    for v in plan["eligible_regions"]:
        row=audit(root,lookup,tool,inventory["reference_bases"],v["category"],v["context"],v["axis_hash"],locators=True)
        require(row["status"]=="verified" and row["raw_paf"]["sha256"]==row["raw_sha256"],"validated cache changed since accounting")
        rows.append(dict(row,query=v["query"],query_part=v["part"],axes_sha256=v["axis_hash"]))
        if len(rows)%50==0:print("VERIFIED_LOCATORS",len(rows),flush=True)
    require(len({r["query"] for r in rows})==len(rows)==summary["selected_regions"] and sum(r["raw_rows"] for r in rows)==summary["raw_rows_verified"] and sum(r["raw_bytes"] for r in rows)==summary["raw_bytes_verified"],"closure differs")
    write(out/"raw-locators.json",dict(schema="wheat_4d_exact_raw_locators_v1",group="4D",source_snapshot_sha256=SNAP,source_part_lookup_sha256=LOOK,original_plan_sha256=PLAN,accounting_sha256=SUMMARY,request_sha256=REQUEST,tool=tool,mapper_calls=0,verified_rows=len(rows),seconds=monotonic()-start,contexts=rows,usage="Read-only locators relative to the snapshot producer. Revalidate original query/targets, decision, command, all receipt bytes and CIGAR before use; preserve original core projection. Not an imported ready manifest, not cross-group completeness, and not authority to publish a path."))


if __name__=="__main__":main(*map(Path,sys.argv[1:]))
