# Long-query windowing experiment — 2026-10-29

## Result and boundary

**The known 270 Mb synthetic failure is bypassed by a functioning prototype,
without modifying minimap2 or omitting query bases. This is not customer or
whole-GRT acceptance, and no production defaults or Release assets changed.**

- Unmodified `minimap2 2.31-r1302`, Linux x86_64.
- Executable SHA-256: `b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.
- Deterministic 270 Mb FASTA SHA-256:
  `0fbc225dfa32c1e4e99ed4cfb611f5023768423fbc5c4f6ec789342aff1e6fc4`.
- `reproduce_large.py` was run end to end, including a fresh unsplit baseline.
  The baseline terminated by SIGABRT (`-6` in Python) with the exact
  `align.c:301: mm_update_extra` query/target-span assertion. It was not an OOM
  or an intentionally skipped query.
- Windowed mapping retains `-c`, uses explicit `--eqx` for base-level checking,
  and aligns against the full target. Core=50 Mb, context=100 kb per side,
  two mapping threads, 10 GiB address-space cap, 600-second per-command timeout.
- Large synthesis, preparation, hashing and recovery time are **not** included
  in the mapping-only times below; no general performance claim is made.

## 270 Mb results

| Strand case | Query union, bp | Target union, bp | Owned rows | Stitched rows | Mapping seconds | Peak mapping RSS, GiB-like minimap2 log value |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| plus | 270,000,000 | 270,000,000 | 6 | 1 | 28.639 | 2.411 |
| reverse | 270,000,000 | 270,000,000 | 6 | 1 | 29.896 | 2.411 |

Both outputs recover original query identifiers, lengths and global coordinates.
Every raw and retained `=`/`X` operation is checked against source bases, and
CIGAR consumption equals both query and target spans. The current Server
`validate_paf(require_cigar=True)` accepts all 6 owned rows and the 1 stitched row
for each orientation. This is parser compatibility, **not downstream acceptance**.

The stitched logical match is emitted as `268435455=1564545=`. Each individual
CIGAR numeric term remains within the 28-bit boundary; the complete alignment
is represented externally in PAF text, never encoded back into minimap2 or BAM.
MAPQ remains unknown (`255`); original global scores and primary/secondary status
are not invented.

Evidence: `evidence/large-reproduction.json` contains actual commands, executable
and input identities, raw failure log, successful logs, coverage, recovered PAF
rows, and source-file SHA-256 values. Large inputs/indexes are not tracked.

## Eleven bounded comparisons below the original length limit

These cases use 2 Mb source DNA, 500 kb cores and 10 kb context. Each has an
unsplit real-minimap2 baseline and new synthetic CGAT workspaces for actual
`prepare.sh` + `assign_chr_groups.sh`; no full GRT run is started.

The relation comparison preserves exact query/target positions, strand,
mismatch and indel placement, while allowing a path to be represented by multiple
rows. It does not relabel changed paths as equivalent. Assignment comparison
includes orientation, support bases/percent **and anchor_start**, not just chromosome.

| Case | Query length | Covered query | Stitched base/indel relations | Owned-only assignment | Stitched assignment |
| --- | ---: | ---: | --- | --- | --- |
| `identity` | 2,000,000 | 2,000,000 | PASS | PASS | PASS |
| `reverse` | 2,000,000 | 2,000,000 | PASS | PASS | PASS |
| `insertion_across_core` | 2,002,048 | 2,002,048 | PASS | DIFF | PASS |
| `deletion_at_core` | 1,997,000 | 1,997,000 | PASS | DIFF | PASS |
| `mismatch_at_core` | 2,000,000 | 2,000,000 | PASS | PASS | PASS |
| `ambiguous_across_core` | 2,000,000 | 1,999,600 | PASS | PASS | PASS |
| `repeat_deletion_at_core` | 1,999,970 | 1,999,970 | PASS | DIFF | PASS |
| `inversion_at_core` | 2,000,000 | 2,000,000 | PASS | PASS | PASS |
| `duplicated_target` | 2,000,000 | 2,000,000 | PASS | PASS | PASS |
| `reverse_insertion_across_core` | 2,002,048 | 2,002,048 | PASS | DIFF | PASS |
| `reverse_deletion_near_core` | 1,997,000 | 1,997,000 | PASS | DIFF | PASS |

The ambiguous-base case intentionally has a 400-base N interval that is unmapped
by **both** pipelines. It is reported as 1,999,600/2,000,000 coverage, not falsely
claimed as 100% or silently filled.

### A real integration issue caught and addressed in the prototype

Owned-only split rows changed CGAT's weighted anchor selection despite identical
base relations. For example, the insertion case shifted `anchor_start` from `1`
to `-2047`; deletion moved it to `3001`, and the homopolymer deletion to `31`.
The reverse-strand indel cases exposed the same issue.

Reciprocal-unique, exact query-and-target adjacency stitching recovered the
baseline assignments in all eleven comparisons. No gap was bridged, no different
placement was dropped, and the inversion/N-gap paths retained their distinct
segments. This is why coordinate lifting alone must not be shipped as a fix.

Evidence: `evidence/small-comparison.json` retains the **owned-only differences**
alongside the stitched results, input hashes, relation signatures and original
assignment rows. No differences were hidden by weakening the comparison.

## Automated checks

- 24 tests passed locally with system minimap2 `2.26-r1175` and with the pinned
  `2.31-r1302` environment (the defect/large-run conclusions use **2.31**, not 2.26).
- Includes reverse liftover, exact core coverage, all cut positions on 24 seeded
  random indel paths on both strands, deletion-boundary ownership, insertion
  splitting, insertion-only rejection, ambiguity statistics, malformed CIGAR,
  duplicate IDs, long unwrapped FASTA lines, partial PAFs, subprocess failure and
  timeout, alternative placements, exact deduplication and non-bridging stitches.
- Empty/insufficient synthetic coverage never promotes final candidate files;
  raw and pending evidence remains, and inputs are checked unchanged.
- A comparison-regression test proves that moving a deletion or changing a target
  remains a real difference, even when total coverage and lengths are identical.
- The lightweight tests are included as a separate Linux Quality step. The
  multi-GiB reproduction and larger assignment comparisons remain opt-in.

## Still required before Server integration

1. A defined contract for whole-contig primary/secondary ranking, score and unknown
   MAPQ; no naive numerical use of `255` as high confidence.
2. CGAT self-alignment alias/no-diagonal/no-dual compatibility, which this prototype
   does not attempt to emulate.
3. Repeat-rich, near-identical alternative placements and boundary disagreements;
   unique coordinate adjacency is not a general biological stitching proof.
4. Full GRT Step1–Step4, structural events, retained source lineage and Final Path
   comparisons, including the meaning of long adjacent identical CIGAR terms in
   each consumer.
5. The customer's actual failure evidence and an approved isolated rerun. Their
   wheat failure is not diagnosed merely because this synthetic case is solved.

The chosen location is deliberately `experiments/`, outside the published Server
bundle. Do not replace a customer's PAF, change a prepared workspace, or promote
the output into the default workflow based on this report alone.
