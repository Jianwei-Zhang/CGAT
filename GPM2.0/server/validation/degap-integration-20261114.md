# App / DEGAP integration validation — 2026-11-14

Scope: feature branch `feat/app-degap-integration-20261113`, based on `abb748c`.
No merge to master, published Release, updater-feed change or customer input.
DEGAP source is pinned to `0b3c9bc7acc5bd290ad2b23d53cc57815f1c7e75`.

## Evidence

- Conda solves succeeded for both linux-64 and linux-aarch64. The shared environment
  retains Python 3.11.14, minimap2 2.31 and samtools 1.23.1. Selected package
  versions/platforms are recorded in the companion JSON.
- A real installer run plus `install.sh --check` succeeded in an isolated
  `MAMBA_ROOT_PREFIX`, creating one named `cgat-server` environment, verifying
  16 commands, Python imports and the bundled DEGAP entrypoint. Existing user
  environments were not modified.
- The pinned upstream DEGAP test suite passed (37 tests) in the shared x86_64
  dependency environment. Real GapFiller and zero-round TelSeeker smoke runs
  succeeded. A pre-existing upstream zero-round GapFiller crash is rejected by
  the wrapper with an actionable message; the generated upstream code is unchanged.
- The reproducible real roundtrip used generated 24 kb reference/reads, two
  10 kb primary contigs separated by a 4 kb gap, and one support contig. It ran
  the actual GPM pipeline, Windows native import/initialization/export, Linux
  DEGAP/shared preparation/result packaging, and Windows native result import.
  The returned candidate exactly equals the reference; Final Path remains
  byte-equivalent in the project database; the original task association persists.
  Reimport is rejected without adding another source sequence.
- Contract tests cover stale/foreign export receipts, modified source objects
  and Final Path, corrupt package hashes, duplicate imports, cancellation,
  batch rollback after a first candidate has mutated state, stale output FASTA,
  failed TelSeeker status, ambiguous candidates, publication rollback, nested
  runtime copying and update rollback.
- Windows-host frontend tests passed (3,083), as did backend tests (342 passed,
  6 ignored), updater/progress regressions (102), frontend production build and
  backend/Tauri Clippy checks. No browser or native-window UI acceptance is claimed.

## Reproduction

From the repository root, inside the shared `cgat-server` environment, with a
freshly built backend CLI and a **new** output directory:

```bash
python GPM2.0/scripts/sync-degap-runtime.py --check
python GPM2.0/scripts/validate-degap-roundtrip.py \
  --backend /path/to/gpm_next_backend \
  --work-root /new/empty-parent/degap-roundtrip
```

For WSL plus a Windows-host backend, `--backend` may point to
`GPM2.0/app/backend/target/debug/gpm_next_backend.exe`. The validator translates
paths using `wslpath`; it never builds with WSL Cargo or opens a browser. It
refuses an existing output root and writes logs plus `acceptance.json` there.

Dependency-only ARM64 verification does **not** establish ARM64 runtime or
customer-data acceptance. Feature availability in a public release requires a
separate reviewed release; this branch does not replace published Server assets.
