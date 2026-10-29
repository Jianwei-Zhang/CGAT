# Sequential multi-fragment score provenance — implementation awaiting validation

## Why this exists

Upstream minimap2 v2.31 `mm_split_reg` assigns a split tail's chain score from the
current parent's score and seed counts using binary32 division/multiplication and
then subtracts that tail score from the parent head. `mm_align_skeleton` inserts
the tail as the next region, so if it splits again the next calculation uses the
**already rounded tail**, not the original total score. Therefore a final
three-or-more-fragment result cannot be reconstructed by independently multiplying
the original score by each final seed fraction.

`sequential_split_witness.py` implements only that conditional accounting:

1. order same-strand fragments in target/oriented-query chain order;
2. stream the original CN trace and require every original seed to belong uniquely
   to one fragment in a contiguous chain partition;
3. require a complete matching `QT` event;
4. repeatedly separate the next head from the remaining tail with the v2.31
   binary32 rounding model;
5. optionally compare the result to independently reported diagnostic `cm`/`s1`
   values **after** construction.

The default two-fragment API remains explicit. Multi-fragment use must opt in and
is bounded to 64 fragments; trace bytes, lines, line size, time and process buffer
budgets remain enforced. Forward and reverse fragments use the existing oriented
query-coordinate contract.

## What this does not prove

- It does not observe actual internal split-event boundaries. Matching seed
  partitions and scores is conditional evidence for the sequential-tail model.
- It does not reconstruct the complete post-DP candidate universe, parent/secondary
  relationships, ranking, MAPQ, alignment score or primary tags.
- It does not support joins, inversion rescue, mixed-strand fragments, missing or
  shared seeds, nonmonotonic chains, or fragments without full original seed
  coverage. These fail closed.
- It does not establish that a window-produced fragment set is the one whole-query
  minimap2 would retain, particularly in repeats or competing targets.
- It does not repair the customer's assertion or authorize a production PAF.

`test_sequential_split_witness.py` defines deferred forward/reverse three-fragment,
rounding, oracle, malformed trace, identity, bounds and legacy two-fragment cases.
They have **not run** under the user's deferred-testing instruction. Controlled
whole-query minimap2 oracle cases and downstream acceptance remain final-phase gates.
