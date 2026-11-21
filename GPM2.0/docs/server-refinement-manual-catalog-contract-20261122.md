# Manual DEGAP candidates in numbered workspaces

Date: 2026-11-22. Implementation contract; not a claim of completed App/Server acceptance.

The automatic four-engine branches and manual App `DEGAP-JOBS` must not share a mutable scientific baseline. Merely changing `server/metadata` to `.runtime/metadata` in the old collector would mutate source tables covered by the original LGZ proof and migrated-baseline receipt. The new collector therefore keeps the original numbered workspace's LGZ metadata, input sequences, Final Path and published refinement results unchanged.

For layout 2, manual collection builds a versioned candidate catalog under `04_refinement/01_degap/06_manual/01_catalog/<generation>/`. This is an isolated numbered staging view with copied mutable metadata, immutable original input links, candidate source sequences and their real incremental alignments. Subsequent collections inherit that catalog, not by appending to the main LGZ tables. Candidate packages keep the existing portable incremental App protocol and original export receipts; they do not change an App project's Final Path on import.

A sealed catalog binds its base-table identities, full file/link inventory and immutable per-token package registry. Original immutable FASTA links are hashed once per unchanged file identity in a process (device, inode, length, mtime and ctime), with before/after checks; this content cache is never persisted and cannot treat restored mtime as proof after a write. `.runtime/manual_degap/current.json` is the authoritative catalog pointer. A directory or token-named ZIP alone is never completion evidence. Different current base tables, changed candidate files/links/packages or an unfinished publication must not be silently accepted.

Catalogs and package caches are immutable after sealing. The result ZIP at the explicitly exported job directory and catalog pointer are published under the outer workspace lock with a content-bound pending plan and recoverable prior bytes. A later invocation resolves a pending atomic-file exchange before collection, finishing a fully verified new set or restoring the still-owned old one, never overwriting unknown changed files. Recollection uses verified cached packages without repeating their alignments. Legacy layout keeps its existing metadata publication behavior. Collection rechecks the native result receipt, collected candidate snapshot and immutable alignment inputs after staging; a changed input cannot be mixed into a published catalog.

The App export side must independently resolve the numbered/legacy runtime and actual original/refined/manual source catalog rather than assuming portable App paths are Server filesystem paths. Adoption of pre-migration manual package caches also needs an explicit verified adapter, not a bare token-file cache hit. The source/runtime identity work is now specified and implemented in `server-refinement-manual-source-contract-20261122.md`; the historical cache adapter below is also implemented. Their controlled checks do not replace final native/App acceptance. Final checks must include preserved original LGZ proof, incremental candidate source continuity, failure/interruption recovery, both layout versions and the real App importer.

中文要点：编号工作区的人工候选使用独立、版本化来源目录，不追加主 LGZ metadata，不改变原始基线或自动精修 Final Path。内容绑定的候选目录、包缓存和发布指针可恢复；旧布局保持原语义。App 的运行库/种子来源路径必须联动适配，不能只把字符串路径改名就宣称全链路完成。


## Original integration findings and current source status

- App export previously hardcoded legacy runtime and portable seed FASTA paths. The source identity/runtime contract now replaces that execution assumption for both layouts and Full/Light sources; a declared broken/pending numbered runtime cannot fall back across migration.
- `build_degap_receipt()` previously used the source dataset as target track except for `derived_ctg`. Export now uses the actual derived placement or an explicitly context-only real project primary track, keeping the source dataset and homology evidence separate.
- Original manual caches moved to `.runtime/run_all/degap_packages` now have the migration-bound adoption adapter below. Controlled migration/installed-collector checks verify original package reuse, source continuity and unchanged original LGZ proof without rerunning completed native work/alignments. Unknown external result ZIPs remain protected.

These were required integration boundaries, not optional polish. Their source implementation and controlled checks do not claim final four-engine/native environment or complete App acceptance.


## Pre-migration package adoption adapter

A committed completed-LGZ migration can carry original `.run_all/degap_packages/<token>.{json,zip}` into `.runtime/run_all/degap_packages/`. These files remain historical inputs, never a fallback cache for a fresh numbered project. On the first requested reuse, a dedicated adapter must:

1. Require the verified original-engine migration baseline and the committed inventory mapping, then verify the selected old cache files against their original unchanged migration identities. Unregistered post-migration files, missing partners and changed bytes fail rather than causing re-alignment of an already existing candidate name.
2. Match the exact original recipe/token, current native receipt/candidate hash, seed/runtime/source proof (when present), canonical candidate name and immutable package bytes. Check the historical incremental manifest/source locator and the actual already-published candidate sequence represented in the migrated source catalog. Retain historical package bytes and provenance; do not relabel them as a new native run.
3. Copy the verified archive/info into the new immutable catalog registry and record migration/cache adoption evidence. Reuse does not run native work or the candidate alignments and does not rewrite original LGZ tables or the historical cache. New candidates in the same batch still follow normal isolated staging.
4. Recheck consumed historical cache/source bindings before sealing, then use the existing recoverable catalog/output publication. A cache adoption is not permission to replace an unknown result ZIP outside the migration inventory or current publication receipt. Preserve such ZIPs and collect using a fresh export folder containing the unchanged original `jobs.tsv` and `degap_jobs/` receipts; do not re-export a new token or edit original recipes simply to force reuse.

If a completed original cache is absent from the migration inventory, the adapter must not manufacture its authority from a token filename, candidate presence, mtime or a ZIP's apparent structure. This is a scoped source/package adapter, not a general loose-cache recovery mechanism.

中文：旧候选仅在已提交且原 LGZ 证明有效的迁移中，经迁移文件清单、原任务/消费内容/原包共同核对后纳入新的不可变 registry；不重跑原生任务或已完成比对，不修改旧缓存/主 LGZ 元数据。未登记、缺失或变化的缓存拒绝接纳；未知旧结果 ZIP 不自动覆盖，可复制未改动的原 jobs/receipt 到新的空目录收集，保留原导入身份。
