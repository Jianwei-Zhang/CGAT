# Deferred CGAT Conda package TODO

## Target state

This capability is not implemented by the current change. The current change only preserves one tracked backlog TODO and then leaves the active Comet workflow.

The TODO records:

- the proposed shared baseline of Python 3.11, minimap2 2.31, and samtools 1.23.1;
- the future goal of one Conda installation unit containing the GPM Server toolset and DEGAP v2 behind a stable `cgat` command;
- that DEGAP compatibility remains unverified until focused smoke tests pass; and
- that App add-dataset import, App add-contig import, and DEGAP job creation/export parameters must stabilize before packaging resumes.

### Scenario: Preserve the deferred package as one TODO

Given Conda packaging is intentionally postponed, when this change is completed, then `docs/comet/todos/cgat-suite-conda-package.md` is the single backlog-facing record of the future work and no package, App, GPM Server, or DEGAP runtime implementation is changed.
