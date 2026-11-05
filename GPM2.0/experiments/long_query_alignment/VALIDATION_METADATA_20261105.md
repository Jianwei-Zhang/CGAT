# Initial-reference validation review and metadata-safe resume

Scope: the original-reference / long-query recovery path only. No mapper flags,
query batching, thread allocation, scheduler, App or LGZ scientific logic change.

## Customer evidence and acceptance boundary

The supplied failure had 676 ordinary queries completing successfully in
239307.731 seconds, with 14 long queries still pending. The first long query
failed before window mapping because the shared target-store binding rejected
ctime-only changes. Follow-up metadata showed unchanged size, mtime and inode
for both original FASTAs, with ctime updated on 2026-11-05 at about 10:39 +08:00.
No content hashes were recomputed by that metadata probe; it does not prove the
customer sequence bytes are unchanged or certify the remaining long-query run.

## Validation review

| Check | Decision and reason |
| --- | --- |
| ctime-only difference directly aborts borrowing, publication or resume | Removed as an independent veto. Stable content SHA-256 must match before old data is reused. |
| Whole runtime receipt hash alone discards completed native work | Allow same-source package changes and one frozen reviewed pre-fix source profile, with matching mapper/helper/scientific modules and original content. Other scientific/runtime changes still start fresh. |
| Full source/spool/index SHA repeated at every unchanged window/guidance/admission boundary | Consolidate by stable path, device, inode, size, mtime and ctime in a bounded process-local memo. Metadata changes invalidate the memo; no persistent trust flag is accepted. |
| Source path, live handle and private-spool ownership | Keep. Prevent wrong-source, closed-handle, linked/replaced spool and offset/layout reuse. |
| Original query accounting, target partition order and inherited minimizer threshold | Keep. Required for native candidate/MAPQ semantics and avoiding omitted records. |
| Tool/helper identity, actual command/exit/log and complete output SHA | Keep. A successful status label or syntactically valid PAF alone is not a completed matching calculation. |
| Candidate multiplicity, overlap/CIGAR/base/coordinate and native selection evidence | Keep. Removing these would change what a recovered result means. |
| Atomic output publication and final source/runtime checks | Keep. Never publish an incomplete/changed result. |
| Diagnostic six-hour timeout inherited by formal recovery | Removed for prepared Server execution; the submitted job lifetime/cancellation controls execution. Explicit standalone diagnostic timeouts remain. |
| Input/receipt size, regular-file and bounded trace guards | Keep. They protect integrity/resource safety, not incidental timestamp equality. |

## Resume behavior

- The caller holds the existing alignment lock. A compatible key transition
  hashes both original FASTAs against their previously recorded content first.
- Both sides of the reviewed migration are pinned complete 26-file digest maps, not a
  version string or user-provided production-ready flag. A changed scientific
  module/helper, unsupported source-profile pair or old recovered cell is not adopted by
  the legacy compatibility path.
- Both original control receipts are backed up. If either control update fails,
  both are restored. Input, MMI, completed native PAF and native commands are
  never rewritten by this migration.
- Existing groups/stores/index/completion/output proofs are revalidated before
  mapping reuse. Corrupt payloads fail closed; they do not trigger an automatic
  mapper retry or silently fall back to an unverified old output.
- Source size, mtime or physical-file identity changes remain fresh-work or
  integrity boundaries; the metadata-only path is specifically ctime tolerance.
- Scientific analysis acceptance on the customer's original long sequences is
  still pending. Local controls do not replace the customer rerun.

## Local regression controls

Use the pinned minimap2 2.31-r1302 and bundled portable companion explicitly.
The tests cover live ctime-only changes, source/spool content corruption with
restored mtime, replacement/closed handles, metadata races, bounded digest reuse,
index corruption, frozen-profile migration, write rollback and unknown-profile
refusal. Real-mapper controls require byte-identical final PAF, preserved native
PAF bytes/mtime, no repeated ordinary mapping/index command, and subsequent
complete-cell resume without any mapper invocation.

### Recorded local results

- Alignment/recovery suite: **437 passed**, no skips. Pinned real mapper,
  portable companion and independent v2.31 upstream source controls enabled.
- Server Python suite: **442 tests, OK**, one unrelated MUMmer4 integration
  skip because that tool was not on the local test process PATH.
- The 26-file legacy profile equals the runtime source map in the customer's
  supplied failure receipt. No customer sequences are committed as fixtures.
- No customer original sequence run has been performed by the maintainer.
