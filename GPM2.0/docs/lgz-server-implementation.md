# Server LGZ implementation naming

Confirmed: 2026-11-01. Scope approved after the Server naming discussion.

## Implementation and entry points

- Maintain one implementation under `tools/lgz_core/` and `tools/lgz_*.py`.
- Retain `tools/grt_core/` and `tools/grt_*.py` only as compatibility forwarding modules, including private-symbol/module identity needed by existing Python consumers.
- Use LGZ names for algorithm-specific internal functions, but do not prefix generic helpers such as `execute_step2` or `validate_contract` unnecessarily. Preserve old function aliases for callers.
- New CLI help and generated shell commands use `--lgz-*` and LGZ script names. Continue accepting every existing `--grt-*` option and generating forwarding shell entry points for the old names.
- Both installed tools and existing `.prepare_lib/tools` must receive the new implementation, compatibility modules, top-level Python dependencies and active packaged reference-recovery receipts/runtime through verified, backed-up, reversible updates. Do not rewrite an existing execution plan merely to rename it.

## Stable contracts

- Do not change algorithm parameters, decision rules, workflow/schema versions, `grt/` output paths, `metadata/grt_*` tables, serialized field names, persistent unit IDs or database/desktop import contracts.
- Keep historical validation records and frozen source-provenance baselines unchanged. Regenerate only the active package-bound runtime inventory (`resume-base.json` and `branch-runtime.json`) with the existing maintainer synchronization script so its current tool hashes include both namespaces; do not edit those hashes manually.
- Updated engine bytes and module paths change the verified engine fingerprint. Do not forge compatibility with an old decision checkpoint. Preserve raw alignment caches and all user data/results/logs/checkpoints; stage-decision revalidation may legitimately be required. No update operation starts analysis.
- Retain validation against unmanifested modules and active/foreign-host process locks for both old and new namespaces. Maintain rollback for files added during migration.

## Validation and publication boundary

Validate old/new Python import and CLI equivalence, generated script aliases with unchanged plan unit IDs, legacy workspace code updates and rollback, engine fingerprint parity, raw cache preservation, stable data-contract validation and the Server regression suite.

This task authorizes implementation and source commit/push. It does not authorize overwriting a published Release attachment, deploying a website or mutating a customer workspace. Public Server-package refresh is a separate publication gate; report it as pending unless separately authorized.

## 中文摘要

正式实现与新入口使用 LGZ，旧 GRT 名称仅作为转发兼容层。既有 CLI 参数、Python 导入、生成脚本继续可用；数据协议、产物路径、序列来源及持久化阶段 ID 不变。运行时更新同时覆盖安装目录和工作区内嵌工具，保留校验、备份和回滚，不自动运行分析。源码指纹变化应如实记录，不冒充旧检查点身份；保留原始比对缓存与所有用户数据。本次授权实现及源码提交，不自动发布附件、上线站点或修改客户工作区。

## Validation result (2026-11-01)

- All **411 Server Python tests** passed in an isolated Linux source mirror. Executable Server/test sources were compared byte-for-byte with this working tree; no shared Windows frontend dependencies were used.
- All eight Server shell acceptance suites passed: fake-command control, environment, package templates, preparation metadata, full preparation, Final Path, add-dataset and add-contig. These include synthetic end-to-end pipeline/delivery generation, both CLI spellings, stable plan IDs and safely spied legacy shell forwarding.
- Windows-host `cargo test --locked grt_package`: **33 passed, 1 pre-existing opt-in benchmark ignored**. No App/frontend source changed, so no frontend rebuild was needed. This does not claim native desktop interaction or real biological-workload acceptance; the complete Server-to-App E2E remains a CI gate rather than a locally claimed pass.
- All **34 moved implementation modules** passed AST equivalence after normalizing the approved module/helper/constant names, executable provenance paths and compatibility aliases. The intentionally changed shared engine-fingerprint file-selection body was reviewed and tested separately; algorithm decisions/parameters were not changed.
- Both update routes have migration/rollback regression coverage. Checks include newly added namespace removal on rollback, old engine-hash restoration even if empty directories remain, source-manifest stripping, missing package initializers, unknown core/recovery files, raw-cache preservation and copying the complete active Python/recovery dependency closure into embedded workspaces.
- The maintained generated-runtime sync verified **31 files**; only its two current inventory receipts were regenerated. A staged LGZ tool tree matches the package-bound reference-handoff inventory; tampering is still rejected.
- A local, explicitly non-release source archive verified all **257 manifested Server files**, fresh extraction, old/new CLI entry points, relocated skill binding and producer/updater fingerprint parity. No public artifact was replaced.
- Shell syntax, tracked LF line endings, guide-version checks and scoped Git whitespace checks passed. Historical Release Notes, frozen validation records, App/database contracts and the DEGAP submodule were not modified.

Source implementation is ready for commit/push. Public Server source-asset refresh and any corresponding docs/download deployment remain separate, unexecuted publication gates. Previously published archives continue to require their older entry/flag names until refreshed; both spellings are supported by this source implementation.
