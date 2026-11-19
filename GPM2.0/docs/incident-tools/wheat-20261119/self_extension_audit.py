"""Portable output-bound audit for completed incident cross/self alignment.

Read-only science inputs. This is a companion to final project delivery, not
initial-reference policy, full-workflow acceptance, or a biological accuracy claim.
"""
import argparse
import json
from pathlib import Path

from self_extension_context import installed
RECEIPT = "self-profile-receipt.json"


def self_rows(ctx):
    ctx.verify()
    for unit in sorted({row['unit_id'] for row in ctx.selfs.rows.values()}):
        ctx.selfs.output_identities(unit)
    rows=[]
    for rel,profile in sorted(ctx.selfs.profiles.items()):
        names=dict(line.split('\t',1) for line in Path(profile.native['name_map']).read_text().splitlines() if line)
        batches=[]
        for i in profile.selected:
            if not profile.validate_batch(i):raise ValueError('approximate self batch is not committed')
            native=profile.native['batches'][i];directory=Path(native['directory'])
            proof=json.loads((directory/RECEIPT).read_text())
            batches.append({'batch_index':i,'native_key':native['key'],'executed_key':proof['key'],
                'queries':[{'name':names[row['name']],'length':row['length']} for row in native['entries']],
                'query_sha256':native['query_sha256'],'policy':proof['policy'],
                'execution_profile_sha256':proof['profile_sha256'],
                'result_paf':ctx.contract.file_identity(directory/'result.paf',relative_to=ctx.work),
                'receipt_sha256':ctx.contract.sha256_file(directory/RECEIPT),
                'mapping':proof['mapping'],'candidate_reused':proof.get('adoption') is not None})
        rows.append({'operation':rel,'profile_sha256':profile.sha,
            'profile_schema':profile.spec['schema'],
            'native_manifest_sha256':profile.spec['native_manifest']['sha256'],
            'source_identity_basis':'recorded_bound_native_manifest_not_rehashed_by_exporter',
            'target_sha256':profile.native['identities']['target'],'tool_sha256':profile.native['identities']['tool'],
            'ordinary_batch_count':len(profile.native['batches'])-len(profile.selected),
            'approximate_batch_count':len(profile.selected),'approximate_batches':batches,
            'result_paf':ctx.contract.file_identity(Path(profile.native['output']),relative_to=ctx.work)})
    ctx.verify()
    return rows


def build(ctx):
    import export_routing_provenance as cross_audit
    dependency=ctx.plan['dependencies']['cross_audit']
    if Path(cross_audit.__file__).resolve()!=Path(dependency['path']).resolve():
        raise ValueError('unbound cross audit implementation')
    cross=cross_audit.build_audit(ctx.cross,ctx.base.HERE/'cross-leaf-checkpoints',ctx.contract)
    rows=self_rows(ctx)
    return {'schema':'cgat_incident_q0_cross_self_provenance_v1','complete_within_scope':True,
        'scope':'planned_q0_self_operations_and_explicitly_routed_cross_leaves',
        'certifies_whole_workflow':False,'initial_reference_policy':False,
        'accuracy_claim':'approximate self alignments may lose substantial evidence; not output-equivalent to native',
        'self_plan_sha256':ctx.plan_sha,'implementation_sha256':{k:v['sha256'] for k,v in ctx.plan['dependencies'].items()},
        'self_operation_count':len(rows),'approximate_self_batch_count':sum(r['approximate_batch_count'] for r in rows),
        'self_operations':rows,'cross':cross}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('work','plan','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    with installed(args.plan,role='audit_exporter',caller=__file__):
        from self_profile_context import load_context
        import export_routing_provenance as cross_audit
        ctx=load_context(args.work,args.plan,role='audit_exporter',caller=__file__)
        if args.output.resolve().is_relative_to(ctx.work) or args.output.is_symlink():
            raise ValueError('portable companion must be outside the analysis workspace')
        result=build(ctx);cross_audit.publish(result,args.output,ctx.contract)
    print(json.dumps({'status':'portable_cross_self_audit_written','output':str(args.output),
        'sha256':ctx.contract.sha256_file(args.output),'approximate_self_batch_count':result['approximate_self_batch_count']}),flush=True)
