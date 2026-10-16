# v2.0.10 Server source asset refresh — 2026-10-17

## Scope and provenance

At the user's request, the existing official Release `v2.0.10` Server source
attachment was replaced without changing the app version or moving its tag. The
replacement exports the tracked Server subtree from
`856d5f46c3017b5a86f8a0d40ead6e7314f83534` and adds only `SOURCE.json`
provenance. This receipt is recorded after publication and is not part of that
frozen export.

The published source contains the validated optimized workflow defaults and
execution path: optimized profile, full Step2, gap-screen Step3, self `m200/n100`,
whole-record self-query batching with independent checkpoints, adaptive profiled
alignment scheduling, batched refill and compatible `.mmi` reuse. Step2
gap-screen remains experimental and disabled by default. The bundled
`gpm-server` skill remains v3 and is aligned to companion runtime revision
`76db2c9`.

## Complete-data acceptance

Release-candidate runtime job **40588179** ran the complete customer2665
self-alignment workflow in an isolated ARM32 workspace with 32 CPUs. It ended
`SUCCEEDED` after 31,395.362 seconds and passed **17/17** retained-result checks,
including actual production batching/adaptive profiles, all workflow units,
q2/q3/q4 DNA, complete semantic Final Path, and both delivery packages.

The independent default-full customer suffix initially retained a strict raw
postcheck failure for generated Step3 event/attempt identities. Metadata-only
semantic review job **40590173** resolved the referenced objects and returned
PASS with no core or audit differences. The experimental Step2 gap-screen suffix
retains diagnostic differences and is not promoted by this refresh.

## Published artifact

| Field | Verified value |
| --- | --- |
| Release ID | `410753956` |
| Release tag/title | `v2.0.10` / `GPM v2.0.10` |
| Source commit | `856d5f46c3017b5a86f8a0d40ead6e7314f83534` |
| Source tree | `2faac469a5b71062806fcf498c58ef72efb7dcc9` |
| Quality run | `38951689629` |
| Replacement asset ID | `648314481` |
| Filename | `GPM_Server_2.0.10_source.tar.gz` |
| Bytes | `498285` |
| SHA-256 | `cd3e02d20154de9409895804dea1826114b2c64aa39a7f73e5655afa7dccf478` |
| Tracked source files / regular files / tar members | 163 / 164 / 179 |
| Previous asset ID | `641019824` |
| Previous SHA-256 | `f45fd47c55b9fe9588f5aae452c73993a6190ce515d86f263d67af51bf3c2669` |

## Verification

- Exact-revision Quality CI `38951689629` completed successfully for both Linux
  Server and Windows App. This was ordinary push quality, not a desktop installer
  rebuild.
- Local focused validation passed 121 tests covering adaptive scheduling,
  self-query batching/checkpoints, run orchestration and outer checkpoints,
  refill batching/index reuse, MUMmer parallel execution, self parameters,
  delivery archives and the bundled/official skill update path. The preparation
  metadata shell regression and Server shell syntax also passed.
- All 163 tracked Server files in the archive match the pinned Git tree
  byte-for-byte. The only additional regular file is `SOURCE.json`, recording the
  release, source revision/tree, skill/runtime binding, quality run and complete
  data validation. Git executable classes are preserved.
- Gzip CRC, tar member uniqueness, safe `GPM_Server/` paths, absence of links or
  special members, and complete file-set equality were checked before upload and
  again on a fresh public download.
- The local upload, GitHub API digest/size and public download agree exactly. The
  public SHA-256 is
  `cd3e02d20154de9409895804dea1826114b2c64aa39a7f73e5655afa7dccf478`.
- From a fresh public extraction, `run.sh --help`, all Server shell syntax and the
  skill's relative `../..` tools binding passed. The 49 bundled skill fixture,
  binding, staging and official-update tests passed against the downloaded files.
- Release metadata was re-read after publication. Release ID, title, tag target,
  original publication time, draft/prerelease state and all five other approved
  attachment identities remain unchanged. The Release still contains exactly the
  four installers, this Server source archive and `test_data.zip`.
- One concise October 17 refresh bullet was added to each existing language
  section. Complete English still precedes complete Chinese, and both macOS
  first-launch sections remain present.

## Rollback and evidence boundary

The previous Server archive, before/after Release/API metadata, release bodies,
tag identity, public member lists, checksums and verification reports are retained
locally for rollback. No backup asset, raw sequence, biological delivery archive
or private absolute-path report was uploaded to the public Release.

No new desktop installers were built, the v2.0.10 tag was not moved, and
`test_data.zip` was not changed. The complete-data acceptance establishes
workflow/output semantic equality for this customer dataset; it is not desktop
native visual acceptance and cross-architecture wall times are not an isolated
algorithmic speedup measurement.
