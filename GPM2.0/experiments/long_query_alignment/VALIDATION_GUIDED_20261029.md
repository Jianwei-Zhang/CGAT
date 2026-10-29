# Whole-query-guided CIGAR recovery, 2026-10-29

## Result and boundary

**The two retained repeat-placement counterexamples are corrected in an isolated
prototype.** All nine bounded comparisons now match the unwindowed baseline's
aligned-base/indel relations and all 29 downstream checks per case. A fresh 270 Mb
run reproduces the original minimap2 assertion, while guided forward/reverse runs
both recover complete 270 Mb query/target coverage with checked CIGARs.

This is not a transparent production fallback. A new real divergent-block decoy
proves that whole-query chain-only selection and final DP selection/MAPQ differ.
The new implementation refuses that case rather than publishing an incomplete
candidate or borrowing provisional confidence. Formal Server, minimap2, native
App and published assets are unchanged; no customer wheat data was accepted.

## Implementation

`guided_alignment.py` is a separate opt-in experiment:

1. Run the existing bounded-query, full-target-index, `-c --eqx` experiment in a
   new child directory. Keep its unfiltered raw/owned/stitched PAFs unchanged.
2. Run an additional **complete original query** against the same verified single
   index with the same assembly preset, without requesting base-level alignment.
   This is provisional chain evidence only, not final PAF for a consumer.
3. Parse and retain every selected whole-query primary/secondary candidate. Match
   each checked stitched CIGAR row to a unique query/target/strand candidate,
   considering both coordinate envelopes and an endpoint-derived diagonal band.
   Reverse-query geometry uses oriented coordinates. All CIGAR vertices, not only
   row endpoints, must stay within the corridor.
4. Exclude a window-only placement only when no whole-query placement supports it;
   retain its full original evidence and exclusion reason. Overlapping but
   unsupported geometry, or multiple compatible owners, **fails** instead of
   selecting a convenient owner. Primary/secondary status is not used to delete
   legitimate secondaries.
5. For **every** selected candidate, require recovered canonical query bases and
   target endpoints. An unrecovered secondary fails too. Requested full-query
   coverage is checked again **after** selection, across every original query,
   not inferred from pre-filter window coverage. Unaligned N/ambiguity
   intervals are explicitly reported, not counted as aligned coverage.
6. Keep final `cg`, verified coordinates/counts, and MAPQ **255 = unknown**. Never
   copy chain MAPQ, chain primary/secondary tags or window DP scores as global DP
   confidence. Chain scores/status remain only in provenance sidecars.
7. Validate input, tool, index and stitched-input identities before finalizing
   `guided.experimental.paf`. Failures retain diagnostics/pending files, but no
   top-level final guided candidate. Existing directories are never overwritten.

The default corridor slack is an **experimental 1,000 bp**, bounded by configured
context. There is no automatic widening or retry. Cancelling large indels whose
internal path leaves this endpoint-derived band are deliberately unsupported;
passing this geometric check is not proof of original chain/DP equivalence.

The auxiliary no-CIGAR output is named `whole-query.chains.paf`. All accepted final
rows still have base-level CIGAR and original-base validation. This does **not**
remove the `-c` evidence requirement or use aggressive `-N`/secondary filtering to
manufacture a pass. `compare_grt.py` and `reproduce_large.py` retain their original
unguided behavior unless `--guide-chains` is explicitly supplied.

## Nine actual downstream comparisons

Command (normal Server toolchain on PATH, same explicit minimap2):

```bash
python3 GPM2.0/experiments/long_query_alignment/compare_grt.py \
  --minimap2 /absolute/path/to/minimap2 --server-dir GPM2.0/server \
  --guide-chains --out /tmp/new-guided-grt-comparison
```

Pinned executable: minimap2 **2.31-r1302**, SHA-256
`b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.
Retained run: `/tmp/cgat-guided-grt-final-20261029`.

| Scope | Prior unguided result | Guided result |
| --- | --- | --- |
| Aligned-base/indel relations | 7/9 equal | **9/9 equal** |
| All 29 downstream checks per fixture | 8/9 equal | **9/9 equal** |
| Two window-only repeat placements | retained incorrectly | excluded using whole-query evidence |
| Two equally good full-reference placements | both retained | **both still retained** |
| Real external-donor patch cases, forward/reverse | accepted | same accepted patches/lineage/DNA |
| Raw metadata bytes | different | still explicitly different |

The 75% extra chr2 assignment is gone in `repeat_assignment_threshold`. The original
unfiltered candidate still contains that placement and still fails the relation
comparison, proving the test was not weakened or the baseline changed. The shorter
repeat control is also corrected. Exact duplication is not used as a reason to
collapse legitimate alternative placements.

These runs retain the previous audit scope: substitute only initial primary
reference PAF, skip same-dataset self alignment, execute unchanged GRT Step1–Step4,
chromosome-local dataset comparisons, evidence finalization and Final Path export.
Independent GRT alignments are not windowed. All comparisons preserve scientific
events, source-card lineage, candidate/rejection/decision tables and ordered DNA;
raw evidence-registry/stage-status differences remain reported separately.
No native App, complex polyploid acceptance or new self-guidance integration was
performed. The separately tested earlier self-alias experiment is unchanged.

## Fresh 270 Mb reproduction

```bash
python3 GPM2.0/experiments/long_query_alignment/reproduce_large.py \
  --minimap2 /absolute/path/to/minimap2 --guide-chains \
  --out /tmp/new-guided-270m-reproduction
```

Retained run: `/tmp/cgat-guided-270m-final-20261029`.

- New deterministic 270,000,000 bp FASTA, original binary, two threads, explicit
  10 GiB per-command address-space limit and 600 second timeout.
- Unwindowed `-c -x asm10`: return code **-6**, same `mm_update_extra` / `qoff`
  assertion reproduced in this run, not inferred from an earlier log.
- Forward and reverse: six raw/owned windows each; strict stitching gives one row;
  one whole-query chain supports that row. Both query and target coverage are
  exactly **270,000,000 bp**. Inputs and binary are unchanged.
- Final CIGAR is `268435455=1564545=` with MAPQ unknown. Each operation remains
  within the internal 28-bit length limit; the text is not re-encoded into
  minimap2/BAM. All represented bases are checked against the original FASTAs.
- Window mapping took 27.479 s forward / 28.688 s reverse; extra whole-query chain
  passes took 20.614 s / 20.473 s. These exclude indexing, generation, spooling,
  hashing and recovery, so **no end-to-end speedup claim** is made.

This proves recovery of the known synthetic mechanism, not the customer's actual
root cause or an 8 Gb wheat production run.

## Real refusal control: provisional candidates are not DP candidates

The added real-tool regression constructs a deterministic 200 kb query, one exact
reference, and a decoy differing only in a 2 kb internal block. Same executable,
preset and input sequences produce:

| Run | Selected targets | Exact-target MAPQ |
| --- | --- | --- |
| Complete-query chain-only pass | exact + decoy | **4** |
| Complete-query `-c --eqx` baseline | exact only | **60** |

The windowed decoy does not recover 1,999 canonical query bases inside its selected
whole-query chain. Guidance therefore stops with `whole-query candidate not
completely recovered`; no `guided.experimental.paf` is created. It neither silently
drops the selected decoy to claim completion nor assigns MAPQ 4/60 to its output.
The earlier raw windowed candidate and complete rejection evidence remain available.

This behavior is an expected fail-closed regression, **not a successfully recovered
case**. It is also concrete evidence that passing a chain-only selection through
as final global DP ranking/MAPQ would be wrong. Upstream v2.31 `map.c::align_regs`
performs base-level filtering and parent/subalignment selection after chaining;
`mm_map_frag_core` then computes mapping quality. The v2.31 manual separately
identifies approximate chain statistics, DP scores and missing MAPQ.

The deterministic fixture is in
`test_guided_alignment.py::RealGuidanceTests.test_dp_split_decoy_is_refused_instead_of_borrowing_chain_confidence`.
Retained real run: `/tmp/cgat-guided-rejection-final-20261029`; corresponding baseline:
`/tmp/cgat-guided-zdrop-survey-20261029/2000`.

## Evidence and checks

- `evidence/guided-grt-comparison.json`: nine reports, all downstream checks,
  per-row exclusions/owners, full candidate-coverage records, raw metadata hashes,
  input/tool/harness fingerprints. Earlier failing unguided receipts are retained.
- `evidence/guided-large-reproduction.json`: fresh baseline abort, forward/reverse
  output PAFs, coverage, command timings and identities.
- `evidence/guided-rejection.json`: actual divergent-block baseline, provisional
  chains, unfiltered CIGARs, uncovered bases and failed publication status.
- **50 experimental tests pass** on real minimap2 2.26-r1175 and 2.31-r1302,
  including 16 new guidance checks. Existing Linux Quality test discovery runs
  these automatically; full 9-case GRT and 270 Mb runs remain opt-in local tests.
- Negative tests cover missing secondary candidates, ambiguous owners, unrecovered
  canonical bases, reverse geometry, cancelling indels, false score inheritance,
  malformed/no-CIGAR rows, tag-like sequence names, changed indexes, and refusal
  to overwrite previous runs. N gaps remain visible rather than declared covered.

## Remaining production gate

No default or published runtime changes are justified yet. The demonstrated
repeat-placement defect is corrected on these fixtures, but whole-query guidance
is only a provisional constraint. Original DP candidate selection/ranking, explicit
unknown-confidence behavior in native consumers, broader structural/repeat cases,
self-alignment integration and customer data still require validation.
Do not weaken the refusal control, fabricate MAPQ, or silently discard unresolved
candidates to make the next benchmark green.
