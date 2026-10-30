#!/usr/bin/env python3

"""Run traceable LGZ Step3 from a validated completed Step2 checkpoint."""

from __future__ import annotations

import argparse

try:
    from grt_core.repair_runtime import (
        DEFAULT_STEP3_MUMMER_SCOPE,
        MUMMER_SCOPES,
        add_common_cli_arguments,
        validate_common_cli_arguments,
        REFILL_MAX_LENGTH,
        fail,
    )
    from grt_core.step3_engine import execute_step3
except ModuleNotFoundError:  # Imported as server.tools.grt_step3.
    from .grt_core.repair_runtime import (
        DEFAULT_STEP3_MUMMER_SCOPE,
        MUMMER_SCOPES,
        add_common_cli_arguments,
        validate_common_cli_arguments,
        REFILL_MAX_LENGTH,
        fail,
    )
    from .grt_core.step3_engine import execute_step3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_cli_arguments(parser)
    parser.add_argument(
        "--max-fill",
        "-m",
        dest="refill_max_length",
        type=int,
        default=REFILL_MAX_LENGTH,
        help="Maximum Step3 optimized refill length in bp (default: 1000000)",
    )
    parser.add_argument(
        "--step3-mummer-scope",
        choices=sorted(MUMMER_SCOPES),
        default=DEFAULT_STEP3_MUMMER_SCOPE,
        help=(
            "Step3 MUMmer scope: full keeps the established path; gap-screen "
            "screens local gap windows and reruns selected partitions against "
            "the complete Q2 chromosome (default: gap-screen; full preserves the complete alignment scope)"
        ),
    )
    args = parser.parse_args()
    validate_common_cli_arguments(args)
    if args.refill_max_length < 1:
        fail("max-fill must be a positive integer")
    execute_step3(args)


if __name__ == "__main__":
    main()
