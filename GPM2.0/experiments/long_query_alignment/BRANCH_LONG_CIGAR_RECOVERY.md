# Hypothesis branch: selective long-CIGAR recovery

Branch: `fix/minimap2-long-cigar-recovery`
Base: `988ca4e907da2fd31cf9d5c1c19eeaf696582b10`
Status: implementation only; **no tests or experiments executed** in this phase.

## Authorized objective and constraints

Work ahead of customer feedback assuming a long CIGAR-operation encoding overflow,
without claiming that assumption is the confirmed customer root cause. Keep
minimap2 source/binary unchanged. The eventual Server integration must retain the
existing `run.sh`/`sbatch` interface and must not ask the customer to split FASTA,
write JSON or estimate memory. Do not change master, Release assets, the running
customer diagnostic or existing workspaces.

## First branch slice implemented

`selective_reference_alignment.py` composes the existing window/guidance prototype
with ordinary whole-record mapping for a mixed query dataset:

1. Validate original plain FASTA and retain identities, order and original IDs.
2. Route only queries **longer than 268435455 bp** to the risk path. Length is
   merely a conservative routing condition, not proof of an overflowing operation.
3. Copy complete records to two private files without rewriting case, comments or
   line wrapping. No query record is discarded. When all records are ordinary,
   use the original query file directly.
4. Run ordinary records with the existing `-c -x asm10` command shape; keep their
   PAF row bytes, tags and MAPQ rather than recomputing them from windows.
5. Run risk-only input through existing 50 Mb cores, 100 kb context on each side,
   full-target mapping, base-checked clipping/stitching and provisional whole-query
   guidance. Existing refusal controls remain in force.
6. Validate route ownership, original names/lengths, coordinate bounds and CIGAR
   consumption. Group rows by original query order through disk-backed row files;
   retain candidate multiplicity and explicit records with no alignment.
7. Emit only `reference.candidate.experimental.paf` and a non-production receipt.
   No `result.paf`, success checkpoint or downstream acceptance marker is emitted.

Risk rows keep unknown MAPQ and must not carry recovered `AS/ms/s1/s2/tp` claims.
Ordinary rows retaining native tags does not establish equality of the whole mixed
workflow. `guided.experimental.paf` is still a conditional diagnostic candidate.

The default CLI is **plan only**, creating nothing and starting no tool. Its
`--execute` switch is for a developer's final-validation harness, not a new customer
`run.sh` option. This branch has not connected the prototype to Server `run.sh` yet.
That is deliberate until the correctness gates below are resolved, not an assertion
that the branch is a working customer repair.

## Original multipart reference context: implemented, execution unverified

`minimap_index_context.py` reads the pinned v2.31 MMI2 serialization: metadata
contains original record membership, followed by bucket and sequence payloads.
The reader skips payloads with bounded metadata reads and checked extents. It
checks little-endian format, supported flags, record IDs/lengths/order, partition
boundaries, file identity and byte hashes. Missing target sequences/names, HPC,
unknown format/flags, duplicates, truncation or a foreign context are refused.

For risk-query experiments, build the reference index with the normal `asm10`
**default partition policy** (no `-I` override). Copy each serialized part
byte-for-byte into a private index file; do not guess FASTA chunk boundaries or
re-index subsets. Pass that same verified part to both whole-query guidance and
window mapping. Verify its hash again between/after the passes. The legacy
standalone single-index experiment remains available; it is not silently used
for the customer's multipart context anymore.

An additional upstream state must be preserved: v2.31 `mm_mapopt_update` computes
`mid_occ` on the first index part only while its value is unset; subsequent parts
retain it. Independent part invocations would otherwise recalculate it and could
change seed filtering. The branch takes the shared value from the ordinary
multipart mapping log when available; with risk-only input, it runs a chain-only
pass against the first original part. Both window and whole-query guidance pass
that measured integer via `-f`, after the preset. This is preservation of original
filtering state, not a parameter-workaround sweep or an arbitrary new threshold.
Missing, inconsistent or out-of-range threshold evidence is refused.

The selective driver records each original part and keeps part/query ownership
when combining rows. A normal-only run preserves native PAF order byte-for-byte;
a mixed run uses original part-major order followed by original query order,
not query-major concatenation across parts. A row cannot migrate to another
part's target. Original target records/order and reference bytes are unchanged.

A part with both no whole-query candidates and no window rows may be recorded as
no-hit. A disagreement remains a refusal. If every part produces no risk-query
candidate, the driver still refuses rather than presenting empty recovery as a
repair. The ordinary standalone empty-output refusal is unchanged.

**This addresses index-context handling, not MAPQ or candidate reconciliation.**
No global MAPQ is fabricated from part-local output. The added implementation and
its deferred tests have not run, and a real large-reference equivalence run is
still mandatory before delivery. This does not prove the customer's job will fit
its memory/time/disk allocation.

## Remaining work before a usable branch build

- Execute pinned-MMI format/part-reuse validation and real default-index context
  comparisons on representative large references; context handling is implemented
  but not yet execution-validated.
- Full post-DP candidate completeness, parent/secondary decisions and MAPQ; coarse
  guidance and an AS threshold are not replacements. The known decoy counterexample
  must continue to refuse until correctly handled.
- Boundary conflicts, long target-only deletions, repeats and complex split events.
  A short query window does not bound every possible target-consuming CIGAR op.
- Server command generation/runtime bundling and correct nonzero-exit/checkpoint
  handling, only after there is an accepted recovery result to publish. The branch
  must not quietly run GRT on diagnostic candidates with unknown semantics.
- End-to-end original workflow/scientific acceptance once customer feedback arrives.

## Deferred validation

`test_selective_reference_alignment.py` defines routing-boundary, raw-record copy,
normal-record command, byte-preserving PAF merge, bad provenance/span/confidence,
plan-only, fresh-output, original index-part ownership/order and normal-only native
row preservation cases. These have **not run**, including
mock-only checks. Old validation receipts do not certify the newly added code.

Additional deferred modules:

- `test_minimap_index_context.py`: MMI2 boundaries, raw-part copying, metadata/payload
  truncation, flags, duplicate IDs, reference ordering and context/hash binding.
- `test_original_index_part_guidance.py`: same part reused across both passes,
  explicit no-hit part, disagreement refusal and unchanged standalone empty guard.

Final testing also needs real mixed ordinary/long synthetic inputs, both strands,
normal-only output comparison, index-part cases, retained decoy negative controls,
and the existing assignment/GRT/Final Path comparisons. Customer localization and
whole-record replay precede asserting any customer-specific root cause or repair.

## Delivery gate status

- Original multipart index bytes, membership, shared first-part threshold and
  emission order: implemented; static syntax/diff reviewed, execution deferred.
- Ordinary-only native PAF preservation: implemented; execution deferred.
- Post-DP candidate selection and global MAPQ: still incomplete.
- Transparent `run.sh` integration, distributable branch package and rollback:
  still incomplete; no official Release refresh is authorized by this branch work.
- Final automated/scientific validation: deferred under the existing user request.
- Customer-specific root-cause and complete-workflow acceptance: not established.

A source commit is progress toward delivery, not a claim that all delivery gates
are met. No test result or production readiness is asserted for this increment.


## Window candidate pool and native selection core: implementation only

The selective branch now requests an internal `all_chains_pool` window policy.
Only the short-window mapping command adds native `-P`; the ordinary whole-record
route and preliminary whole-query guidance do not. Existing standalone defaults
also do not change. This avoids pruning competitors solely by each window's
primary/best_n decision. It does NOT prove full-query candidate completeness:
local chaining, seed filtering, DP extension and global ranking-score correction
can still differ. The raw pool is never final PAF or accepted downstream evidence.
All base checks, coordinate restoration, core ownership, reciprocal-unique
stitching, and guided coverage/corridor refusals remain in place.

`post_dp_selection.py` implements the pinned v2.31 **post-skeleton** hit sort,
query-overlap parent assignment and secondary selection for the ordinary asm10
single-query/index-part case. The module does not parse window PAF into native
state and is deliberately NOT wired into the recovery output yet. Its boundary:

- Require complete explicit original state after skeleton filters and optional
  `mm_update_dp_max`, before native hit sorting. No guessed AS/ms/cm/hash or zero
  defaults for missing pre-DP subsc/n_sub/dp_max2.
- Sort by native corrected dp_max and original hash. Port the original radix
  partition order, including hash ties above its 64-record insertion-sort limit;
  Python stable sort is not silently substituted.
- Determine parent competition using query overlap and UNION coverage of current
  primaries, across target IDs/strands. Preserve native strict mask inequality,
  float32 comparison steps and first-primary versus later-primary counter reset.
- Preserve upstream differences between identical-DP-hit exclusion when updating
  dp_max2 and identical-coordinate exclusion when retaining secondary rows.
- Apply native chain-score ratio OR absolute score difference, with a single
  query-wide best_n=50 count, then synchronize retained parent IDs. No AS cutoff.
- Emit a structured selection receipt only, not PAF, native confidence or MAPQ.
  Keep `production_ready:false`, provenance/completeness unproven and execution
  validation explicitly false.

Pinned official source hashes are embedded for hit.c/map.c/options.c/misc.c and
ksort.h; the upstream MIT notices accompany the port. **No minimap2 implementation
or installed binary is patched.** `post_dp_native_oracle.c` is only a deferred
verification harness linking a PRIVATE build of unmodified upstream sources. It
calls native selection functions without running alignment or altering that tool.

### Deferred final-validation checks (NOT run during implementation)

`test_post_dp_selection.py` includes deterministic cases for the score-decoy,
coverage union, different targets/strands, first/later-primary prior counters,
identical/nested DP geometry, seed-count/DP competition, query-wide best_n, small
sort ties and binary32 large-score comparisons. The optional native-source oracle
covers 0/1/2/63/64/65/100/257/600 candidates, large ties, both strands and prior
state. Enabling that oracle will compile a fresh private source copy; it requires
an explicit maintainer-provided `CGAT_MINIMAP2_NATIVE_SOURCE` path and must wait
for the user-authorized final validation phase. This is NOT customer configuration.
The original-index guidance checks also cover pool flag isolation, legacy default
preservation and continued refusal of chain/window disagreement.

Writing these cases and statically parsing Python is NOT a passing test result.
Do not infer an upstream-equivalence or customer-repair claim from this commit.

### Remaining delivery gates

1. Establish all original candidate/anchor ownership and the actual split/trim
   state, retaining global native scores and pre-DP parent metadata; handle native
   DP rejection without demanding fictitious canonical coverage.
2. Reconstruct and validate native post-skeleton ranking-score adjustment before
   supplying state to the new selection core; raw all-chain `ms` is insufficient.
3. Reconstruct/verify whole-query MAPQ, including repetitive length and primary
   competitors; never inherit window MAPQ or mark unknown as high-confidence.
4. Connect only the validated reference-alignment path to the existing run.sh/task
   entry, with atomic final output and original workspace/checkpoint protection.
5. At final validation, execute the deferred native oracle and small/large/normal
   controls, then GRT/Final Path comparisons. Customer localization and the real
   full run remain a separate acceptance gate. No new run.sh flags or manual
   splitting/configuration should be required from the customer.


## Full recovered-path statistics and rank adjustment: implementation only

`whole_query_scores.py` now supplies the score/statistic part of the earlier
selection-state boundary. It reads the **complete recovered path** against
original query/target bases, with at most a 1 MiB sequence fetch per side:

- Base-check =/X on either strand; reproduce native mlen/blen/nn accounting,
  including IUPAC-as-N, insertion/deletion ambiguity and negative ambiguous-base
  scores. Recover the zero-reset local maximum `dp_max0`, without trusting any
  window AS/ms/cm/s1/MAPQ. No AS claim is produced.
- Coalesce adjacent textual pieces of one logical operation with Python integer
  lengths. A serialized >268435455 bp exact run is never encoded into minimap2's
  internal CIGAR, and a gap split across ownership/text boundaries is charged
  only once. Whole-query scoring is not the sum of window scores.
- Port the pinned binary32 `mg_log2` approximation and asm10 gap penalties, not
  math.log2. Preserve ambiguous-base ordering within matches and the native
  truncation model. Refuse unsupported leading-gap normalization, false =/X,
  inconsistent coordinates/counts or native field/arithmetic overflow.
- Implement `mm_update_dp_max`'s query-coverage/runner-up gates, first-equal-best
  convention, event-identity reference, global mismatch/gap factor and corrected
  scores over a caller-supplied **first-filtered** query/index-part candidate set.
  Original anchor counts and that set's completeness remain mandatory separate
  provenance. Mixed or unbound original index parts are refused. This function does NOT discover or certify that set.

The selective branch internally enables `recover_path_scores` (no customer CLI
flag). Guided recovery writes `guided.path-scores.jsonl` before its final private
candidate is promoted, and records the sidecar hash, PAF source hash, input hashes
original index-part hash and implementation identities in guidance.json. Existing normal records and legacy
standalone defaults are unchanged. Sidecar scoring failure prevents candidate
promotion; it cannot bless a partial/incorrect result. The PAF itself still has
unknown MAPQ and no invented native score/type tags.

**Global correction is deliberately NOT applied automatically to the provisional
guided set.** Original anchor ownership and post-DP filtering are not yet proven;
pretending that the set already passed those gates would supply wrong competitors
to ranking. The new functions are score-state implementation, not a bypass of the
existing guided refusals or an assertion of complete whole-query DP equivalence.

### Original chain-state evidence boundary

Pinned map.c/hit.c show that the native hash uses encoded anchor data, including
seed flags; the CN columns currently collected do not print all those bits. It is
not sound to hash just the printed coordinates, to hash window names, or to set
missing pre-DP subsc/n_sub to zero. Remaining work must acquire that state without
changing minimap2, then bind it to actual recovered paths/splits and the new score
outputs before connecting the post-DP selector. No conditional hash guess has
been added to make the branch appear complete.

### Deferred validation additions (none executed)

- `test_whole_query_scores.py`: competing exact/decoy/deletion paths, global
  correction, ambiguity, local resets, gap coalescing, different read-chunk sizes,
  reverse orientation, a >28-bit virtual exact path with bounded reads, native
  threshold/source-identity guards, invalid paths and immutable sidecar input.
- The optional native oracle now includes the **unmodified** pinned align.c only
  in its isolated test translation unit. It can call native static score logic
  and public rank correction without patching/rebuilding the installed minimap2.
  It verifies normalized controlled paths and rejects any oracle input whose
  native normalization changes its coordinates or CIGAR. This is not an aligner.
- Native-source checks compare mlen/blen/nn, local and globally corrected scores,
  event identity, forward/reverse gaps and ambiguous bases. The native source hash
  pins now also cover align.c. Compiler/FMA behavior of the actual pinned tool
  remains a final-oracle acceptance concern, not a claimed bitwise result.
- Original-part guidance mock checks now include binding the path-score receipt
  to the unchanged private PAF; neither AS nor MAPQ is silently promoted.

All these are written, not passed tests. No minimap2 execution, native build,
customer job, downstream run, formal result.paf, Release artifact or new customer
configuration was produced by this implementation increment. Final automated and
scientific acceptance, original-chain-state recovery, MAPQ, transparent run.sh
integration and customer acceptance remain open.
