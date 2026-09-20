# Outcome

Provide a future Conda-distributed CGAT server suite that users can install as one product and operate through a stable `cgat` command, without locating or invoking repository-internal shell scripts. The distribution includes the GPM Server toolset and DEGAP v2.

# Scope

- Package the GPM Server runtime tools and DEGAP v2 as one user-facing Conda installation unit.
- Use Python 3.11, minimap2 2.31, and samtools 1.23.1 as the initial shared dependency baseline.
- Add focused DEGAP compatibility smoke tests against that baseline before declaring it supported.
- Provide installation diagnostics and a clear success/failure result after installation.
- Define the final command and artifact interfaces only after the prerequisite App/Server workflows have stabilized.
- Document installation with Conda-compatible managers, including mamba and micromamba.

This change is intentionally deferred in Shape. Work should resume only after the prerequisite workflows below have been completed or their contracts have been explicitly stabilized:

1. App import of add-dataset update packages.
2. App import of add-contig update packages.
3. DEGAP job creation and export, especially the complete parameter contract.

# Non-goals

- Do not build, publish, or test the Conda package as part of the current workflow pass.
- Do not change the current App import/export implementation under this deferred change.
- Do not finalize the public channel, package namespace, or complete `cgat` subcommand surface before the prerequisite workflows stabilize.
- Do not include the desktop App itself in the server Conda package.
- Do not claim DEGAP compatibility with the shared dependency baseline until the smoke tests have actually passed.

# Acceptance examples

The complete acceptance scenarios for the future implementation are defined in `specs/conda-distribution/spec.md`. No acceptance run is authorized while this change remains deferred in Shape.

# Constraints and invariants

- The initial dependency baseline is Python 3.11, minimap2 2.31, and samtools 1.23.1.
- DEGAP compatibility with the baseline is a working expectation, not yet a verified result.
- Users install one CGAT server suite even if the recipe resolves multiple third-party dependencies internally.
- Existing GPM Server and DEGAP outputs must remain scientifically equivalent after packaging.
- The future CLI must wrap stable workflow intent rather than expose repository layout or generated script names.
- The package and CLI contract must follow the final App add-dataset, add-contig, and DEGAP job parameter contracts instead of freezing their current intermediate forms.
- Linux server deployment is the initial packaging target unless the future Shape explicitly expands platform scope.

# Decisions

- 2026-09-20: Adopt Python 3.11, minimap2 2.31, and samtools 1.23.1 as the proposed common baseline.
- 2026-09-20: Verify DEGAP on that baseline with focused smoke tests when implementation resumes.
- 2026-09-20: Defer the Conda packaging change until the App incremental imports and DEGAP job parameter workflow are improved.
- 2026-09-20: Keep this work as a separate Comet Native change rather than mixing it into the prerequisite workflow changes.

# Open questions

None requires a decision while the change is deferred. Channel naming, the final package namespace, and the complete CLI surface will be revisited when the prerequisite workflow contracts are stable.

# Verification expectations

- Solve and create a clean Conda environment from the future recipe.
- Verify the installed `cgat` entry point and installation diagnostics from outside the source checkout.
- Run a minimal GPM Server smoke workflow using packaged files only.
- Run representative DEGAP v2 smoke cases under Python 3.11, minimap2 2.31, and samtools 1.23.1.
- Confirm the packaged command consumes and produces the finalized App/Server artifact contracts.
- Record exact resolved dependency versions and test outputs before publishing.
