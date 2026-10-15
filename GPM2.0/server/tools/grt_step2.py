#!/usr/bin/env python3

"""Run traceable GRT Step2 against the frozen Q1 and D0 inputs."""

from __future__ import annotations

import argparse

try:
    from grt_step23 import (
        DEFAULT_MUMMER_SCOPE,
        MUMMER_SCOPES,
        add_common_cli_arguments,
        execute_step2,
        validate_common_cli_arguments,
    )
except ModuleNotFoundError:  # Imported as server.tools.grt_step2.
    from .grt_step23 import (
        DEFAULT_MUMMER_SCOPE,
        MUMMER_SCOPES,
        add_common_cli_arguments,
        execute_step2,
        validate_common_cli_arguments,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_cli_arguments(parser)
    parser.add_argument(
        "--step2-mummer-scope",
        choices=sorted(MUMMER_SCOPES),
        default=DEFAULT_MUMMER_SCOPE,
        help=(
            "Step2 MUMmer scope: full keeps the established path; gap-screen "
            "screens local gap windows and reruns selected partitions against "
            "the complete Q1 chromosome (experimental, default: full)"
        ),
    )
    args = parser.parse_args()
    validate_common_cli_arguments(args)
    execute_step2(args)


if __name__ == "__main__":
    main()
