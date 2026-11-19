"""Run the original combined reader with the same explicit composite factory."""
import argparse
from pathlib import Path
import runpy
import sys
from self_extension_context import installed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    args,rest=parser.parse_known_args();old=list(sys.argv)
    try:
        with installed(args.plan,role='extension_reader',caller=__file__) as plan:
            sys.argv=[plan['dependencies']['reader']['path'],'--plan',str(args.plan),*rest]
            runpy.run_path(sys.argv[0],run_name='__main__')
    finally:sys.argv[:]=old


if __name__=='__main__':main()
