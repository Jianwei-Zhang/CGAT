#!/usr/bin/env python3
"""Prepare validated global, chr-local and supplementary q0 alignment evidence."""
from __future__ import annotations
import argparse
from pathlib import Path
try:
    from lgz_core.q0_preparation import prepare_evidence
    from lgz_core.q0_sources import Q0EvidenceError
    from run_resources import execution_threads
    from run_orchestration import OrchestrationContractError
except ModuleNotFoundError:
    from .lgz_core.q0_preparation import prepare_evidence
    from .lgz_core.q0_sources import Q0EvidenceError
    from .run_resources import execution_threads
    from .run_orchestration import OrchestrationContractError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--supplement-scope", choices=("full", "decision_frontier"), default="full",
                        help="experimental lossy regional window scope; default retains full evidence search")
    args = parser.parse_args()
    try:
        prepare_evidence(args.server_dir, threads=execution_threads(args.threads), minimap2=args.minimap2,
                         supplement_scope=args.supplement_scope)
    except (OSError, ValueError, Q0EvidenceError, OrchestrationContractError) as exc:
        parser.exit(1, f"q0 evidence preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
