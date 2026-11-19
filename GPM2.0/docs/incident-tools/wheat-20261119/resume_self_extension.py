"""Own the original workflow through an explicit composite self profile layer."""
import argparse
import runpy
import sys
from pathlib import Path
from self_extension_context import installed


def execute(plan_path,*,validate_only=False,install_reader=False):
    old=list(sys.argv)
    try:
        with installed(plan_path,role='extension_entry',caller=__file__) as plan:
            if validate_only:
                from self_profile_context import load_context
                import self_profile_admission as admission
                ctx=load_context(Path(plan['workspace']),plan_path,role='entry',caller=plan['dependencies']['entry']['path'])
                admission.SelfDispatcher(ctx.selfs,ctx.base.TwoMappingDispatcher().exclusive,
                                         max_fast=plan['resource_policy']['max_fast'])
            sys.argv=[plan['dependencies']['entry']['path'],'--plan',str(plan_path)]
            if validate_only:sys.argv.append('--validate-only')
            if install_reader:sys.argv.append('--install-reader')
            runpy.run_path(sys.argv[0],run_name='__main__')
    finally:sys.argv[:]=old


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--validate-only',action='store_true');parser.add_argument('--install-reader',action='store_true')
    args=parser.parse_args();execute(args.plan,validate_only=args.validate_only,install_reader=args.install_reader)
