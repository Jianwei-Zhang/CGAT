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

### Four routed leaves complete; separate self-alignment pilot

By 08:15:30 on November 19, 1D and 6D also committed, bringing the observed
cross total to 21. Independent export job `42737813` succeeded and produced
`comparison-audit/q0-routing-provenance.json` (20153 bytes, SHA-256
`b318e68e3d58de4d1cde3fbba528e440d99baba55b27f2626810f0f3fac1820a`).
It covers only the four routed leaves, not reference or self alignments and
not whole-workflow completion. Include it separately in the comparison delivery.

`full_self_seed_pilot.py` is a **new, isolated diagnostic**, not a self router.
It runs the exact complete 289,508,469 bp query from the live 3D self batch,
with the original cached index, single thread, names and self-specific flags;
only `-f 0.005` is added. It never builds an index or writes to the analysis
workspace and never creates a native completion marker. The live original
batch is the only baseline; no duplicate baseline is launched.

It validates source/tool/index identities, complete traversal, PAFs and source
stability. Timeout/interruption kills and waits for its child; an existing
output directory is refused. Mapping has an 1800-second limit. The ten tests
passed locally and in remote job `42740281`, which was RUNNING at 08:45:41 on
agent-X86-61 (8 scheduler CPUs/80 GiB for memory, one mapper thread).
The complete local incident suite passed 81 tests. Evidence and launch receipts
are under `self-full-3D-pilot-20261119/`; inspect live status before any action.

**No self candidate has been adopted or proven equivalent.** Any future decision
requires a successfully committed native batch and self-specific all-hit/pair
and positional checks. Primary-only cross comparisons or cropped-query window
calibration do not establish preservation of self-alignment evidence.

### Downstream routed-checkpoint reader (installed, execution pending)

The native `q0_preparation._initial_inputs()` creates a separate native checkpoint
manager. It would reject the explicit routed identity even though the running
controller can successfully commit it. `routing_q0_evidence_reader.py` supplies
a read-only manager using the **same frozen routing support**, retaining normal
input/output checks plus receipt validation. It cannot commit alignment markers.
The original scientific builder/policy/identity remain unchanged; the actual
launcher and a reader declaration become explicit evidence inputs. The existing
builder pre-publication check also fences routing dependencies and these inputs.
Unmodified downstream evidence consumers verify the resulting manifest.

Ten targeted tests passed locally and on remote validation job `42741013`,
including an actual frozen-module/plan import without building real evidence.
The whole local incident suite passed 91 tests. On November 19 at 08:57:34,
only the still-pending `prepare_q0_evidence.sh` was atomically replaced; the
running mappings, plan, frozen helpers and checkpoints were not changed and
main job `42710779` was not restarted. Backups, hashes and installation receipts
are in `routing-q0-reader-20261119/`. Real q0 evidence execution remains pending.
See the handoff before rollback: reverting the launcher restores the original
reader incompatibility, and changing it after evidence publication invalidates
the bound inputs of that manifest.

The isolated self candidate job `42740281` has meanwhile **SUCCEEDED**: complete
query mapping took 444.913 s, with Minimap2 reporting 5.073 GB peak RSS. At 08:58
the original native batch was still running. There is no completed-baseline
speedup ratio or self-evidence agreement result yet, and the candidate remains
unadopted. Its secondary/multi-position hits must be included in future comparison.

### Self-specific all-hit comparator and verified candidate inventory

`self_paf_comparison.py` retains **all** PAF hits, including secondary and zero-MAPQ
hits. At each query-grid position / target / strand, it matches distinct target
positions one-to-one; one surviving repeat placement cannot stand in for two
baseline placements even inside the tolerance. Exact duplicate coordinates are
coalesced and counted separately. Exact unions of CIGAR-aligned intervals per
oriented pair additionally expose coverage losses shorter than the sampling grid.
These pair-summed quantities are not genome-unique coverage. The comparison is
baseline agreement, not ground-truth accuracy or exhaustive nucleotide agreement.

`inspect_full_self_pilot.py` launches no mapper and never writes native results.
It verifies the completed candidate's inputs, index, tool/helper, command trace
and all outputs. Baseline comparison additionally requires the correct native
batch key, complete output inventory and hashes, normal full traversal, and
unchanged proof after comparison. A temporary/native PAF without its successful
marker is never accepted. `--candidate-only` explicitly produces inventory only.
Normal comparison reports both 1 kb and 10 kb grids; there is no adoption policy.

Remote job **42744063** succeeded on agent-X86-18 at 09:11:04–09:11:12 on
November 19. It passed **23** comparator/proof tests and validated the actual
candidate inventory without rerunning alignment. Native completion was still
absent, so the output is only
`self-full-3D-comparison-20261119/candidate-inventory.json`:

- 27,451 PAF rows: **24,855 secondary**, 2,596 primary;
- 80 oriented query/target pairs;
- 261,140 distinct sampled placements on the 1 kb grid, with 926 duplicate
  placement observations coalesced.

This measured secondary-hit majority confirms why the cross primary-only check
cannot establish preservation of this self evidence. No baseline agreement or
speedup ratio is available yet. The complete local incident suite passed
**114 tests**. All main-job settings and outputs remain unchanged by this work.

### Bounded full-length/name-preserved masked self probe: not admitted

`masked_self_probe.py` retains the entire query length and original name, index,
self flags and thresholds, but replaces bases outside three fixed windows with
N. The comparator now supports explicit query windows, clips CIGAR intervals
on either strand, and refuses comparisons with different window declarations.
These diagnostic changes are not installed into any active mapper/controller.

The reference side is a bounded native masked-query run; the candidate side is
the already completed **full-query** candidate restricted to those coordinates.
Masking changes chaining context. Therefore this is a local screening experiment,
not a same-input full-context accuracy measurement and not proof that the native
full-query output contains all masked-query hits. There is no adoption logic.

- Three 5 Mb windows: job `42749029` hit the 300-second mapper timeout (return
  code 124, 300.088 s). The owned child was killed/waited; main jobs were unaffected.
  No complete quality result was produced. Evidence: `self-masked-probe-20261119/`.
- Three 1 Mb windows: job **42766357 SUCCEEDED**, November 19 10:56:04–10:58:50,
  mapper 152.966 s; all **45** staged tests passed. Evidence:
  `self-masked-probe-1mb-20261119/native-probe/probe.json` and `final-job.json`.
- The masked native result has 40,533 distinct 1 kb sampled placements, versus
  1,770 in the restricted full candidate; 1,754 match within 100 bp. Thus 38,779
  masked-baseline placements lack candidate support. Pair-query aligned coverage
  also falls from 8,528,353 to 1,164,722 pair-summed bases, with 7,370,642 baseline
  pair-bases missing. Significant pairs disappear. These are not unique genome
  coverage counts or biological error rates.
- Proposed local limits **failed**; no parameters/results were adopted. The
  ~95.67% unsupported fraction belongs only to this different-context experiment,
  not to the pending full-native versus full-candidate comparison. Wait for that
  native commit (or separately control context) before attributing the difference.

The final local incident suite passed **126 tests**. Original full-self pilot,
its committed candidate, original all-hit inspector and the live routed reader
retain their frozen remote copies; do not overwrite those dependency profiles
with these diagnostic extensions.


### Same-input self controls and stratified diagnostics

`self_context_control.py` reuses the completed three-by-1-Mb masked native
probe, including its full query name/length, index, native flags and hash-bound
results. It runs only a filtered variant (`-f 0.005`, `0.002` or `0.001`), with a
300-second mapper limit. No duplicate native mapper is launched. For `0.005`
it also compares the new masked result against the already-completed full
`0.005` candidate in the same windows, separating seed-filter and context
effects. It never adopts a result or writes a native checkpoint.

All-hit comparisons remain available. Additional explicit diagnostic strata
are literal `tp:A:P` rows and rows with alignment block length >=10 kb and
matching-bases/block-length >=95%; neither stratum certifies correctness.
Tests cover immutable-source contracts, command changes, separate filters,
all-hit retention and overwrite refusal. The 2026-11-19 user authorization
permits accuracy/speed tradeoffs, not silent removal of source provenance or
pretending that primary-only evidence represents the entire downstream input.

### Whole-record moderate candidate (not deployed)

`full_self_moderate_candidate.py` runs one isolated `-f 0.001` (default) or explicit `-f 0.002` whole-query
candidate, reusing the earlier f0.005 pilot only as a hash-bound source/index/
command provenance record. It preserves every original self flag, name,
length, query base and cached index. The native batch is not rerun. Output
`candidate.json` has a distinct scope/status and cannot be accepted by the
original f0.005 verifier or as a native batch marker. A 5400-second mapper
limit bounds this single long-query trial; child termination/wait, full
traversal, PAF/CIGAR geometry, restoration and pre/post source hashes remain
required. No source or native complete marker is changed. Future adoption
requires a separately verified explicit self execution profile.

### Explicit self profile execution layer (incident-only cutover)

`self_seed_profile.py` validates an isolated immutable profile over an unchanged
q0-input-bound native manifest. Only selected single-record queries >=100 Mb
receive an explicit `-f 0.001` or `-f 0.005` policy and distinct profile-bound batch keys.
The owning production profile has no diagnostic 90-minute mapper timeout;
isolated pilot time budgets remain separate. Ordinary batch keys
and original manifests stay unchanged. Original tool/index/query/name mapping,
full traversal and PAF geometry remain checked. A receipt binds the actual
command, validated index proof, inputs, outputs and any adopted candidate.

A completed whole moderate candidate can be copied after exact source/output
verification without launching a mapper or restoring names again. Existing
native/unknown completion markers are preserved and cause a request to refresh
the plan, not an overwrite. Profile-aware merging accepts mixed native/profile
batches in original order; the original native merger cannot certify the new
keys. Tests specifically cover a native batch finishing last and corruption of
receipts, index proofs, adoption origins and output files.

The producer/cache/merge layer is complemented by the tested controller adapter
below and by the isolated entry/reader/stager further below. Deployment is always explicit; see the dated handoff for the active job.
The portable combined audit exporter below must accompany final project delivery. Do not invoke it on the live
workspace or cancel a main job just because these focused tests pass. Its owner
must hold the usual workspace lock.


### Self dispatch and outer-checkpoint composition (immutable plan-bound)

`self_profile_bindings.py` replaces only explicitly selected self commands,
restores original task identities in callbacks, verifies/reuses cached batches
without launching the helper or rereading its derived index, and merges once
per operation before its last successful callback. Ordinary batches can finish
last; failed/cancelled groups cannot be published as successful. The adapter
preserves an existing cross-bound checkpoint payload and output identities,
and reconstructs the fresh composed input before publishing an outer marker.

Native-only operations are supported with an empty selection: all native keys
and the original native merge identity remain unchanged. A valid merged native
PAF is not recopied. The eventual planner should include these operations too,
so resume savings are not restricted to the thirteen operations with long
queries. Source/tool/target/output digests remain mandatory; process-local hash
memo entries originate from actual byte reads and recheck inode, size, mtime
and ctime. A same-size alteration with restored mtime is rejected in tests.

Full native-command inventories are verified at initialization/preparation and
the final fresh-input fence, not rescanned across all operations on every child
completion. Callback checks are scoped to their affected operation. Scientific
flags remain unchanged for native-only batches.


### Isolated self entry, combined reader and metadata staging (explicit installation)

`self_profile_context.py` verifies the original frozen cross plan/runtime and
composes self/cross checkpoint identities. `resume_with_self_profile.py` requires
the normal workspace lock and a separately installed, hash-matched reader
launcher; it never accepts a preview plan for execution.
`self_profile_evidence_reader.py` binds extra receipts as actual q0 input files,
not only a descriptive note, and restores its module hooks on failure.
`stage_self_profile.py` generates a new isolated plan covering every planned
self operation, excludes already-native-complete batch markers, and preserves
all original manifest/command files. Final staging requires a completed candidate matching its explicit fraction.
For f0.005 it additionally binds the completed evidence-loss audit; f0.002
cannot silently satisfy either execution policy. A completed native batch wins
over candidate adoption. The f0.005 plan does not recopy the 3D candidate over
its already-complete native baseline.

`self_profile_admission.py` preserves **exclusive execution for all long/fast,
cross and unknown work**. A single low observed RSS does not prove other long
queries safe to overlap. `max_fast=1` cannot be enlarged by the stager; only the
existing native-small two-process allowance remains. This corrects an earlier
isolated preview heuristic which allowed four fast queries based on one peak.
Frozen remote preview directories are not overwritten. The dated handoff
distinguishes previews from the explicitly installed active profile. Reservation numbers are not hard mapper
memory limits.

### Full fast-self evidence audit (no mapping or adoption)

`audit_self_fast_evidence.py` consumes the previously verified complete-native /
complete-candidate comparison receipt and rechecks the actual PAF/marker hashes.
It compares the necessary identity threshold from the frozen workspace's actual
q0 PathPolicy, without dropping secondary or MAPQ-zero alignments. A separate
>=10kb/high-identity diagnostic is not a q0 admission rule. Both exact pairwise
coverage and sampled one-to-one placements are reported.

The sampled query-side ambiguity transition counts cases where several native
maps become one fast map, including opposite strands within the same contig
pair. This catches a risk that coverage-only comparisons hide; it is not a full
q0 uniqueness/admission replay. Reference placement, sequence complexity,
target-side uniqueness and all competing 100bp overlaps remain unevaluated.
The audit never writes workspace outputs or certifies final biological accuracy.


### Authorized aggressive self cutover and portable companion

After the user explicitly accepted greater precision loss for within-assembly
self evidence on 2026-11-19, the incident planner may select f0.005 for unfinished
single queries >=100 Mb. Reference and between-assembly policies are unchanged.
`resume_with_self_profile.py --install-reader` requires the real acquired
workspace lock, an unchanged previous launcher, and absent q0 evidence/reader
declaration. It preserves the old launcher and SHA receipt outside the workspace,
atomically replaces only that launcher, and restores it if installation fails.
It never installs from a preview or steals an active lock.

`self_profile_audit.py` verifies committed merged/self outputs and selected
batch receipts, composes the existing verified cross audit, and exports a
portable companion without private absolute paths. Each approximated query,
actual fraction, result hash and native/executed key is explicit. Run it on a
compute node after q0 alignments complete, using the final plan and an output
outside the workspace; deliver it alongside the finished project. This is not
whole-workflow or biological-accuracy certification.

`inspect_moderate_self_candidate.py` prepares the separate complete f0.001/f0.002
comparison path. It rejects unfinished, timed-out, mislabelled or wrong-driver
candidates and never launches the original mapper. That middle-parameter trial
no longer blocks the explicitly authorized f0.005 self execution.


### Guarded two-lane resource overlay (separate from scientific profiles)

`self_memory_guard.py` verifies a frozen script, opens the verified inode, sets
Linux per-process RLIMIT_AS to at most 64 GiB, disables core dumps, and executes
that script through the open descriptor. Descendants inherit the limit; there
is no added mapper timeout. This is NOT a cgroup or aggregate RSS limit. An
allocation failure is not accepted as a completed alignment.

`self_two_lane_admission.py` permits at most two whole-query f0.005 processes
within the <=300 Mb query / <=800 Mb target envelope. Each lane reserves 128 GiB
for helper/mapper overhead within the existing 320-GiB job. Fast/native pools
are not mixed; cross, unknown and oversized work remain exclusive. Ordinary
native-small eligibility retains the previous 1-Gb target envelope, rather than
accidentally applying the new 800-Mb fast calibration bound to it.

`stage_self_resource_resume.py` copies the original final plan without changing
any scientific profile, original command, selected batch key or cross dependency.
It requires at least two distinct completed production f0.005 queries, rechecks
those output hashes/logged peaks, and emits hash-bound resource wrappers plus a
new reader launcher outside the workspace. Existing completed results are reused;
they are NOT retrospectively claimed to have run under the new memory limit.

`resume_self_resources.py` verifies that resource-only transition and selects
the explicitly bound admission module, then executes the same frozen owning
entry. It preserves the original lock and reader-installation checks. Do not
regenerate the science profiles to change concurrency: doing so would invalidate
already-completed approximate keys. Inspect the dated handoff for the active
resource plan, job and preserved origin plan.

`probe_guarded_minimap2.py` uses synthetic sequences only. On the actual frozen
binary it checks two concurrent 64-GiB-guarded processes against a nonempty,
byte-identical unguarded result; a deliberately tiny 16-MiB subcase must fail
with an explicit allocator error. This validates enforcement/error behavior,
not complete wheat throughput or a guarantee against every source of job OOM.


## 2026-11-19 sub100 self extension (incident only)

The 100-Mb boundary left a 99-Mb native self query running for over an hour.
An isolated same-node `-f 0.005` candidate completed its whole query in 334.302s
(3.835 GB mapper peak), without rerunning the native baseline. This is runtime
calibration, not a completed native agreement comparison or a biological accuracy
claim. The user explicitly accepts greater loss for within-assembly self evidence.

- `extended_self_seed_profile.py` is an explicit versioned sibling of the original
  executor. It selects only unfinished **single-whole-record queries >=10 Mb**,
  keeps `-c`, self-name ordering and the other native flags, and records `-f 0.005`.
  Multi-record batches and smaller records remain native; cross/reference mapping
  does not inherit this precision policy. This is not a shipped global default.
- `composite_self_profile.py` combines the unchanged primary profile with a disjoint
  extension. Primary profiles, completed output bytes, original keys and execution
  scripts are preserved. Per-batch validation uses its actual owning profile;
  only the future aggregate merge binds the composite. Nested composites are
  deliberately rejected rather than silently inventing migration semantics.
- `stage_self_extension.py` verifies the full candidate, source/output identities
  and the parent plan, stages guards/scripts outside the analysis workspace, and
  excludes completed native batches. A native completion racing with staging
  requires restaging; it is never discarded to force the new profile to run.
- `self_extension_context.py`, `resume_self_extension.py`, and
  `read_self_extension.py` explicitly bind the factory/dispatcher and execute the
  original owning entry/reader. They retain the normal lock and checked reader
  installation/backup gate; no frozen source is edited in place.
- `self_extension_audit.py` is the companion exporter for the new plan. It keeps
  **each receipt's actual execution policy/profile SHA**, not the extension policy
  retroactively applied to primary results. Use this exporter, not the old direct
  `self_profile_audit.py`, for a composite plan.
- `run_remote_tests.py` adapts only the cross-router fixture's tools path for a flat
  remote bundle; it does not change test selection or assertions. The first remote
  all-suite invocation failed because `../../../server/tools` does not exist in
  that layout. The explicit-tools rerun passed 237 tests, then verified the actual
  staged controller and reader. Local final validation passed 239 tests, including
  two further portable composite-audit regressions.

The deployed plan still uses two lanes with a 64-GiB **per-process virtual address
space** guard and a 320-GiB scheduler allocation, not an aggregate 64-GiB RSS cap.
Its 444 added selections are not all of the remaining 1320 batches: eligibility
also requires exactly one record. Existing completed results are not relabeled as
having used the extension or its guard. The successful isolated 99-Mb candidate
is bound for verified adoption; it must not be mapped a third time.


## Guarded native concurrency pilot (not deployed)

`native_concurrency_pilot.py` replays exactly four completed native self batches
on an x86 compute node, using the frozen batch helper, mapper, original flags
and eight threads per batch. Query totals are bounded at 20 Mb and targets at
1 Gb. Source manifests, complete markers, original command records, mapper and
input/index content are verified; fast-profile baselines are rejected.

Writable batch, merge and index-cache paths are cloned into a fresh isolated
directory. The main workspace and its completed results are not replaced. Each
helper and its sequential mapper/restore child inherits a 32-GiB per-process
address-space limit from `self_memory_guard.py`; this is not an aggregate RSS
limit. The trial requests 32 CPUs / 320 GiB. Its 1800-second execution budget
is only a diagnostic deadline, never a production timeout.

Acceptance requires successful native helpers, guard receipts, intact source
results, and byte-identical raw and restored PAFs for all four cases. The pilot
does not install a dispatcher, change scientific profiles, adopt outputs, or
certify whole-wheat speedup. Ten focused tests exercise isolation, native key and
source validation, parameter identity, failure handling and actual guard
inheritance with dummy helpers; real mapper acceptance requires the remote trial.

```bash
python3 -B -m unittest discover -s GPM2.0/docs/incident-tools/wheat-20261119 \
  -p test_native_concurrency_pilot.py -v
# Compute node only, with frozen tools selected by the incident environment:
python3 -B native_concurrency_pilot.py --config config.json \
  --output isolated-results --timeout 1800
```

Remote trial `42942033` succeeded on `agent-X86-56` on November 20, 2026.
All four raw and restored PAF pairs were byte-identical to their native baselines.
The four-lane helper execution took 490.524 seconds (510.588 seconds including
staging/verification), with a scheduler-observed peak of 27797 MiB. This is a
controlled replay on a different node from the original results, not a paired
whole-workflow speedup. The production wheat job still uses its prior dispatcher.
