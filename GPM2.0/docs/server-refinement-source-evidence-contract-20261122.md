# Accepted refinement source evidence

Date: 2026-11-22. Implements the affected-source measurement portion of the approved Final Path publication chain. Native accuracy and final four-engine/environment acceptance remain separate gates.

## Inputs and execution boundary

After a tool has a sealed successful accepted result, measure only its newly registered patch source records. Bind the accepted provenance/source table, actual original reference, original prepared annotation files/snapshot, executable contents, parameters and helper recipe. Do not realign LGZ datasets, change the accepted Final Path, rerun native gap filling, load a newer official/local annotation library, or write indexes into original FASTA. Full patch records remain the source coordinate domain; a patch's presence in a Final Path is not homology evidence.

Reference measurements use the prepared minimap preset, full CIGAR PAF and the existing total thread budget. Validate query/target identities, lengths, intervals and CIGAR spans. A successful empty PAF is a measured no-hit, not an unmeasured source or a reason to fabricate a placement. Keep all actual hits, including other chromosomes and ambiguous hits, separately from the context placement used to display an accepted patch.

Use the existing frozen telomere rules and centromere scan policy (repeat-sensitive nucmer/show-coords) on new sources only. Disabled annotations, an empty prepared telomere-rule set (`no_rules`) or missing chromosome-specific library entries (`no_chr_library`) are explicit states, not negative biological findings. A valid scan with zero marks is explicitly scanned. Store source-domain marks and project their clipped intervals through each accepted source slice/orientation into final chromosome coordinates, including reverse sources and repeated uses. Do not carry old final-genome coordinates forward; unchanged source-domain evidence remains valid.

## Reusable scanners and numbered paths

The generated telomere scanner currently embeds old `root/tel` paths and refers to `workspace_join` without importing it inside its subprocess. Extract that scanner into a shared `tel_scan.py` entrypoint, preserving its literal motif/reverse-complement and TSV semantics, resolving both layouts and checking the prepared snapshot at execution. Generated chromosome jobs and patch measurements use the same scanner. Outer checkpoint input identities include this helper so a changed implementation cannot masquerade as an unchanged scan. This targeted caller fix does not change the original LGZ algorithm or annotation rules.

## Artifacts, cache and delivery

Keep a separately content-bound source-evidence generation under the tool's `04_accepted/<run>/01_source_evidence/<generation>/`. A cache hit requires completed output inventory and unchanged bound inputs/recipe, not an empty or leftover directory. Failed evidence generation fails that branch's delivery phase, retaining valid native/admitted results for retry; it never turns LGZ into a successful refined result. Report/bundle changes alone must not rerun native or already completed source measurements.

The report links measured per-source status, actual commands/logs and the source-to-final annotation table. Full/Light packages receive the same measured PAFs, new-source tel/cen marks and evidence metadata; Light omits sequence payloads as before. Patch cards retain explicit context-only placement, while their reference status records the actual independent measurement. Older source-identity/refined packages without this optional evidence capability retain their truthful `not_measured/not_scanned` state; the current production orchestrator must produce the new evidence before final delivery. Matching App validators must verify measured-status bindings rather than merely accepting another enum value.

## Necessary intermediate checks

Use small source/runtime/serialization checks for forward/reverse slices, genuine empty results, source/reference/rule drift, cache reuse, disabled vs scanned annotations, original-input immutability and both layouts. Tool-command test doubles must be labeled controlled producers; they are not actual minimap2/nucmer/four-engine acceptance. Fresh Windows Rust build, actual App import/re-export and complete native/environment acceptance remain in the consolidated final matrix.

中文：新增精修来源独立比对和注释，消费原始参考与已冻结库，不更新原 LGZ 数据。命中、无命中、未扫描、未启用明确区分；来源注释按真实切片和方向映射到新 Final Path 坐标。测量证据与原生结果分开缓存，Full/Light 同步携带；显示上下文不伪装成同源证据。实际编号路径的 tel scanner 同时修复，主流程必须测量后才能交付，新旧 App 包兼容边界保持明确。

## Current source implementation and check boundaries

- `refinement_source_evidence.py` builds and reuses sealed measurement generations; `refinement_source_payload.py` shares bounded full-record FASTA/FAI serialization without coupling delivery changes to native adapter recipes. `refinement_source_marks.py` maps source evidence using 1-based inclusive source and 0-based half-open final intervals. Complete vs clipped marks are distinguished. Boundary-spanning features not present in the scanned sources are not claimed to have been discovered by a full final-genome rescan.
- `refinement_batch.py` has an explicit failure-isolated `source_evidence` phase and freezes the shared reference/library/source-mark inputs across selected tools. Process-local content identities prevent repeatedly hashing unchanged large inputs while retaining size/inode/mtime/ctime and before/after content-read fences.
- Reference commands, versions and logs, annotation helper-call arguments, cen scan logs/coords and final coordinate tables are available through the report/packet evidence. Context placement remains separate from independent hit/no-hit/multi-hit measurements; no new original assignment or homology-derived placement is invented.
- Production delivery requires the source receipt and matching report binding. Full/Light archive validation checks the same receipt. Older component packets without the optional measured-source capability are readable but retain `not_measured`; they do not satisfy the current production delivery prerequisite.
- `refinement_source_delivery.py` handles packaging/semantic validation separately from measurement generation. App-side validation reads only portable packet data, never probes Linux Server paths or a local tool environment. It checks PAF names, lengths, CIGAR spans and actual status counts, frozen rules, complete source placement coverage and annotation/source coordinate reconstruction.
- Shared tel tests execute both layouts plus the actual generated numbered runtime command. The measured cross-language fixture uses a controlled accepted `GTNNAC`, actual developer-base minimap2 no-hit output, literal-motif tel scans and explicit controlled nucmer/show-coords producers; it is not pinned-environment, MUMmer or four-engine acceptance. Windows test cases are added for both availability modes, source marks, preserved refined sequence export and rejection of resealed false statuses/coordinates. A compile-only check is not evidence that those tests executed.

Measurement failures retain private query/command/log evidence under `failed-<generation-prefix>-<attempt>/` with a failure receipt, never a completion receipt. The failed branch's portable report links those diagnostics under the normal asset bounds. Retry preserves the native/admitted result; incomplete source-measurement jobs are not claimed as complete just because their files remain. The original full-source scanner/aligner inputs receive no new indexes or metadata.
