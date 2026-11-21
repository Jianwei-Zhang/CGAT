# Refinement reporting and publication contract

Date: 2026-11-22. Status: implemented public launcher, real App archive validation, and independent report/delivery refresh; final acceptance remains pending.

## Reports are not final publications

`refinement_batch.execute_batch()` runs the requested engines sequentially, keeps independently verified successful native/admission results, and builds an attempt report. A native or report failure does not stop later tools. It returns a nonzero aggregate outcome if any tool/report fails.

Each tool attempt retains `04_refinement/<tool>/01_inputs`, `02_jobs`, `03_native`, `04_accepted`, and `05_report`. Success reports have `cgat.refinement-report` manifests bound to the immutable provenance hash, generator hash and diagnostic hashes. Failure reports use a distinct `cgat.refinement-failure-report` schema and explicitly have no final result. They cannot satisfy the publication gate.

A report contains the accepted sourced Final Path document, not a new whole-chromosome source. Original-gap pages use zero-based half-open placement coordinates; source intervals remain one-based inclusive. Original gap IDs are the same chromosome/sequence/interval identities used by admission.

Native text diagnostics are copied without alteration. A per-file 20 MiB and aggregate 200 MiB attachment limit prevents raw sequences or large native intermediates from making reports unusable. Omitted entries have explicit availability and original hash information, with no broken link. Upstream HTML is retained as source text, not executed with external CDN scripts. The CGAT report has no JavaScript/network requirement. This does not certify upstream interactive HTML offline behavior.

The current-batch overview is `06_report/report.html`. Its comparison data are under `06_report/03_comparison/<batch_id>/`. It keeps every original LGZ gap even when all engines fail; a failed engine is not presented as a successful zero-fill result. A changed common baseline invalidates the comparison instead of mixing denominators. No best-tool or biological-accuracy metric is invented.

## Three-area publication

`refinement_commit.publish_result(root, lock, result, report, delivery, validate_delivery)` requires the actual held numbered-workspace lock. It validates native completion/provenance, the final artifact hashes and the report binding, then calls the supplied **repository-owned App validator** for both full/light deliveries.

The App validator must return `cgat.refinement-delivery-validation` version 1, including:

- the exact tool and native run ID;
- `modes: [full, light]`, a versioned validator identity;
- the admitted Final Path and provenance file SHA-256 values;
- the exact portable report manifest SHA-256, verified in both archives;
- a chromosome-name map of final sequence lengths and SHA-256 values.

The return value is not a substitute for checking archive contents, source availability and reconstructability. The repository-owned `refinement_delivery.validate_delivery()` now checks those properties before returning it; full mode reconstructs the admitted chromosomes from archive source intervals. There is no CLI option accepting a user JSON assertion or an arbitrary validator script. The filesystem transaction tests still inject a deliberately named fixture validator; **those are not App acceptance**. Separate controlled tests now create and validate genuine full/light App archives through `publish_batch()`.

The transaction prepares stable copies and then publishes the following fixed locations:

```text
05_final/<tool>/
06_report/02_refinement/<tool>/
07_delivery/<tool>/
```

Transaction journals and previous owned trees remain under `.runtime/refinement/publications/<transaction>/`. The tool pointer is `.runtime/refinement/publication/<tool>.json`.

There is no claim that three filesystem renames happen as one OS operation. The pointer is the authoritative commit boundary:

1. Validate the prepared final/report/delivery set and ownership of any prior publication.
2. Persist a `publishing` fence before changing public paths.
3. Move changed prior owned trees into history and their prepared replacements into place; leave byte-identical areas untouched.
4. Verify the published set and App delivery proof again.
5. Persist the committed journal and then the content-bound committed pointer.

`current_publication()` rejects unfinished fences and changed published content. A bare `05_final` directory is never a success receipt. Complete native/admission results may still be reused when report/delivery publication is incomplete; cache results only say `already_published` after the publication receipt is validated.

Ordinary errors restore the prior owned set and pointer. A process interruption leaves enough state for `recover_publication()` to roll back an incomplete exchange, or finish the pointer for a completely validated exchange. Recovery refuses unknown changed targets/backups instead of overwriting user edits. Unowned existing final/report/delivery directories are never silently replaced. This recovery does not run any native engine.

## Report and delivery refresh do not rerun science

A matching scientific `run_id` alone is not a reason to skip publication. The archive set has a separate `cgat.refinement-delivery-generation` binding: accepted provenance hash, report manifest hash, archive format, and exact serialization/validation helper source hashes. An unchanged verified publication reuses its transaction. A report-only or serializer-only change creates a new artifact generation and publication transaction with the **same admitted scientific result**.

Both full and light archive validation checks the portable report's own inventory and provenance, then binds its manifest hash to the generation and publication report. A current `06_report` beside an older archived report is rejected even when DNA and run IDs are identical. The process-local archive validation cache includes the complete archive declaration and validator revision, so a changed generation declaration cannot reuse an earlier proof.

During replacement, byte-identical areas are journaled as unchanged: `05_final/<tool>` is neither copied nor renamed for a report/package update. Recovery verifies those areas in place and restores only exchanged areas. The original native output and admission evidence remain untouched. Older archive declarations without a generation remain inspectable, but are not considered a current generated delivery; the next publication refreshes packages rather than rerunning the native engine.

## Native failure boundary

DEGAP's parent process can return zero even when child jobs fail. The adapter therefore requires its pinned child-job summary/config, checks that every configured job is accounted for exactly once, and rejects nonzero exits, exceptions and timeouts. The pinned engine also labels a normally completed but unfilled job `failed`; that exact no-fill record is distinguished from execution failure, not blanket-rejected or silently called a successful fill.

Native timing is measured independently from requested resource budgets. Report data retain the threads actually used by a reused execution. Peak RSS is explicitly not measured in this implementation.

## Remaining integration

Real full/light App archives have now been built, validated and published through this API on a controlled admitted-result fixture. The Windows App importer/initializer/exporter is checked against that same serializer output. Public launch/config/resume wiring, completed-legacy-workspace migration and default numbered initialization are implemented. Incomplete legacy stage resume, affected-evidence generation and real pinned-native acceptance remain required. This is not a real four-engine/customer-data acceptance claim. Final validation must include the accepted A01–A18 matrix, real pinned-tool small examples and both architecture environments. Intermediate report/transaction checks do not replace those gates.

---

## 中文摘要

这层代码把“原生运行完成”“接纳路径已重建”“报告可读”“最终结果及两类 App 包已发布”分开。工具失败、报告失败或事务中断，都不能用旧目录或 LGZ 副本冒充本次精修成功。

报告覆盖全部原始缺口，能追到 DEGAP job 和原生日志，并明确原生与接纳结果的差异。三目录发布以内容绑定的 committed 回执为准；中断可恢复，旧成功结果保留，不覆盖用户未知文件。

相同 `run_id` 不再直接跳过报告与交付刷新。报告、打包器或格式变化时，生成新的 full/light 包和发布事务，复用原有已接纳科学结果；未变化的 `05_final` 文件不复制、不替换。两种包必须包含与当前发布一致的报告，不能把新报告和旧包混搭。旧版无 generation 的包仍可检查，但下一次发布会补建当前交付，不重跑原生工具。

公共入口、已完成旧工作区迁移、编号布局与真实 App 包校验已接入，Windows App 导入/重建/导出已有受控夹具检查；这不等于四工具真实数据或客户工作区已验收。未完成旧流程续跑、精修片段新证据、真实固定版本工具及双架构环境仍需继续，最后统一进行 A01–A18 完整检查。
