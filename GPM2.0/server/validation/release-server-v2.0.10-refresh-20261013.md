# v2.0.10 Server source asset refresh — 2026-10-13

## Scope and provenance

The existing `GPM_Server_2.0.10_source.tar.gz` attachment on official Release
`v2.0.10` was replaced at the user's request. The previous archive omitted the
entire official agent skill. The replacement exports the tracked Server subtree
from **05f67d00eef16f41af066d896973b324ebe70b2b** with the same `GPM_Server/` root,
plus `SOURCE.json` recording source revision/tree, release, build time and CI run.
The Release tag was not moved. This is a post-tag Server-asset refresh, not a new
app release. Both existing release-note sections now disclose the refresh.

The bundle includes skill v2 (11 skill files), tools-location binding, local
learning guidance and `stage_skill_update.py`. The subsequently requested default
automatic learning and online-update design was **not yet implemented** and is
not claimed as part of this archive. User-local notes, environments, caches and
untracked working-tree files were not packaged.

## Artifact verification

| Field | Verified value |
| --- | --- |
| Release ID | `410753956` |
| Replacement asset ID | `636332952` |
| Filename | `GPM_Server_2.0.10_source.tar.gz` |
| Bytes | `319644` |
| SHA-256 | `28cf865759cf62928967390ea41048d321334deca6021ff2942d12ef7227c677` |
| Tar members / regular files | 122 / 107 |
| Previous asset ID | `634343649` |
| Previous SHA-256 | `fd6c78482b7df5d388d6f43b7d07c6ccc9da0a817829ed89f12bda5478cc591a` |

- All 106 tracked Server files match the pinned Git revision byte-for-byte; the
  only added file is the explicit `SOURCE.json` provenance record.
- The published API digest, uploaded archive and a fresh download through the
  unchanged public download URL have identical SHA-256. All 107 downloaded file
  hashes match the locally checked package; the downloaded skill declares v2.
- Extracted `run.sh --help` succeeds, and the skill's bundled `../..` binding
  resolves to the extracted Server directory without searching or rebinding.
- The 29 skill fixture/location/update tests pass against the extracted package.
- Source CI **38364792773** passed on the exact pinned revision: Linux server and
  Windows app jobs successful; 184 Server Python tests and Server-to-App E2E pass.
  This is the ordinary push-quality run, not a new installer build or a fresh
  agent-behavior/biological-quality validation.

## Unchanged release contents

The four existing desktop installers and `test_data.zip` retain their original
asset IDs, sizes and digests. The Release still has six attachments. Release
name, tag, target commit and original publication time are unchanged. English
still precedes Chinese, and both macOS first-launch sections remain intact.
The old Server archive and before/after metadata were retained locally for
rollback; no backup or temporary attachment was added to the public Release.
