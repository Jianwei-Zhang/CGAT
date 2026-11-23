"""Read-only verification of a genuinely new caller over frozen wheat provenance."""
import argparse
import json
from pathlib import Path
from q0_science_context import opened_transition


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transition',type=Path,required=True);a=p.parse_args()
    with opened_transition(a.transition,role='probe',caller=__file__,require_installed=False) as ctx:
        ctx.verify()
        report={'status':'new_q0_caller_native_origin_verified_only','native_plan_sha256':ctx.plan_sha,
                'transition_sha256':ctx.transition_sha,'self_operations':len(ctx.selfs.profiles),
                'eligible_native_batches':len(ctx.selfs.native_tasks),'workspace_modified':False,
                'q0_runtime_installed':False,'main_task_submitted':False}
        Path('summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
