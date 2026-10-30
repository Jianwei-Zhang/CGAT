# Recovery local acceptance — 2026-10-30

**Local branch/customer-candidate acceptance complete; customer original-data
acceptance pending.** This is not an official Release promotion or an assertion
that the customer's wheat workflow has already finished. The user explicitly
authorized testing for this acceptance run. The published Server source, master
and official assets were not changed.

Implementation checkpoint: `a8baea07bcfef7dba2b9e75f9b530191b1ebc42c`.
The exact shipped runtime/Server/helper file hashes, local acceptance receipt
and extracted-artifact checks are retained, not inferred from a version label.
See [DELIVERY.md](DELIVERY.md) for scope, customer operation and maintainer build.

## Executed acceptance

| Check | Actual result / boundary |
| --- | --- |
| Complete unit suite | **352 passed, no skips**, with the pinned mapper, built helper and independent unchanged-source oracle enabled; final targeted package units also passed. |
| Native candidate/metadata controls | **9/9**, repeated with the legacy-ABI helper and again with the helper extracted from the final customer archive. Ordered core/CIGAR, NM/nn/ms/cm/s1/s2/tp/rl/zd contracts match. AS is not reconstructed or compared. |
| Additional stress | **20/20** fixed-seed 160-kb cases, including reverse, near-repeat/duplicate candidates and boundary SNP/indel controls. Not a general polyploid DP equivalence certificate. |
| Downstream GRT / Final Path | **10/10** scientific projection/path comparisons, including accepted forward/reverse external donor repairs. Generated trace/run metadata are not claimed byte-identical. |
| Real long input | A real **270,000,000-bp** reference and mixed complete forward/reverse long, ordinary and N-only queries trigger the exact original SIGABRT. Both long singletons independently abort and complete selective 50-Mb/100-kb recovery. Geometry, split logical CIGAR, statistics, ordinary native bytes and all four cells match the analytic identity contract. |
| Strict per-result publication | A separate real portable-helper long run generates both leaf completion proofs. Actual original/native abort receipts, original-chain/overlap/full-candidate evidence, complete cells and actual selector input/stdout are bound before admission; **14/14** negative modifications are refused without modifying the retained fixture. Unknown MAPQ 255 is never published. |
| Actual default multipart | A real **8,270,060,000-bp** reference, original default policy (**no `-I` override**), actual **79 + 3 records in two parts**, all **8 query × part cells** complete. Both long first-part singletons recover; the second part completes natively with zero hits. This is a retained native/selective-engine checkpoint, not a claim of running the final packaged entire workflow on customer multipart data. |
| Portable runtime | Separate unchanged-library helper, explicit glibc 2.17 sysroot, static zlib + complete license/header. Measured maximum GLIBC requirement **2.14**, no RPATH/libz dependency. **40** native producer/selector protocols match byte-for-byte on host and actual isolated CentOS 7 / glibc 2.17. |
| Genuine old failed workspace | Original customer-cohort Server `d1519a76ce1f1df37c9186db1edb26e03a51ab26` actually fails with **exit 134** on a 270-Mb long + ordinary + unmapped input. The same run.sh arguments using the candidate auto-match the old staged source, retain original command/logs, recover the reference and finish **all 11 stages**, Full + Light delivery, **exit 0**. This end-to-end recovery fixture is single-part. |
| Same-command rerun | Real same-argument rerun finishes exit 0; reference result, all outer checkpoints and the recovery-attempt receipt have identical byte hashes **and mtimes**. The reference/assignment/chromosome checkpoints are cached; internal GRT cache checks and packaging still run normally. No new mapper/recovery attempt. |
| Actual long delivery App import/export | Real Full and Light archives import into the App backend, initialize projects and expose valid Final Path. The 270-Mb source contig export and Q4 coordinates/sequence hash match the analytic reference. Default App chromosome export correctly retains **both assigned source contigs plus its 100-N assembly gap**, not just the Q4 overlay. No native desktop UI claim. |
| Lifecycle/failure/rollback | Packaged actual subprocess native-byte, non-target error and SIGTERM controls pass; mapper and child stop on cancellation, stale results stay quarantined, failed partials never publish. These three controls explicitly use a fake mapper, not scientific evidence. Unit filesystem fault injection also covers no-clobber publication, source mutation, task/launch ownership, partial-handoff rollback, incomplete-journal recovery and concurrent-edit preservation. |
| Canonical Server gate | Full `quality-gate-server.sh` passed, **no Server-to-App skip override**. Backend CLI built; frontend Node tests used Windows Node 22, not WSL Node against Windows node_modules. No frontend production build/native desktop run was claimed. |
| Merge compatibility | Latest fetched `origin/master` = `fcfb161a0464aba00a3346729a8a1df9721cb008`; implementation merge-tree is clean. Existing App fix `c8e3a4f` remains an ancestor. Master was not merged/pushed by this task. |
| Final archive, not only worktree | Reopened archive hashes match all named regular members. Extracted to a **new path containing spaces**; all 9 native controls, all 3 lifecycle cases and a fresh normal **11-stage run.sh** pass. Fresh normal PAF is byte-identical to completed native output and never enters recovery. Final outer ZIP CRC/member hashes and supplied SHA256SUMS pass. |

Pinned minimap2: `2.31-r1302`, SHA-256
`b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.
Unmodified upstream library commit:
`3c28777e7e2dcc90f825de1b9f17a89cca7d4452`.
Portable companion SHA-256:
`00a0cee279f70d1faf35202b9328217226efcbe261bf0ff7e19b5bf4c783ab2e`.
No installed minimap2 source/binary was changed or replaced. The companion's
immutable build manifest records its original build recipe; later source-only
ELF inspector refinements are not falsely attributed to that build.

## Delivered local candidate

Windows directory:
`D:\desktop\CGAT-deliveries\minimap2-recovery-20261030`

- `CGAT-minimap2-recovery-20261030-linux-x86_64.zip` (**637,865 bytes**):
  `3a8db653ce5b6439ece5f2f1712a31679e62fd88bcd6ec7dc7e993a926b382ec`.
- Inner `CGAT-minimap2-recovery-candidate-linux-x86_64.tar.gz`:
  `a2a59becdcf58c1bb3eb9c81a79ed680586423efad8acad129738a158d4798ad`.
- ZIP includes the tar, Chinese operator instructions, artifact verification and
  SHA256SUMS. No customer compiler/configuration or experiment command is needed.
- Package status: `customer_deliverable:true`, `customer_validation_pending:true`.
  `production_ready:false` deliberately excludes unperformed customer acceptance
  and official Release promotion; it is not a closed per-result recovery switch.

## Boundaries / rejected evidence

- Customer correct tool version and independent single-record reproduction are
  already confirmed by returned logs. Do **not** ask to repeat that same step.
  Customer FASTA/PAF were not supplied: the exact original overflowing operation
  and correct complete original-data output still require the candidate run.
- Only initial-reference asm10 is adapted. Self `-X`, other presets, non-target
  failures, unsupported inversions/seams/alternative-source cases are not silently
  assigned this recovery. No arbitrary whole-query DP/AS equality is promised.
- Original default index context and records are preserved; no BAM is written.
  The issue class involves packed internal CIGAR operations, not proof that the
  customer requested BAM output.
- Earlier two-thread multipart attempts with a deliberate 12-GiB address-space
  cap stopped before the target assertion: one logged insufficient memory and
  one exited SIGSEGV without attribution. They were correctly not recovered and
  are **not** passing receipts. The one-thread default-multipart control passed.
- ARM/macOS, native desktop interaction and customer wheat biological acceptance
  are unverified. No broad scheduler/memory framework or unrelated App edits were
  added for this closure. Keep old installations/workspaces and handoff backups.

## Retained evidence and reproduction

Raw local reports/commands/fixtures remain under
`/tmp/cgat-merge-readiness-20261030-2uXTWv/`. The archive embeds the source-bound
maintainer `LOCAL_ACCEPTANCE.json`; it is an auditable attestation, not a test
runner, signature or a way to bypass the actual per-result admission checks.
Earlier source checkpoints are identified as such rather than presented as
executions of later code. This task did not run customer jobs or upload FASTA.

Complete suite (requires the already built/tested local prerequisites):

```bash
export PATH=/home/xbzhang/micromamba/envs/cgat-server/bin:$PATH
export PYTHONDONTWRITEBYTECODE=1
export CGAT_MINIMAP2_BINARY="$(command -v minimap2)"
export CGAT_NATIVE_CHAIN_STATE_BUNDLE=/tmp/cgat-merge-readiness-20261030-2uXTWv/legacy-native/linux-x86_64
export CGAT_MINIMAP2_NATIVE_SOURCE=/tmp/cgat-merge-readiness-20261030-2uXTWv/native/linux-x86_64/upstream-source
python3 -m unittest discover -s GPM2.0/experiments/long_query_alignment -p 'test_*.py' -v
```

| Evidence | SHA-256 |
| --- | --- |
| `unit-closure.log` | `5ecc3a820b0bf3b392b00945ce59707cbd04834cdf42f835e16aea995910550f` |
| `legacy-native-controls/native-controls.json` | `f21854d696aa9fd7e1b84c9c3a878b6ecd893d8eb8ace23303c340656bd93450` |
| `stress/summary.json` | `9d07cd593711dbc4f995204fe447861a0f139dd383fa9c25cb19a831ae4eb18d` |
| `grt-controls-fixed-env/comparison.json` | `ae92a48177ffedcc62a4537619940153f3d8a37960fe24815f84c6aa1cb4f31c` |
| `real-long/long-identity.json` | `6be994263dc6e5ba6afabc92bd15a97cb70913b292cd03d36cd52d7c389feea8` |
| `proof-long/admission-strict.json` | `a2ec29f3aada203b9a11bb9d56b90933f9223e3bc962a35ef9056983634bbd49` |
| `multipart-single-thread/multipart.json` | `cf5f58a39c85311d7d020ddad27a4d7047b3097f4f3eb32b727ed591936ebd7e` |
| `publication-controls/publication-controls.json` | `d766d35a0eb381debd64f84363074d17a2f1999f2ec46aa0e7c51ea8e7b64888` |
| `legacy-runtime.json` | `49fbbebb8851dcc50d13617c94ac6165e95ff0fa3576ae9b3027e73813eaee17` |
| `lifecycle-controls-fixed/lifecycle-controls.json` | `10f6bb4ee06d74fb5ca7448a84ecb4809f78fbdeefd256da827399582f831145` |
| `full-run-product.json` | `14f852092e061322d6eca6307357080730a342920be2c7122a9863a0e5c2d0a3` |
| `full-run-repeat.json` | `9db829d8a793c9225f0082bc05ebaa17124e47ceadde93768001e2606eaa2b89` |
| `actual-app-import-fixed/app-import-export.json` | `386a1d40231719e21c1404d2991549abca1bf8a95ca944c55d959b4ac66fe71d` |
| `server-quality.log` | `a8bbbbb40d9d4959e5b8a4c86a9dce4899d0b581808b37a4a836369714e45ceb` |
| `merge-compatibility.json` | `43b7d4f17c812b824e361de5f432e7e4fd7369a14d72cda043dfe62a50127a73` |
| `local-acceptance.json` | `ba496041e4997bd22cc5edd6528e12a28cb263c223ea455ec2c0152d5732b6ce` |
| `final-artifact-verification.json` | `e7db6cb389489ac47dc2800f47cabf10e364b02fa6b15d6d0b207b58b8351fec` |
| `customer-handoff.json` | `0c7c9fea6f7961a83bff56c018342218e06f41461b9281bbb3b6ce3d618400e2` |
