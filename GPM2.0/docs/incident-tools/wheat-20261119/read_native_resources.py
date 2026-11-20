"""Use the authentic scientific evidence reader with explicit resource bindings."""
import argparse
from pathlib import Path
import runpy
import sys
from native_resource_bootstrap import installed


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--plan",type=Path,required=True)
    args,rest=p.parse_known_args();old=list(sys.argv)
    try:
        with installed(args.plan,role="native_reader",caller=__file__) as plan:
            sys.argv=[plan["dependencies"]["reader"]["path"],"--plan",str(args.plan),*rest]
            runpy.run_path(sys.argv[0],run_name="__main__")
    finally:sys.argv[:]=old


if __name__=="__main__":main()
