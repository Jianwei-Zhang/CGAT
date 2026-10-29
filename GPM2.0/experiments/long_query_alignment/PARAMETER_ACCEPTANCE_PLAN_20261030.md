# Parameter-only workaround acceptance plan — execution deferred

## Existing evidence

The prior 270 Mb deterministic self-alignment audit used the unchanged minimap2
binary and included default `asm10 -c`, `--eqx`, smaller query/index batches,
`--no-long-join` with a narrower band, `asm5`, extreme Z-drop, SW-memory cap and
`--max-qlen`. It did not establish a universal parameter-only repair. In
particular, output omission via a query-length cap cannot be relabeled as success.
Do not rerun that matrix merely to obtain a different timestamp.

## Missing acceptance dimension now implemented

`compare_parameter_controls.py` is a final-phase harness for **normal inputs**. It
runs each mechanism-motivated candidate over the existing boundary, reverse,
indel, ambiguity, repeat, inversion and duplicated-target fixtures using `-c
--eqx`, then compares against default `asm10`:

- complete aligned-base/indel coordinate relations;
- row count and pair/strand multiplicity;
- query coverage per pair/strand;
- MAPQ histogram and unknown-255 count;
- primary/secondary type tags;
- exact row multiset including CIGAR and confidence.

A candidate that changes any of these remains ineligible for a customer contrast
unless the difference is separately justified by the intended contract. A
candidate that skips the query or returns an empty PAF is disqualified regardless
of exit status. Passing normal controls only permits evaluation on the controlled
long assertion; it does not accept a workaround.

The harness and `test_parameter_controls.py` have been implemented but **not
executed** under the user's deferred validation instruction. It creates only a fresh synthetic output directory and
never reads customer FASTA or submits a cluster job.

## Final phase sequence

1. Run the full experimental unit suite on unchanged minimap2 2.26 and 2.31.
2. Run `compare_parameter_controls.py` on both versions and retain raw PAF/logs.
3. Review prior 270 Mb evidence. Re-run only if source/tool contract changed or a
   genuinely new mechanism-based candidate was added.
4. For a candidate that both preserves normal controls and completes the long
   case with nonempty full-query CIGAR output, compare its relations against the
   independent checked-window diagnostic. That comparison is evidence, not an
   oracle for candidate ranking/MAPQ.
5. Run the existing synthetic GRT/Final Path and self-alignment comparisons.
6. Only after customer query localization and independent failure reproduction,
   run one explicit selected-record contrast. Do not automatically cycle through
   parameters on customer data.
7. Require complete PAF, coordinates, strands, CIGAR, candidates, accepted/rejected
   repair decisions, resulting DNA and Final Path before calling it fixed.

`--eqx` itself changes CIGAR representation and was already tested in the long
matrix; it is used in normal controls to make base/indel relations unambiguous,
not claimed as a repair. Resource scheduling is outside this customer-issue scope
and cannot turn a scientifically different parameter result into an accepted one.
