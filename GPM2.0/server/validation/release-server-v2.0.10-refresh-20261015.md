# v2.0.10 Server source asset refresh — 2026-10-15

## Scope and provenance

At the user's request, the existing official Release `v2.0.10` Server source
attachment was replaced without changing the app version or moving its tag.
The replacement exports the tracked Server subtree from
`3250731e921095721dcdf8d9ad229ad10fe96cd6` and adds only `SOURCE.json` provenance.
This receipt is recorded after publication and is not part of that frozen export.

The published source includes the official `gpm-server` skill v3, its pinned
version-check/update-staging helpers, and the corrected workspace-derived
archive-root reminder. The skill now explicitly distinguishes an analysis
failure from a task-local post-run verification failure and prescribes
verification-only recovery without rerunning successful analysis or relabeling
an original failed scheduler job.

Source packages retain the `GPM_Server/` root. Analysis delivery archives instead
use their actual workspace basename: the custom `run01` regression covers both
ZIP and tar.gz behavior and the preparation reminder. No biological parameters,
input files or desktop runtime code were changed by this fix.

## Published artifact

| Field | Verified value |
| --- | --- |
| Release ID | `410753956` |
| Release tag/title | `v2.0.10` / `GPM v2.0.10` |
| Replacement asset ID | `641019824` |
| Filename | `GPM_Server_2.0.10_source.tar.gz` |
| Bytes | `337710` |
| SHA-256 | `f45fd47c55b9fe9588f5aae452c73993a6190ce515d86f263d67af51bf3c2669` |
| Tracked source files / regular files / tar members | 113 / 114 / 129 |
| Previous asset ID | `636332952` |
| Previous SHA-256 | `28cf865759cf62928967390ea41048d321334deca6021ff2942d12ef7227c677` |
| Pinned quality run | `38601297008` |

## Verification

- All 113 exported tracked source files match the pinned Git revision
  byte-for-byte. The only additional file is `SOURCE.json`, recording the source
  revision/tree, release, skill version, build timestamp and exact quality run.
- Source archive gzip CRC, all tar members, safe paths, absence of links/special
  members, and file hashes were checked before publishing and against a fresh
  download from the unchanged public Release download URL.
- The local upload, public download and GitHub API digest/size agree.
- The publicly downloaded package was freshly extracted. `run.sh --help` works;
  the bundled `../..` skill binding resolves to that extracted Server, and
  **49 skill fixture/binding/update tests pass** against the downloaded files.
- Local focused checks passed: 5 delivery archive tests (including custom-root
  ZIP/tar.gz coverage), 49 skill tests, the preparation shell regression and
  tracked LF checks. The task-local corrected verifier also passed 8 bounded
  checks covering custom roots, Full/Light contents, report status, traversal,
  SHA mismatch and gzip trailer corruption.
- Exact-revision Quality CI `38601297008` completed successfully for
  Linux Server and Windows App. The canonical Linux gate passed **205 Python
  tests**, all Server shell regressions and Server-to-App fixture E2E. This was
  ordinary push quality, not a new installer build or Full Tauri validation.

## Preserved contents and rollback

The Release still has six approved attachments. The four desktop installers and
`test_data.zip` retain their asset IDs, sizes, digests and timestamps. Release
ID, title, tag object, target commit and original publication time are unchanged.
A refresh bullet was added to each existing language section; complete English
still precedes Chinese and both macOS first-launch sections remain intact.

The previous Server archive and before/after Release/tag metadata were retained
locally for rollback. No backup asset, raw sequences or private task outputs were
uploaded to the public Release.

The local project `AGENTS.md` now requires Release refresh plus public-download
verification when closing published Server/skill changes. The tracked
`RELEASING.md` contains the same Server-only closure procedure.

## Evidence boundary

No new desktop installers were built, and no new native visual acceptance or
actual import of the user's biological delivery was performed. Fixture E2E and
source-package checks do not establish independent biological quality gains.
The user's existing analysis archives were verified separately without rerunning
or rebuilding them; their results and private receipts remain in the remote task.
