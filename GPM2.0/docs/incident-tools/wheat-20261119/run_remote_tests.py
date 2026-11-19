"""Run the incident tests against an explicit frozen tools directory.

A flat remote incident bundle does not have the repository's ../../../server
layout. Bind the existing cross-router fixture TOOLS constant to the explicit
runtime under test; do not edit test sources or alter assertions/test selection.
Run through the scheduler, never on the login node.
"""
import argparse
from pathlib import Path
import sys
import unittest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests',type=Path,required=True)
    parser.add_argument('--tools',type=Path,required=True)
    args=parser.parse_args();tests=args.tests.resolve(strict=True);tools=args.tools.resolve(strict=True)
    for name in ('run_orchestration.py','self_alignment_batches.py'):
        if not (tools/name).is_file():raise ValueError('incomplete explicit test tools directory')
    sys.path[:0]=[str(tests),str(tools)]
    import test_long_query_cross_router as cross_tests
    cross_tests.TOOLS=tools
    print('REMOTE_TEST_FIXTURE_TOOLS',tools,flush=True)
    suite=unittest.defaultTestLoader.discover(str(tests),pattern='test_*.py',top_level_dir=str(tests))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
