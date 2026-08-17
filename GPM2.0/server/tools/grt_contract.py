#!/usr/bin/env python3

"""CLI-compatible facade for the modular GRT v2 contract validator."""

import argparse
import json
import sys
from pathlib import Path

try:
    from grt_core.contract import ContractError, DEFAULT_SCHEMA_PATH, validate_contract
except ModuleNotFoundError:  # Imported as server.tools.grt_contract in repository tests.
    from .grt_core.contract import ContractError, DEFAULT_SCHEMA_PATH, validate_contract

def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a GPM GRT precomputed package contract")
    parser.add_argument("--bundle", required=True, type=Path, help="Path to the gpm_server bundle root")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    args = parser.parse_args(argv)
    try:
        summary = validate_contract(args.bundle, args.schema)
    except ContractError as exc:
        print(f"ERROR {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
