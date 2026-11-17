# ARM to x86 continuation: evidence and implementation boundary

## Scope

The customer approved pursuing x86 continuation, not multi-node execution.
Cancel the queued ARM job only after real x86 continuation succeeds, not after
an environment smoke test. Preserve completed PAFs and their original commands.
Do not run two writers against the same workspace. If ARM has already started,
the authorization to cancel a queued job does not authorize stopping that run.

## Implemented in this step

`ordinary_tool_transition.py` verifies the exact reviewed minimap2 2.31-r1302
binary pair. It checks real file content, ELF architecture, source/path agreement
and the new executable's actual version. A historical binary can be audited
without executing a foreign instruction set. It cannot validate PAFs or migrate
any checkpoint. Unknown builds are not admitted merely by version string.
Receipts cannot extend the inventory or disable payload revalidation.

The helper is not yet wired into the Server adapter/controller/publication path
or included in the generated runtime. No published Server artifact, existing
runtime, workspace checkpoint or scientific output is changed by this step.

## Verification

- 14 focused unittest cases pass, including content mutation, ELF mismatch,
  foreign/same/reverse pairs, unknown binaries, version failure/timeout, forged
  receipts, boolean/integer schema confusion and symlink substitution.
- Generated Server runtime synchronization: 40 files verified, zero changes.
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

## Remaining acceptance gates

1. Integrate historical/active tool separation through adapter, ordinary
   controller, unit receipts and final publication without mutating old tool
   claims, using exact reviewed runtime transitions.
2. Verify all 26 completed native units on x86 without remapping, and reject
   changed inputs, index, tool, native commands and PAFs.
3. Permit the unfinished unit and future units to use the x86 executable while
   retaining per-unit execution provenance and existing policy/quality checks.
4. Cover old/new/mixed completed work, interruption, repeated resume, publication
   and concurrent-owner rejection with targeted regressions and real-data proof.
5. Validate and publish the integrated runtime, update the installed/workspace
   runtime under safe ownership, then start one authoritative full continuation.
6. Confirm genuine continuation before canceling the still-pending ARM job.
7. Monitor until every workflow stage and final delivery are verified complete.
