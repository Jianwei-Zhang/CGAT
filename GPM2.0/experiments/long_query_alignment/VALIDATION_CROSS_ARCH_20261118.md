# ARM to x86 continuation: evidence and implementation boundary

## Scope

The customer approved pursuing x86 continuation, not multi-node execution.
Cancel the queued ARM job only after real x86 continuation succeeds, not after
an environment smoke test. Preserve completed PAFs and their original commands.
Do not run two writers against the same workspace. If ARM has already started,
the authorization to cancel a queued job does not authorize stopping that run.

## Reviewed binary evidence

`ordinary_tool_transition.py` verifies the exact reviewed minimap2 2.31-r1302
binary pair. It checks real file content, ELF architecture, source/path agreement
and the new executable's actual version. A historical binary can be audited
without executing a foreign instruction set. It cannot validate PAFs or migrate
any checkpoint. Unknown builds are not admitted merely by version string.
Receipts cannot extend the inventory or disable payload revalidation.

The helper is now wired through adapter identity migration, ordinary controller,
unit execution, long-query native-window execution and final publication. The
original index and completed commands retain their original ARM builder/executor
identity. Incomplete old unit directories are archived, not rewritten or deleted;
future commands bind the x86 executable. Delivery policy records identify the
actual executable per native/window source without leaking filesystem paths.

This transition requires a completed ordinary calibration. Previously started
long-query work is not migrated: the current wheat long record has not started,
so its native-window mapping/review can run on x86 against the unchanged original
index. Existing calibration timing remains historical evidence, not a claim of
x86 speedup or a new cross-architecture benchmark. Quality checks, review budgets,
default fallback and complete input/output validation remain in force.

Generated sources are synchronized, but this change has NOT yet been published
or installed into the live wheat workspace. No full x86 continuation has yet
been submitted. ARM job 42396961 remains pending as of 03:20 CST.

## Verification

- 14 focused unittest cases pass, including content mutation, ELF mismatch,
  foreign/same/reverse pairs, unknown binaries, version failure/timeout, forged
  receipts, boolean/integer schema confusion and symlink substitution.
- Generated Server runtime synchronization: 41 files verified, zero drift.
- Seven additional real-native regressions cover immutable completed units,
  interrupted-unit archival, completed-child recovery, corruption refusal,
  mixed-tool controller resume, existing default fallback, prepared-adapter
  publication/repeated resume with new long-query native-window work, forged
  provenance, previously started long work and unreviewed runtime refusal.
- Server Python tests: 476 tests, one skip, all others passed. An initial invocation
  from repository root had import errors; the actual gate working directory is
  GPM2.0. The corrected run passed. An unrelated process-state race in that first
  run was not patched (Linux reported X/dead rather than the expected Z/zombie).
- Final mixed-long-query alignment suite: 838 tests, one optional native-source
  oracle skipped, all others passed (218 seconds). The additional negative
  previously-started-long-work assertion also passed in the targeted suite.
  This includes real native tests using pinned minimap2 and the portable helper;
  it is controlled regression evidence, not full customer acceptance.
- Donau x86 smoke job `42402478` succeeded on `agent-X86-26`, 2026-11-18
  02:30:14--02:30:17 CST. Pinned binary, synthetic 20kb mapping and selected
  published-runtime imports passed. This was not a wheat continuation test.
- Donau x86 real-index reader probe `42403680` succeeded on `agent-X86-56`,
  2026-11-18 02:38:02--02:39:13 CST. Read the unchanged ARM-built 22,182,328,026
  byte wheat index, mapped a synthetic 20kb query through both index parts,
  checked the index SHA-256 before/after and checked file identity across the
  operation. Mapper peak RSS: 13.592 GB. This is index compatibility evidence,
  not real-query alignment equivalence or an application speedup benchmark.
- The real ARM binary's native `--version` and SHA were checked on the ARM
  login host. The proof helper verified the real old/new artifacts on the x86
  login host without trying to execute the ARM artifact.

Observed binaries:

- ARM: `03f361d0b8dba343adb6067fbdc109719196ef0e2619ba02c5295826dcec56dc`
- x86: `cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3`
- Original two-part index:
  `efd680d24d22d9083be5d85a1ce4ed0713701d6d9ce2ca465b998e07e92dcb5b`

Operational scripts/receipts are in
`docs_deploy/release-v2.0.20/server-refresh-20261118/wheat/x86-readiness/`
and the corresponding remote `~/cgat-reads-debug/jm19-x86-readiness-20261118/`.
These are evidence records, not new user-facing configuration.

## Customer read-only replay

- First x86 audit 42406872 failed because the verification harness used the
  initial filter for Flye units after its valid recorded default fallback.
  The existing unit identity check correctly rejected that mismatch.
- Second audit 42408144 correctly revealed a real scope gap: hifiasm contains
  the unstarted long query ptg000049l. An ordinary-only transition would not
  complete this workload. The implementation now covers new long-query native
  windows and native quality reviews while retaining original index provenance.
- Neither audit launched a mapper or wrote the scientific workspace. Their
  failure logs are preserved. They are not successful customer acceptance.
- Third audit 42410157 uses source profile
  `5a6f6ae44f11b533ad2541dc77a5aabe7c0d9c170b19d6de990d90563b68ca6f`.
  It is running on agent-X86-26, starting 2026-11-18 03:19:11 CST. It validates
  hifiasm completed units, then the complete Flye publication path, checks all
  26 native PAF and unit-marker hashes before/after, and prohibits original
  workspace writes and all external processes except the new mapper's version
  probe. A running audit is not a passed audit or a full scientific continuation.

## Remaining acceptance gates

1. Finish the exact final-runtime regression/CI gates and real-data read-only
   proof. All 26 completed units must validate with zero mapper calls.
2. Publish the verified runtime and update installed/workspace tools under safe
   ownership. Preserve backups and verify exact installed/runtime file hashes.
3. Start one authoritative x86 full continuation, never two concurrent writers.
   The current workspace lock treats an owner on another host as active; do not
   clear it based on a local PID check. Preserve the queued ARM fallback until
   real x86 continuation succeeds; coordinate ownership before updating code.
4. Confirm genuine continuation, including old-result reuse and new execution,
   before canceling the still-pending ARM job. Recheck scheduler state first;
   stopping an already-running ARM computation is not covered by that instruction.
5. Monitor until every workflow stage and final delivery are verified complete.
