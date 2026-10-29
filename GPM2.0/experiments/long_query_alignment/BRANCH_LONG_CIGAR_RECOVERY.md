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

## Immediate unresolved gate: the customer's multipart reference

The current guided prototype explicitly constructs one full-target index, whereas
the customer evidence indicates a default multipart target index. For risk-query
runs whose target exceeds the pinned default index budget, this first branch slice
refuses **before mapping** instead of silently increasing `-I`, partitioning targets,
combining independent part-local confidences, or calling that equivalent.

Consequently this first slice is **not yet capable of accepting the full customer
wheat reference**. Next development must decide and validate a target-index contract:
original ordered index-part evidence with correct global reconciliation, or an
explicitly verified full-reference index approach. This cannot be solved by merely
concatenating part PAFs or copying their MAPQ. Do not return to a general memory
scheduler project to address it.

## Remaining work before a usable branch build

- Target-index/candidate context for the actual large reference.
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
plan-only, fresh-output and multipart-refusal cases. These have **not run**, including
mock-only checks. Old validation receipts do not certify the newly added code.

Final testing also needs real mixed ordinary/long synthetic inputs, both strands,
normal-only output comparison, index-part cases, retained decoy negative controls,
and the existing assignment/GRT/Final Path comparisons. Customer localization and
whole-record replay precede asserting any customer-specific root cause or repair.
