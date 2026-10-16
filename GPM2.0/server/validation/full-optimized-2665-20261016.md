# Customer2665 complete optimized workflows — 2026-10-16

## Request and boundary

User requested the complete real input and the same parameters/thread budgets as
the original two workflows, but with the newly integrated execution optimizations;
**Step2 gap-screen must remain disabled**. No old baseline is rerun and no running
workspace is modified. This test is independent of the earlier GRT suffix tests.

## Submission

| New complete workflow | Job | CPU | Initial observed state | Node | Original retained job |
| --- | ---: | ---: | --- | --- | ---: |
| optimized, skip-self | 40587587 | 16 | RUNNING / preparation | agent-X86-05 | 40550762 |
| optimized, self-m200-n100 | 40587588 | 16 | RUNNING / preparation | agent-X86-27 | 40550763 |

Submitted 2026-10-16 13:05:11 CST; both started 13:05:15. Queue `x86` plus `-aa`,
16 CPUs requested and `--threads 16`. Original resource/runtime/input environment
is retained rather than substituting the separately tested newer ARM environment.
No added global environment, module, shell-startup or Release changes.

Remote root: `~/cgat-reads-debug/full-optimized-2665-20261016-6cc768d/`.
Pinned source revision: `6cc768d864dc2a541964dce080f0f8d938018938`.
Transferred archive SHA-256 (verified before extraction):
`d7718ee3ccedc73471da27a18249d505ffa579bf2d3ef09c5a36119d4f8da49b`.
Launcher SHA-256:
`9714dc63a85b2a626babb994d7e4e4165d61a9a1c971594160eb299bf6c25350`.

## Exact parameter preservation

`full_optimized_2665.py` reads each original workspace's retained
`.run_all/launch.json` argv. It replaces **only the output directory**, then adds
explicit `--grt-execution-profile optimized --grt-step3-mummer-scope gap-screen`.
Step2 full is fixed by the production generator; no experimental override exists
in this launcher. Parameters remain:

- Complete reference `Caryophyllales_ref`, all datasets in order: hifiasm,
  nextdenovo, flye. Same original input paths; compute-node size/mtime/hash checks.
- Score60, minimap preset asm10, 16-thread total budget, tar.gz packages.
- Telomere TTTAGGG/min_repeat3, max-fill1000000; no reads or centromere input.
- One case uses skip-self; the other self-m200/n100. No other thresholds changed.
- Exactly the old x86 environment: Python3.10.12, minimap2 2.30-r1287,
  MUMmer4.0.1, samtools1.21 and pigz2.4; resolved executable paths/hashes recorded.

## Fresh execution and acceptance

New empty workspaces are required; the launcher refuses existing workspace/report
paths. It does not copy assignment, reads-QC/Step1 checkpoints, numerical caches,
.mmi indexes or old results into new workflows. Production may reuse **its own**
compatible cache/index later in the same run. Shared immutable input paths and
OS file caches are not represented as cold filesystem caches.

Run scope is true end-to-end: prepare, all reference alignments, assignment,
GRT prepare, Step1, separate Step2 and Step3, telomere/finalize, every configured
self/cross chromosome task, final evidence and Full/Light packaging. This differs
from the earlier complete-data **GRT suffix** benchmark.

Reports record complete workflow wall time separately from input/tool preflight
hashing and postchecks. Checks require all stages successful, actual optimized
Step2/full and Step3/gap-screen checkpoint settings, Q2/Q3/Q4 file identities and
ordered Final Path source/interval/orientation/kind/length/DNA against retained
customer golden artifacts. Actual delivery presence is checked; full archive
CRC/content acceptance and App import are separate gates, not claimed here.

No strict old/new speedup is asserted until new workflows finish; different
compute nodes/shared filesystems/OS caches may affect wall time. Complete source,
.dsub scripts, original/new argv, input/tool hashes and logs remain under the
remote root. Existing original and suffix tests continue untouched.

Necessary checks for this submission: scoped Python parsing, Bash syntax,
transfer SHA-256 and actual scheduler/startup inspection. No unrelated tests or
frontend/browser runs were added.

At 13:06:27 CST both jobs remained RUNNING. Generated prepare_options.tsv
confirmed threads16, optimized, Step2 full, Step3 gap-screen, m200/n100 and
the correct per-case skip_self flag. Both were still in preparation.

## Completion — 2026-10-17

Both independent x86/16 workflows completed and passed their retained-golden
postchecks:

| Case | Job | Terminal state | Workflow wall | Checks |
| --- | ---: | --- | ---: | ---: |
| skip-self | 40587587 | SUCCEEDED | 42,910.514 s (11 h 55 m 11 s) | 15/15 PASS |
| self-m200-n100 | 40587588 | SUCCEEDED | 49,741.113 s (13 h 49 m 01 s) | 15/15 PASS |

These jobs retain the original x86 tool environment and validate the earlier
`6cc768d` optimized/full-Step2/gap-Step3 runtime. They predate production
self-query batching and adaptive scheduling. The release-candidate runtime is
validated separately by complete ARM32 job 40588179; do not combine the
architecture, node, tool-version or CPU-budget differences into a pure speedup
claim.
