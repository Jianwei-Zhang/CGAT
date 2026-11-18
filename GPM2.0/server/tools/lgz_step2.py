#!/usr/bin/env python3

"""Run traceable LGZ Step2 from a validated completed Step1 checkpoint."""

from __future__ import annotations

import argparse

try:
    from lgz_core.repair_runtime import (
        DEFAULT_STEP2_MUMMER_SCOPE,
        MUMMER_SCOPES,
        add_common_cli_arguments,
        validate_common_cli_arguments,
        REFILL_MAX_LENGTH,
        fail,
    )
    from lgz_core.step2_engine import execute_step2
except ModuleNotFoundError:  # Imported as server.tools.grt_step2.
    from .lgz_core.repair_runtime import (
        DEFAULT_STEP2_MUMMER_SCOPE,
        MUMMER_SCOPES,
        add_common_cli_arguments,
        validate_common_cli_arguments,
        REFILL_MAX_LENGTH,
        fail,
    )
    from .lgz_core.step2_engine import execute_step2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_cli_arguments(parser)
    parser.add_argument(
        "--max-fill",
        "-m",
        dest="refill_max_length",
        type=int,
        default=REFILL_MAX_LENGTH,
        help="Maximum Step2 optimized refill length in bp (default: 1000000)",
    )
    parser.add_argument(
        "--step2-mummer-scope",
        choices=sorted(MUMMER_SCOPES),
        default=DEFAULT_STEP2_MUMMER_SCOPE,
        help=(
            "Step2 MUMmer scope: full keeps the established path; gap-screen "
            "screens local gap windows and reruns selected partitions against "
            "the complete Q1 chromosome (default: gap-screen; full preserves the complete alignment scope)"
        ),
    )
    args = parser.parse_args()
    validate_common_cli_arguments(args)
    if args.refill_max_length < 1:
        fail("max-fill must be a positive integer")
    execute_step2(args)


if __name__ == "__main__":
    main()
