# TODO: CGAT Conda package

Status: deferred until the prerequisite App and Server workflows are stable.

## Future package boundary

- Provide one user-facing Conda installation unit containing the GPM Server toolset and DEGAP v2.
- Expose a stable `cgat` command so users do not need to locate or invoke repository-internal shell scripts.
- Keep the desktop App outside the server Conda package and integrate through finalized artifact and parameter contracts.

## Proposed dependency baseline

- Python 3.11
- minimap2 2.31
- samtools 1.23.1

DEGAP v2 is expected to be compatible with this baseline, but compatibility is not yet verified. Focused smoke tests must pass before the project claims or publishes support.

## Prerequisites

Complete or explicitly stabilize these workflows before resuming packaging:

1. App import of add-dataset update packages.
2. App import of add-contig update packages.
3. DEGAP job creation and export, especially the complete parameter contract.

## Work to resume later

- Finalize the public channel and package namespace.
- Finalize the `cgat` subcommand surface against the stabilized workflows.
- Build the Conda recipe and installation diagnostics.
- Test clean-environment installation outside the source checkout.
- Run packaged GPM Server and DEGAP v2 smoke workflows.
- Publish only after the resolved dependency versions and compatibility results are recorded.
