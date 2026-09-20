# Outcome

Retire this deferred Conda packaging work from the active Comet change list and preserve its essential decisions as one ordinary tracked TODO.

# Scope

- Create `docs/comet/todos/cgat-suite-conda-package.md` as the single future-work record.
- Preserve the proposed dependency baseline: Python 3.11, minimap2 2.31, and samtools 1.23.1.
- Preserve the intended future product boundary: one Conda installation unit containing the GPM Server toolset and DEGAP v2 behind a stable `cgat` command.
- Preserve the requirement to run focused DEGAP compatibility smoke tests before claiming support.
- Preserve the prerequisites that must stabilize first: App add-dataset package import, App add-contig package import, and DEGAP job creation/export with its complete parameter contract.
- Archive this Native change after the TODO is verified so it no longer occupies an active workflow slot.

# Non-goals

- Do not implement, build, publish, or test the Conda package.
- Do not change App, GPM Server, or DEGAP runtime behavior.
- Do not finalize the channel name, package namespace, or `cgat` subcommand surface.
- Do not keep a complete active specification for work that is intentionally postponed.

# Acceptance examples

- A1: One tracked TODO at `docs/comet/todos/cgat-suite-conda-package.md` records the future package boundary, proposed dependency baseline, required DEGAP compatibility test, and the three prerequisite workflow areas; the Native change can then be archived without implementing the package.

# Constraints and invariants

- The TODO must clearly distinguish proposed decisions from verified compatibility results.
- DEGAP compatibility with Python 3.11, minimap2 2.31, and samtools 1.23.1 remains unverified until future smoke tests pass.
- The TODO is a backlog record, not an active implementation specification or compatibility promise.

# Decisions

- 2026-09-20: Adopt Python 3.11, minimap2 2.31, and samtools 1.23.1 as the proposed common baseline.
- 2026-09-20: Verify DEGAP on that baseline with focused smoke tests when implementation resumes.
- 2026-09-20: Defer the Conda packaging change until the App incremental imports and DEGAP job parameter workflow are improved.
- 2026-09-20: Replace the active deferred Native change with one ordinary TODO so prerequisite work can proceed independently.

# Open questions

None. Channel naming, the final package namespace, and the complete CLI surface remain future TODO decisions.

# Verification expectations

- Confirm the TODO exists at the agreed path and is tracked by Git.
- Confirm it contains the package boundary, proposed dependency baseline, compatibility caveat, and prerequisite workflow list.
- Confirm no package or runtime source code changes are included.
