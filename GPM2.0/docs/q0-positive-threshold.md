# Q0: stop supplementary mapping at supported decisions

`positive_threshold` is a versioned Q0 evidence profile for **new Server workspaces without reads QC**. Use `--q0-supplement-scope positive_threshold` when preparing a workspace. The generated evidence command uses `--supplement-scope positive_threshold`. This is not a resource override for resuming an existing run. `full` retains the existing search and acceptance rules.

The profile builds a provisional backbone from all verified initial alignments, including within-assembly matrices. It asks for weak placements or unsupported junctions, never for the sole purpose of excluding a hypothetical competitor. A strong placement is not permission for an exact cut. The ordinary selector still accounts for competing observed loci, only admits supported paired cuts, and can leave an unknown join. An assignment label alone cannot supply a chromosome with its first reference seed.

## Decision rule for implementation and review

Once existing evidence meets the threshold for **this source interval and this decision** (placement, keeping a gap, or an exact cut), stop looking for competitors for that decision. Apply the stop before queuing work. When reviewing an enumeration, scan, alignment or check, ask: **what could its result change about this decision?** If its only purpose is to show that no alternative exists, remove it. Reuse evidence already checked for the same decision rather than checking it again.

For example, if a selected placement has sufficient support at both ends, a secondary assignment alone must not put that interval back on the request list. A weak adjacent junction is a separate decision: request its unsupported ends, not the whole contig. Evidence sufficient to **leave a gap** does not authorize closing it. Keep checks that can actually invalidate a proposed result, such as counting the same source bases twice or cutting outside the paired alignment. Stopping the search is not a claim that competitors do not exist.

## Supplementary scopes

- **`base_only`**: no supplementary planner ran. The normal consumer must regenerate an empty request from the selected evidence. An empty omission list is not evidence of a full search.
- **`decision_frontier`**: complete query/target contexts that touch a request are kept. The final selection is recomputed. An omitted context intersecting a still-weak decision requires repair. A newly extended request needs no additional pass if both original planning phases completely accounted for their regional tasks and the omitted intervals on both axes are disjoint from it.
- **`full`**: if decisions cannot be localized or bounded repair cannot resolve the search scope, use full supplementary discovery. Invalid bytes, a wrong tool or policy, reads QC, or the absence of a trustworthy path are **not** accepted as successful Q0 construction.

The ordinary `metadata/grt_q0_evidence.json` is published only after the scope and data have been verified. The selection artifact records `supplement_acceptance`, including `alternatives_exhaustive: false`: it certifies the selected backbone under the stated rule, not the absence of unobserved alternatives. Existing source occupancy and interval-aware donor logic are unchanged. Counts of completed windows are not counts of fresh mapper launches; compare both mapper invocations and end-to-end elapsed time before switching a large active analysis.

For large matrices the threshold planner and its verified consumer retain validated hits in a compact in-memory form. Original PAF bytes and record identities are not rewritten. The full ordered CIGAR, optional tags, source geometry and provenance remain available. This reduces retained-input memory, not the number of requested comparisons by itself. On a retained window an old exact mapper result can still be verified and reprojected; a projection signed by a different validator is not accepted under the new validator's identity.
