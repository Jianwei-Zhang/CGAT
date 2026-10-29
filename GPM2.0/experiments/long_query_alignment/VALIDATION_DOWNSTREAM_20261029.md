# Long-query windowing: downstream and self-alignment audit, 2026-10-29

A subsequent provisional-guidance implementation is measured in
`VALIDATION_GUIDED_20261029.md`. The failing unguided results below remain intact;
they are not retroactively counted as successful guided runs.

The MAPQ consumer inspection below describes the original audit snapshot. The
subsequent App-only sentinel fix and score-provenance work are documented in
`VALIDATION_POST_DP_20261029.md`; this does not enable guided Server integration.

## Decision

**Do not integrate the current windowed PAF as a transparent Server fallback.**
Real downstream runs now exist, including accepted donor patches, but a deliberate
repeat fixture changes chromosome assignment. A separate MAPQ sentinel hazard
also remains. Neither is solved by successful coordinate/CIGAR stitching.

This change adds only isolated experiments, tests and evidence. It does not alter
minimap2, Server production code, its parameters, published source, installers or
customer workspaces. No customer wheat input or native App was tested.

## Reproduction and scope

- `compare_grt.py`: 9 deterministic 800 kb-scale fixtures, each with independent
  baseline/candidate workspaces. Core 200 kb, context 10 kb, two threads.
- Both initial mappings use real minimap2 `-c --eqx -x asm10`. Baseline uses the
  complete query; the candidate restores and stitches bounded query windows.
- Only the primary dataset's initial reference PAF is substituted. Each workspace
  has `EXPERIMENTAL_SUBSTITUTION.json`; generated reference commands are not
  falsely marked as executed and `run_all` checkpoints are not forged.
- Actual unchanged generated scripts execute assignment, GRT preparation,
  Step1, Step2, Step3, Step4/telomere, chromosome-local dataset comparisons,
  evidence finalization and Final Path FASTA export. Same-dataset self alignment
  is explicitly skipped here and audited separately below.
- GRT's independent flank/candidate/telomere minimap2 commands and MUMmer work
  remain unchanged. Donor-vs-reference commands, when applicable, also run
  normally in both variants. No input/cache reuse between variants.
- These are **not** whole-Server windowing integration or native import tests.
  In particular, current default Step1 can genuinely record upstream no-op
  events; executing its script is not evidence of accepted Step1 gap filling.

Pinned real tool: minimap2 **2.31-r1302**, SHA-256
`b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.
The normal local `cgat-server` environment supplies samtools and MUMmer.
Run commands are in `README.md`; both scripts reject existing output directories.

Authoritative retained local outputs:

- `/tmp/cgat-windowed-grt-contract-20261029`
- `/tmp/cgat-windowed-self-contract-20261029`

Small committed receipts:

- `evidence/grt-downstream-comparison.json`: all 9 summaries, 29 checks per case,
  exact raw-metadata hashes, actual negative-control PAF/assignment contents,
  input and harness hashes. Failed checks include their actual compared values.
- `evidence/self-comparison.json`: three real self comparisons and negative controls.

Earlier probe/audit directories remain separate. In particular, the first GRT
probe failed because the test harness omitted `tool_version.txt`; the harness
now captures the actual binary version. A Unicode-ID self probe was rejected by
the existing ASCII-only experimental FASTA store. Neither failed probe is counted
as successful acceptance or concealed as a production bug.

## Results: downstream

| Fixture | Initial aligned-base/indel relations | 29 downstream checks | Accepted final actions |
| --- | --- | --- | --- |
| identity | equal | equal | none |
| reverse_indel | equal | equal | none |
| gap_with_donor | equal | equal | filter_component |
| reverse_gap_with_donor | equal | equal | filter_component |
| competing_targets | equal | equal | none |
| local_repeat_competition | **different** | equal | none |
| repeat_assignment_threshold | **different** | **assignment differs** | none |
| gap_with_external_donor | equal | equal | patch |
| reverse_gap_with_external_donor | equal | equal | patch |

- 7/9 initial relationship comparisons match; 8/9 downstream check sets match.
  The additional repeat mappings are real differences, not row-order or ID noise.
- All 9 pairs retain matching ordered Q0–Q4 DNA and Final Path source intervals,
  kinds, orientations and DNA for these fixtures. Each independently exported
  Final Path also matches its own Q4. This does **not** waive assignment differences.
- External-donor cases really accept one Step2 patch each, with matching decisions,
  donor intervals, source-card lineage and resulting DNA, including reverse query.
- In the same-dataset `gap_with_donor` cases, the extra record enters Q0 rather
  than D0; the accepted action is component filtering, **not a successful fill**.
- No accepted telomere extension, complex structural correction or customer-like
  polyploid repeat topology has been established by this matrix.

The comparator retains strict raw metadata results separately: all cases have
raw differences in `grt_evidence_registry.tsv` and `grt_stage_status.tsv`.
These are never relabeled byte-identical. Scientific comparisons omit explicitly
named generated trace identities; complete ordered event semantics retain all
other fields, including covered GAPs/output intervals and future event fields.
Q paths retain source-card lineage; donor/role tables and Step2/3 candidate,
rejection, interval and decision tables are also compared strictly. Unit tests
ensure altered source intervals, DNA, cross-gap coverage or provenance do not
vanish under the comparison.

## Concrete blocker: repeat competition changes assignment

The negative control contains:

- `chr1`: all 800,000 bp of the deterministic query;
- `chr2`: the first 600,000 bp of that same sequence;
- query: the full 800,000 bp.

Whole-record minimap2 outputs only the chr1 placement. The windowed result adds a
600,000 bp chr2 placement. Actual CGAT assignment then changes from:

```text
assembly query -> chr1, support 800000, 100.000%
```

to:

```text
assembly query -> chr1, support 800000, 100.000%
assembly query -> chr2, support 600000,  75.000%
```

The reference/default comparison is not weakened to accept this. The fixture is
now a lightweight **negative regression**: successful windowing and full query
coverage must not be confused with whole-contig placement equivalence. The second
repeat control adds a 400 kb placement but does not cross the assignment threshold;
it still fails the initial relation comparison.

These observations demonstrate the need for whole-contig candidate competition,
not a coordinate arithmetic fix. Deleting secondary candidates, lowering their
scores arbitrarily or using more aggressive filtering would hide the symptom
without establishing correctness.

## Confidence audit

The upstream minimap2 v2.31 `minimap2.1` defines PAF MAPQ=255 as missing, not high
confidence. Its `-X` option combines no-dual/no-diagonal/all-chain behavior; both
contracts were checked against that version's manual/source.

Current local call paths:

- `server/tools/grt_prepare_inputs.py` parses MAPQ from the initial reference PAF,
  but assignment/primary selection use coverage/footprints and ordering, not that
  MAPQ value. This explains why equal DNA in the simple fixtures is insufficient.
- `grt_core/step2_engine.py::best_validation_alignment` applies a numeric MAPQ
  threshold, but reads **independently computed candidate-flank validation PAF**,
  not the initial reference PAF. This experiment leaves that command untouched;
  it does not claim the initial substitution already contaminated Step2 scoring.
- `app/backend/src/alignment_cache.rs` imports `runs/<dataset>_vs_ref/result.paf`
  and persists its MAPQ unchanged; `contig_split/mod.rs` then loads that value and uses
  `mapq >= 20` for high-quality coverage/recommended fragments. Thus promoting the
  experimental reference PAF to normal App input without an explicit missing-value
  contract is unsafe. This is source inspection, not native App execution.

The duplicated-target fixture illustrates the numerical trap: baseline has two
MAPQ=0 rows (one primary and one secondary); the stitched experimental PAF has two
unknown=255 rows and no inherited primary/secondary labels. A plain `>=20` counts
both as high quality, while the explicit known-MAPQ count is zero. The receipt
preserves both counts; no invented replacement score is used.

## Self-alignment audit

`compare_self.py` uses the production `write_self_pair_inputs` alias generator in
an isolated directory. A query window retains the original ranked query alias
before its suffix: `gpm_pair_000000001b_w...`. This preserves the ordering against
all target `...a` aliases. Raw and restored rows must obey the original unordered
pair direction; same-record, reverse-dual and unknown-name rows fail validation.

Three real 120 kb-scale cases cover non-natural lexical names (`ctg10`/`ctg2`),
permuted FASTA order, reverse orientation and a boundary-crossing insertion:

- Original whole-record runs: three rows, all three expected unordered pairs.
- Windowed runs: 12, 12 and 13 raw rows respectively, each stitched to three rows.
- All pair/strand sets and aligned-base/indel relations match their baseline.
- Negative control with ordinary `gpm_window_*` names returns **zero rows** in all
  three cases under `-X`; it is explicitly not a successful workaround.

This is a separate audit utility, not an enabled self-alignment fallback. Complex
repeats and global scoring equivalence are still unverified.

## Automated checks and next gate

- 34 lightweight experimental tests pass with real minimap2 2.26-r1175 and
  2.31-r1302, including the new real repeat negative regression and all three
  self comparisons. Existing Linux Quality discovery picks these up automatically.
- Existing Server Python regression suite: **375 tests passed** in the normal
  local Server environment. No native App/browser validation was run.
- Full GRT comparisons require the normal Server toolchain and are opt-in; the
  lightweight CI suite must not be represented as rerunning those 18 workspaces.
- The main prototype, experimental output markers and fail-closed behavior are
  unchanged. No production source asset refresh is appropriate for these files.

Next work should address whole-contig candidate competition before any integration,
then define and verify missing-confidence handling in all affected consumers.
A possible **unvalidated research direction** is to preserve complete-query
candidate evidence and use bounded base-level alignment only for CIGAR recovery.
Mapping-only output is not an acceptable final replacement for required `-c`
evidence, and approximate chain scores must not be passed off as original DP MAPQ.
First pass the retained negative repeat controls; then expand structural/polyploid
and self cases, native consumers and the customer's diagnostic bundle/data.
