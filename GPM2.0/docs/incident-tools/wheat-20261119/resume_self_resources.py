"""Execute the SAME frozen self entry with a hash-bound resource-only dispatcher.

No frozen file is rewritten. Module selection is explicit in the overlay plan
and verified before use. Original science profiles, batch keys and cross bindings
remain intact. The original owning entry still acquires/releases the workspace.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import runpy
import sys

import stage_self_resource_resume as staging


def execute(plan_path,*,validate_only=False,install_reader=False):
    plan_path=plan_path.resolve(strict=True);plan=json.loads(plan_path.read_text());deps=plan['dependencies']
    for row in deps.values():
        if staging.digest(row['path'])!=row['sha256']:raise ValueError('resource execution dependency changed')
    if Path(deps['resource_entry']['path']).resolve()!=Path(__file__).resolve():raise ValueError('unbound resource wrapper')
    if Path(deps['resource_stager']['path']).resolve()!=Path(staging.__file__).resolve():raise ValueError('unbound resource verifier')
    origin=json.loads(Path(deps['resource_origin']['path']).read_text());staging.verify_transition(plan,origin)
    old_path=list(sys.path);old_argv=list(sys.argv);old_admission=sys.modules.get('self_profile_admission')
    try:
        sys.path.insert(0,str(Path(deps['entry']['path']).parent))
        sys.path.insert(0,str(Path(plan['workspace'])/'.prepare_lib/tools'))
        spec=importlib.util.spec_from_file_location('self_profile_admission',deps['admission']['path'])
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if plan['resource_policy']['reservation_policy']!=module.POLICY:raise ValueError('resource policy differs from dispatcher')
        sys.modules['self_profile_admission']=module
        if validate_only:
            # Real frozen modules and existing profiles, but no workspace lock or mutation.
            from self_profile_context import load_context
            ctx=load_context(Path(plan['workspace']),plan_path,role='entry',caller=deps['entry']['path'])
            module.SelfDispatcher(ctx.selfs,ctx.base.TwoMappingDispatcher().exclusive,max_fast=plan['resource_policy']['max_fast'])
        sys.argv=[deps['entry']['path'],'--plan',str(plan_path)]
        if validate_only:sys.argv.append('--validate-only')
        if install_reader:sys.argv.append('--install-reader')
        print('RESOURCE_ONLY_SELF_RESUME',json.dumps({'plan_sha256':staging.digest(plan_path),
            'origin_plan_sha256':deps['resource_origin']['sha256'],'max_fast':plan['resource_policy']['max_fast'],
            'process_address_space_limit_bytes':plan['resource_guard']['limit_bytes'],'scientific_profiles_preserved':True}),flush=True)
        runpy.run_path(deps['entry']['path'],run_name='__main__')
    finally:
        sys.path[:]=old_path;sys.argv[:]=old_argv
        if old_admission is None:sys.modules.pop('self_profile_admission',None)
        else:sys.modules['self_profile_admission']=old_admission


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--install-reader',action='store_true');args=parser.parse_args()
    execute(args.plan,validate_only=args.validate_only,install_reader=args.install_reader)
