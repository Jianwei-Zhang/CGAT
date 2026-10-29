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
