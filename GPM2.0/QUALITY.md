# Quality gates

GPM2.0 uses repository-owned scripts as the shared quality contract for local
development, pull requests, `master`, and installer releases. The scripts fail
on the first broken command and never install dependencies or modify fixtures.

## Canonical commands

Run the desktop and Rust gate on a Windows host from the project root:

```powershell
pwsh -NoLogo -NoProfile -File scripts/quality-gate-windows.ps1
```

From WSL, the same host-side gate can be launched with PowerShell 7:

```bash
'/mnt/c/Program Files/PowerShell/7/pwsh.exe' \
  -NoLogo -NoProfile \
  -File "$(wslpath -w "$PWD/scripts/quality-gate-windows.ps1")"
```

Run the server gate on Linux:

```bash
bash scripts/quality-gate-server.sh
```

The Windows gate checks tracked LF line endings, all frontend tests, the
frontend production build, and formatting, strict Clippy, and tests for both
Rust crates. The Linux gate checks tracked LF line endings, shell syntax, all
server Python tests, the focused server shell tests, and the GRT server-to-app
end-to-end contract.

The complete Windows gate requires `python`, Node.js/npm, Rust, `rustfmt`, and
`clippy`. The complete Linux gate requires `python3`, Bash, Node.js, Rust, and
`zip`. Install frontend dependencies with `npm ci` before the Windows gate.
The focused shell tests provide their own fake bioinformatics commands; the
real alignment toolchain is not required for quality verification.

When working in WSL, where Rust verification is intentionally delegated to the
Windows host, the server-only checks can be run without the Rust-backed GRT E2E:

```bash
GPM_SKIP_GRT_SERVER_APP_E2E=1 bash scripts/quality-gate-server.sh
```

That override prints a visible `SKIP` warning and represents an incomplete
local gate. CI and release verification never set it.

## Focused diagnosis

Use the failing group name to rerun only the relevant command:

```bash
# All 59 frontend test files (809 tests at gate introduction)
cd app/frontend && npm test

# Server Python suite (80 tests at gate introduction)
python3 -m unittest discover -s server/tests -p 'test_*.py'

# Read-only LF validation for tracked GPM2.0 text files
python3 scripts/check_line_endings.py
```

On Windows, the Rust commands used by the gate are:

```powershell
cd app/backend
cargo fmt --all -- --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --locked

cd ../src-tauri
cargo fmt --all -- --check
cargo clippy --all-targets --locked --no-default-features -- -D warnings
cargo test --locked --no-default-features
```

The baseline when this gate was introduced was 116 backend Rust tests and 7
Tauri Rust tests. Test counts may grow; the gate discovers the full suites
rather than pinning those counts.

## App import performance probes

Run these opt-in probes on the Windows host from `app/backend`:

```powershell
cargo test --lib benchmark_q4_validation -- --ignored --nocapture
cargo test --lib benchmark_pairwise_query_indexes -- --ignored --nocapture
# Optional: validate an existing q4 read-only instead of generating synthetic data.
$env:GPM_IMPORT_BENCH_Q4 = 'D:\path\to\project\grt\q\q4.fa'
cargo test --lib benchmark_q4_validation -- --ignored --nocapture
Remove-Item Env:GPM_IMPORT_BENCH_Q4
# Optional: copy index columns from a read-only existing database.
$env:GPM_IMPORT_BENCH_DB = 'D:\path\to\project\project.sqlite'
cargo test --lib benchmark_pairwise_query_indexes -- --ignored --nocapture
Remove-Item Env:GPM_IMPORT_BENCH_DB
```

The q4 probe compares retained records with streaming summaries and asserts
identical artifact/chromosome hashes and lengths. App import retains only
summaries; source-reconstruction callers still retain records. Both paths use
the same FASTA validation and cancellation checks. The summary reader's memory
depends on chromosome count and the longest FASTA line, not the total wrapped
genome sequence.
Normalized chromosome bases are hashed in 64 KiB batches rather than one short
FASTA line per digest call. The SQLite probe uses disposable databases to compare
two legacy five-column indexes with one four-column index, verifies equivalent
forward/reverse multi-id lookup results/plans, and checks database integrity.
Both directions constrain run id and both sequence ids; the reverse permutation
is redundant, and mapq is selected but not a lookup predicate. Existing current-
version databases are not rewritten on open; new imports use the compact index.
Transactions, durability settings, and SQLite's default worker policy are unchanged.
Debug profiles optimize SHA-256/SQLite and use opt-level 2 for backend data loops
in both Cargo roots, retaining debug symbols and an unoptimized Tauri/UI crate.

`cache/import.log` appends monotonic `elapsed_ms` to each step. Root resolution,
per-entry directory promotion (rename, not payload copy), index creation, and
transaction commit are distinct events. Compare equivalent inputs/build modes;
cache and antivirus state affect timings. These probes are not full import or
native-UI acceptance tests.

## CI and releases

`.github/workflows/quality.yml` runs the same scripts for pull requests and
pushes to `master`. `Release installers` calls the reusable quality workflow
before creating a release or building any installer, so packaging cannot bypass
the gate. Generated frontend `dist/`, Rust `target/`, temporary test workspaces,
and other build products remain ignored and must not be committed.
