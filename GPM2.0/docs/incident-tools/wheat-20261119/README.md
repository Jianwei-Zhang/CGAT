# Wheat 2026-11-19 incident admission patch

This directory preserves a tested onsite recovery policy, not a production
scheduler default. See `../../wheat-remote-handoff-20261118.md` for the dated
incident, job IDs and receipts. Do not run a historical submission blindly.

`memory_admission.py` subclasses the existing `alignment_tasks.AdaptiveDispatcher`.
It changes admission only: long/unknown mappings run alone, small mappings retain
a two-process limit, and the existing per-task thread allocation is unchanged.
The 100 Mb threshold is an incident heuristic, not a RAM guarantee. Both cross
mappings and self-alignment batches are covered. No scientific parameters change.

The onsite entry point imports this class instead of its previous fixed
`TwoMappingDispatcher`, retains the original checkpoint wrappers, and requests
32 scheduler CPUs plus 327680 MiB memory while preserving the 16-thread execution
budget. Its receipts and all 14 pre-existing cross checkpoints remain on 180.
Do not install this module into an active workspace whose fingerprint captures
runtime files; use a reviewed recovery boundary and preserve the original
checkpoint and leaf-cache locations.

Focused local validation (from the repository root):

```bash
python3 -B -m unittest discover -s GPM2.0/docs/incident-tools/wheat-20261119 -p 'test_*.py' -v
```

On the incident host, prepend the frozen workspace `.prepare_lib/tools` to
`PYTHONPATH`; tests must use that runtime, not whichever master happens to be
checked out. The admission profile is memoized only for the process lifetime;
input/output integrity remains enforced by the existing outer checkpoints.

Future integration must separately generalize admission, durable cross-leaf
reuse and integrity-preserving resume validation. Archiving this patch in master
does not claim those features are enabled in the default Server runtime.


## Isolated seed-filter pilots (not deployed)

- `seed_filter_pilot.py`: three disjoint 5 Mb windows from the longest query in
  each of 3D and 1A; baseline, `-f 0.001`, and `-f 0.005`, with a 300-second
  timeout per alignment. Full source hashes and the frozen Minimap2 hash are
  verified on a compute node. Outputs stay outside the analysis workspace.
- `long_window_pilot.py`: repeats with 20 Mb windows and 600-second timeouts,
  then compares both pilot sets using `paf_anchor_comparison.py`.
- Position checks project a query grid (every 10 kb) through primary CIGARs,
  respect reverse strand and indels, and report missing/additional/ambiguous
  positions. Coverage and PAF row counts alone do not prove mapping agreement.

Remote jobs `42675569` and `42677292` succeeded. The larger pilot measured:

| Query windows | Baseline time / peak RSS | `-f 0.001` | `-f 0.005` |
|---|---|---|---|
| 3D, 3 x 20 Mb | 250.36 s / 22.231 GB | 125.41 s / 12.700 GB | 24.80 s / 4.334 GB |
| 1A, 3 x 20 Mb | 229.39 s / 19.774 GB | 118.41 s / 11.580 GB | 30.25 s / 4.413 GB |

Time is the measured mapping-command wall time, excluding source extraction,
source verification and index construction; RSS is Minimap2's reported GB.
Each configuration ran once, in baseline/0.001/0.005 order, on one x86 node
with the same tool and three threads. These are not end-to-end speedups.

In 3D, all 5998 baseline primary grid positions retained an exactly matching
position under both filters; candidate coverage and CIGAR details still changed.
In 1A, exact support was 5972/5981 and 5965/5981 respectively, with additional
and missing positions. These are agreement with a baseline, not ground-truth
accuracy. All candidate PAFs differ bytewise from baseline. A grid may miss
short changes and windows omit whole-query chaining context.

No production parameters were changed. Do not silently generalize these cross
mapping pilots to self-alignment (`-X`, custom chain/minimizer thresholds),
all chromosomes, or initial reference mapping. Do not adopt a candidate PAF
as if it were produced by the original command: any future use needs an explicit
algorithm/parameter provenance transition and checkpoint-safe adoption.


### Full-context 3D follow-up (candidate only)

`full_3d_seed_pilot.py` runs one full 3D cross mapping with `-f 0.005`, three
threads and an 1800-second command timeout. It uses the original FASTAs, not
sampled windows, and retains input/tool/output hashes. Job `42681096` was
submitted to `agent-X86-46` with 8 CPU / 81920 MiB; inspect its live state.

There is no duplicate baseline submission: the baseline is the already-running
3D leaf of main job `42646893`. The script compares only after that leaf has a
successful checkpoint whose command, input, tool and output identities match.
A PAF file existing (even valid/nonempty) without its leaf checkpoint is not
sufficient. If the baseline is still pending, the candidate is preserved with
status `candidate_complete_native_comparison_pending`, not adopted or declared
equivalent. A later scheduled invocation with `--compare-only` validates the
stored artifacts and performs only comparison; it must not rerun alignment.
This follow-up does not modify either analysis workspace or approve a global
approximation policy. Native and candidate run on different x86 nodes, so any
later timing comparison must disclose that boundary.

Four focused tests exercise refusal of changed inputs/corrupt candidates,
ignore an uncommitted baseline PAF, and verify comparison without replacement.


### Completed full-context measurement and stratification

The full candidate job `42681096` and comparison-only job `42685578` both
succeeded. Native 3D finished and its verified leaf checkpoint was retained.
Minimap2 reported **7091.836 s / 125.225 GB** for native, versus
**583.913 s / 18.254 GB** for the full `-f 0.005` candidate: an observed time
ratio of 12.15 on these two x86 nodes, not a full-workflow speedup.
The candidate processed all 113 queries against 988 targets; query coverage
was 99.686%, versus native 99.625%. All PAF names and lengths were checked
against the assignment-checkpoint-bound `metadata/chr_assignments.tsv`.

Unlike the fragment pilots, full-context results are not position-equivalent:
62577/62772 primary grid positions retained an exact position. In particular,
`stratify_full_3d.py` (job `42686656`, succeeded) found:

| Group | Baseline positions | Exact support | Changed/missing positions |
|---|---:|---:|---:|
| Queries >=100 Mb | 28899 | 28861 | 38 |
| Queries <100 Mb | 33873 | 33716 | 157 |
| All baseline MAPQ=60 positions | 62517 | 62417 | 100 |
| >=100 Mb, baseline MAPQ=60 | 28875 | 28857 | 18 |

Quality filtering is applied only to the baseline; a candidate MAPQ decrease
must not be mistaken for a changed destination. Candidate geometry is always
compared without that quality filter. These are baseline-agreement measures,
not ground-truth accuracy. About 80.5% of the sampled position differences were
in queries below 100 Mb, arguing against indiscriminate whole-group filtering.

A next design to evaluate is whole-record routing: approximate only eligible
very long queries and keep the ordinary path for others, preserving record
order, all query records and per-record provenance. An isolated prototype is
now archived below, but it is **not deployed** and has not demonstrated a 12x
speedup or been validated for the
self-alignment path. The already completed native 3D result should be reused,
not replaced merely to install an optimization. No candidate has been adopted.


## Whole-record routing prototype (2026-11-19, not deployed)

`long_query_cross_router.py` routes only eligible complete queries, never final
window fragments. Internal defaults require a query >=100 Mb and target
100 Mb–1 Gb. Three 5 Mb windows calibrate filters 0.005 then 0.001, requiring
at least 1,000 baseline grid positions, <=0.2% position disagreement and
<=0.1% primary coverage loss; these samples do not establish whole-query
accuracy. Failed calibration retains ordinary options. Full candidate primary
coverage below 90% falls back to an ordinary whole-record mapping. Ordinary
records retain their original names, bytes and options. Self alignments are
outside this prototype's scope.

Private mapping caches bind actual input/tool bytes, preset/filter, complete
traversal, CIGAR-valid outputs and successful exit. Probe evidence cannot be
used as a whole-record mapping. The final receipt also binds the preset,
policy and implementation dependencies; changing only resource threads is
not an analysis change. Cancellation does not leave a detached mapper. Any
future main-workspace adoption still requires explicit command/checkpoint
migration and preserving completed native leaves; uploading this file is not
an installation into the main job.

- Initial frozen-runtime validation: job `42701257`, 21/21 tests passed with
  Python 3.10.12 / minimap2 2.31-r1302 on x86.
- Review then found and fixed a missing final-receipt preset binding. Added
  preset-change, dependency-change and multi-index ordinary-fallback tests.
- Local incident suite: 47/47 passed; revised remote router suite: 24/24
  passed at the start of job `42703218`.
- `calibrate_whole_record_router.py` is a separate real-3D validation driver.
  It verifies the completed native leaf, compares three bounded ordinary
  whole records against that result, then calibrates eligible long records
  without remapping those full long records. All products remain outside
  the main analysis workspace. Job `42703218` was running this validation
  at the 05:20 snapshot. The three ordinary-record outputs were subsequently
  verified byte-identical to their completed native counterparts; long-record
  calibration is still running. No main-workspace adoption is claimed.
- Remote evidence: `long-query-router-validation-20261119/` and
  `long-query-router-validation-v2-20261119/`, each retaining its source hashes,
  launch script, logs and submission record.


### Real-data calibration result, 05:21:28 +08

Job `42703218` subsequently **SUCCEEDED**. Three complete ordinary records
(263657, 502552 and 187423 bp) produced byte-identical PAF to the matching
records in the completed native 3D leaf. The only >=100 Mb query,
`ptg000049l` (289508469 bp), admitted filter 0.005 using the unchanged internal
policy: all 1498 baseline sampled window positions had exactly matching
candidate target/strand/position support. One additional candidate position
was absent from the baseline sampling; this is not a claim of identical PAF.
This remains three-window calibration, not whole-record accuracy verification
or a router speedup measurement. No full long-query remapping or main-workspace
adoption occurred. `real-calibration.json`, `final-job.json` and
`wheat-router-v2.sha256` retain the result and frozen-source bindings.


## Explicit resume adapter staged, not activated (05:40 +08)

`routing_resume_support.py`, `resume_with_cross_router.py` and
`stage_routing_commands.py` prepare isolated execution overrides for pending
1D/4D/5D/6D cross leaves. They do **not** rewrite any live workspace command,
helper or task manifest. Current 6A and the 16 completed native cross leaves
are excluded. Initial references, assignment and self mappings keep their
existing execution paths.

The adapter substitutes an isolated script at dispatch, but maps callbacks
back to the original task. Logs explicitly identify both commands. Both the
leaf input identity and q0 outer input fingerprint include the executed
script, frozen dependency hashes and policy. Successful routed leaves also
require a matching final routing receipt and PAF hash; they cannot be reused
as ordinary native leaves. Before any routed leaf completes, its former logs
and existing outputs are copied into isolated attempt evidence.

The frozen outer checkpoint `commit()` constructs a literal base manager.
A naive subclass would therefore fail its final q0 input check. The adapter
preserves that check: it reconstructs a fresh native preparation, adds the
same explicit override, compares against the pre-execution fingerprint and
then atomically writes the success checkpoint. No guard is removed and no
native checkpoint is temporarily published for a routed result.

- Local incident suite: **62/62** passed. Frozen-runtime validation job
  **42706833**: **15/15** binding/dispatch/checkpoint tests passed, including
  actual scheduler subprocess dispatch, changed scientific inputs, changed
  receipts, original-key rejection and preservation of ordinary task keys.
- Remote stage: `routing-resume-staged-20261119/`; plan SHA-256
  `3bf29f170bf27276f19c767b296a0bc082fa86a8ff27c7152d22f10937e2fc00`.
  Shell syntax and all staged source/plan hashes were checked. The entry
  `resume.dsub` has been prepared but **not submitted**.
- This test is not a successful production cutover. First recheck main job
  state, 6A completion, plan exclusions and resources. Do not interrupt 6A
  merely to install this adapter; do not start another analysis concurrently.
- The future entry sets the verified process-local hash cache limit to 8192;
  it does not seed hashes from stored receipts or modify frozen runtime files.
- Rollback before activation is simply to retain the current native entry.
  After routed results exist, reverting to native parameters requires archiving
  the affected routed markers/results and recomputing those selected leaves;
  never relabel approximate outputs as native. Completed native leaves remain
  separate and must be preserved.


### Controlled activation, 2026-11-19 05:58 +08

After native 6A committed at 05:55:39 (17 complete native cross leaves), only
new-run job `42646893` was intentionally terminated. Its lock released normally;
no cache/lock deletion or native result substitution occurred. Job **42710779**
started on `agent-X86-06` through the staged entry, with the same 32 CPU/320 GiB
reservation and original 16-thread global budget. Two initial references were
subsequently verified and skipped. At the 06:02 snapshot, assignment/leaf reuse
verification and first routed execution were still pending. Submission alone
is not evidence that approximation has been used or the workflow has passed.

The frozen App packager exports only initial-reference policy companions, not
these q0 receipts. Final comparison delivery must therefore include a separate,
output-bound q0 routing provenance attachment plus the retained Server audit;
do not relabel q0 routing as the initial-reference policy schema. Main log:
`logs/resume_routed_42710779.out`; cutover backups and scheduler evidence are in
`routing-resume-staged-20261119/cutover-20261119-0555/`.


At 06:09:58 the activation receipt `resume-verified.json` confirmed both
references, assignment and all **17 native cross leaves** were validated and
reused. The first real routed leaf, **5D**, started at 06:08:28. Its baseline
and 0.005 window-calibration mappings had begun; no complete routed 5D result
or whole-workflow success was claimed. Startup-to-first-new-leaf took 10m18s,
including content verification, not alignment time or a controlled speedup.


## Portable q0 routing audit attachment

`export_routing_provenance.py` prepares a separate
`comparison-audit/q0-routing-provenance.json` only after every leaf in the
fixed routing plan has a matching successful marker. It verifies current
PAF/log/receipt bytes, execution bindings, whole-record source selection,
record inventory and effective filters. Source FASTA hashes are explicitly
reported **as recorded in completed checkpoints**, not falsely described as
rehashed by this exporter. Raw attempt paths and private diagnostic strings
are omitted. A full-coverage fallback is reported as ordinary mapping rather
than as approximate simply because a candidate was attempted.

This schema is not initial-reference policy, does not cover self alignments,
and sets `certifies_whole_workflow=false`. It must accompany final comparison
delivery; it is not evidence that the whole wheat workflow has finished.
Publication is idempotent for identical evidence and refuses to overwrite a
different existing audit.

- Local incident suite **71/71** passed; frozen-runtime job **42715067** passed
  **9/9** exporter tests. Its real-workspace gate also correctly refused an
  incomplete four-leaf scope without publishing an audit.
- Frozen exporter/test copies and receipts are under
  `routing-audit-validation-20261119/`. They do not replace any source used by
  the active main job.
- After all planned routed leaves have committed, run on a **compute node**
  with the existing x86 environment (not directly on the login node):

```bash
cd "$HOME/cgat-reads-debug/jm19-compare-614589f-20261118/routing-audit-validation-20261119"
sha256sum -c wheat-audit-code.sha256
python3 -B export_routing_provenance.py --root "$HOME/cgat-reads-debug/jm19-compare-614589f-20261118"
```

At 06:27 the full audit had not been produced. In active 5D mapping, the two
complete long-record candidate mappings (105593624 and 154141050 bp) had
succeeded as one group: minimap2 reported 245.858 s and 14.069 GB peak RSS.
The other 639 records were still using ordinary options. These are group-only
measurements, excluding calibration and ordinary mapping; there is no complete
original-parameter 5D baseline for claiming a speedup multiplier.


## First complete routed leaves and a medium-record counterexample

5D cross committed at **06:36:16**, 27m48s after its routed start. Independent
compute job **42720570** verified its final PAF, receipt, complete record
inventory and saved group outputs. It contains all 641 processed queries:
2 approximate records and 639 ordinary records. Native tool times were
245.858 s for the two long records and 1242.760 s for the ordinary group; these
exclude calibration and wrapper work. The final PAF is 1,023,183 bytes, SHA-256
`0559de26a82882cdebbb287adaabc53bf66a27220463db0efbaf65fd3c7bae13`.

`inspect_routed_leaf_and_length_strata.py` also reused existing complete 3D
PAFs rather than rerunning them. At a 10 kb grid, baseline positions without
candidate target/strand/position support within 100 bp were:

| Original query length | All primary baseline positions | Baseline MAPQ=60 positions |
|---|---:|---:|
| <20 Mb | 51/4925 | 7/4751 |
| 20–50 Mb | 94/9363 | 65/9331 |
| 50–100 Mb | 11/19585 | 9/19560 |
| >=100 Mb | 38/28899 | 18/28875 |

The favorable 3D 50–100 Mb aggregate does **not** justify a blanket threshold
reduction. The diagnostic ran only one additional complete 5D ordinary record,
`ptg000056l` (51,086,554 bp), at filter 0.005, reusing its already completed
native baseline. Candidate time was 126.046 s / 5.143 GB reported peak RSS.
Coverage increased, but baseline-position support was lost at 153/5052 sampled
positions (10 kb grid) and 1543/50532 (1 kb grid), about 3% in both cases.
Extra candidate placements also exceeded the current limits. This is baseline
agreement, **not a measured biological error rate**. Native per-record time is
unknown, so the 639-record group time cannot be used as its speedup denominator.

The candidate did not pass the current full-context quality limits and was not
adopted. The 50 Mb automatic *window-selection gate* was not exercised; do not
claim it has passed or failed from this experiment alone. The main 100 Mb
policy and completed native results remain unchanged. Evidence:
`routing-first-leaf-qc-20261119/{first-leaf-qc.json,length-strata.json,medium-record-study.json,final-job.json}`.
The frozen script SHA was checked after job success.

4D cross subsequently committed at **07:09:47**, taking 33m31s, with one
approximate record and five ordinary records. The main job advanced directly
to 1D, without restart. There are now **19 complete cross leaves** (17 native,
2 routed), not 19 complete outer q0 stages or a completed wheat workflow.
