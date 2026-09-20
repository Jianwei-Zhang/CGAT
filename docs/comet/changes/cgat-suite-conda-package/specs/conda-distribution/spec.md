# CGAT Conda distribution

## Purpose

The completed capability provides one Conda-installable CGAT server suite containing the GPM Server toolset and DEGAP v2. Installation must not require users to discover the repository's `server` directory or invoke internal setup scripts directly.

## Distribution contract

- The initial supported target is a Linux server environment.
- The initial shared runtime baseline is Python 3.11, minimap2 2.31, and samtools 1.23.1.
- The installation exposes a stable `cgat` executable on `PATH`.
- GPM Server and DEGAP v2 code required by supported workflows is installed inside the environment rather than read from a source checkout.
- Third-party programs are declared as package dependencies and are not silently downloaded by normal workflow commands.
- Installation diagnostics identify missing or incompatible runtime tools and return a non-zero status on failure.

## Workflow contract

- User-facing commands describe workflow intent and do not require knowledge of `env.sh`, `prepare.sh`, `run_all.sh`, `add_dataset.sh`, `add_ctg.sh`, or `export_final_path_fasta.sh` locations.
- The final command surface follows the stabilized App add-dataset, add-contig, and DEGAP job parameter contracts.
- Human-readable output states whether an operation succeeded, where its result was written, and the next relevant action.
- A machine-readable result mode is available for future App orchestration without parsing human terminal text.
- Existing scientific inputs and outputs remain compatible unless a separately confirmed workflow change explicitly replaces them.

## Compatibility validation

### Scenario: Install the complete server suite

Given a supported Linux host with a Conda-compatible package manager, when the user installs the CGAT server suite into a clean environment, then the solver completes without requiring a source checkout and the `cgat` executable is available on `PATH`.

### Scenario: Diagnose the installed environment

Given the package is installed, when the user runs the installation check, then the command verifies required runtime programs, reports their resolved versions and paths, and exits successfully only when the supported environment is complete.

### Scenario: Run a packaged GPM Server smoke workflow

Given small valid reference and dataset fixtures, when the packaged GPM Server workflow is executed from outside the repository, then it completes using only installed package resources and produces a valid delivery artifact.

### Scenario: Validate DEGAP v2 on the shared baseline

Given representative minimal DEGAP fixtures, when DEGAP v2 is run under Python 3.11 with minimap2 2.31 and samtools 1.23.1, then the selected smoke workflows complete successfully and produce structurally valid expected outputs.

### Scenario: Reject an unverified compatibility claim

Given one or more required DEGAP smoke workflows have not passed on the shared baseline, when release readiness is evaluated, then the package is not described or published as compatible with that baseline.

### Scenario: Follow the finalized App and job contracts

Given the prerequisite add-dataset import, add-contig import, and DEGAP job parameter contracts have stabilized, when the package command interface is finalized, then its accepted parameters and produced artifacts match those contracts without requiring users to manually translate internal package types or script arguments.
