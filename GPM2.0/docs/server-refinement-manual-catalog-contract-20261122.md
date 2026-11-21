# Manual DEGAP candidates in numbered workspaces

Date: 2026-11-22. Implementation contract; not a claim of completed App/Server acceptance.

The automatic four-engine branches and manual App `DEGAP-JOBS` must not share a mutable scientific baseline. Merely changing `server/metadata` to `.runtime/metadata` in the old collector would mutate source tables covered by the original LGZ proof and migrated-baseline receipt. The new collector therefore keeps the original numbered workspace's LGZ metadata, input sequences, Final Path and published refinement results unchanged.

For layout 2, manual collection builds a versioned candidate catalog under `04_refinement/01_degap/06_manual/01_catalog/<generation>/`. This is an isolated numbered staging view with copied mutable metadata, immutable original input links, candidate source sequences and their real incremental alignments. Subsequent collections inherit that catalog, not by appending to the main LGZ tables. Candidate packages keep the existing portable incremental App protocol and original export receipts; they do not change an App project's Final Path on import.

A sealed catalog binds its base-table identities, full file/link inventory and immutable per-token package registry. Original immutable FASTA links are hashed once per unchanged file identity in a process (device, inode, length, mtime and ctime), with before/after checks; this content cache is never persisted and cannot treat restored mtime as proof after a write. `.runtime/manual_degap/current.json` is the authoritative catalog pointer. A directory or token-named ZIP alone is never completion evidence. Different current base tables, changed candidate files/links/packages or an unfinished publication must not be silently accepted.

Catalogs and package caches are immutable after sealing. The result ZIP at the explicitly exported job directory and catalog pointer are published under the outer workspace lock with a content-bound pending plan and recoverable prior bytes. A later invocation resolves a pending atomic-file exchange before collection, finishing a fully verified new set or restoring the still-owned old one, never overwriting unknown changed files. Recollection uses verified cached packages without repeating their alignments. Legacy layout keeps its existing metadata publication behavior. Collection rechecks the native result receipt, collected candidate snapshot and immutable alignment inputs after staging; a changed input cannot be mixed into a published catalog.

The App export side must independently resolve the numbered/legacy runtime and actual original/refined/manual source catalog rather than assuming portable App paths are Server filesystem paths. Adoption of pre-migration manual package caches also needs an explicit verified adapter, not a bare token-file cache hit. Until that source/runtime work is integrated and checked, this Server catalog alone does not establish an operational manual App workflow. Final checks must include preserved original LGZ proof, incremental candidate source continuity, failure/interruption recovery, both layout versions and the real App importer.

中文要点：编号工作区的人工候选使用独立、版本化来源目录，不追加主 LGZ metadata，不改变原始基线或自动精修 Final Path。内容绑定的候选目录、包缓存和发布指针可恢复；旧布局保持原语义。App 的运行库/种子来源路径必须联动适配，不能只把字符串路径改名就宣称全链路完成。


## Remaining integration points

- `app/backend/src/degap_jobs.rs` still hardcodes `.prepare_lib/tools/degap_results.py` and `degap.py`; its `SeedMemberPlan` projects portable App FASTA paths directly onto a remote Server root. A new export must resolve actual original/refined/manual source identities and the layout-specific runtime, including light-package sources, without guessing a native filename or falling back across an incomplete migration.
- `build_degap_receipt()` currently derives `target_track` from the source dataset except for `derived_ctg`. A refinement patch's internal dataset is not the original display track; use its actual placement/track context instead of inventing an assignment or homology hit.
- Original legacy manual caches moved to `.runtime/run_all/degap_packages` need verified adoption into the new immutable registry. Bind the original migration inventory, candidate/recipe and actual package bytes before reuse; do not rerun an otherwise completed job or treat a leftover ZIP as authority. Unknown external result ZIPs must remain protected from silent overwrite.

These are outstanding requirements, not optional follow-up polish. The current Server catalog checks do not close those App/legacy boundaries.
