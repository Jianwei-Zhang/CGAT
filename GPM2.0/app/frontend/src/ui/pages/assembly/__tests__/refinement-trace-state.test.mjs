import test from "node:test";
import assert from "node:assert/strict";
import { normalizeRefinementTrace } from "../refinement-trace-state.js";
import { normalizeGrtFinalPathByChr } from "../grt-state.js";
import { normalizeFinalPathByChr } from "../final-path-state.js";

test("refinement lineage and residual N origin survive editable-state normalization", () => {
  const raw = { chr1: { chr: "chr1", q4_length: 6, q4_sha256: "a".repeat(64), segments: [
    { segment_id: "retained", kind: "source", length: 4, source_length: 8, parent_segment_id: "lgz-parent",
      parent_interval: [0, 4], source: { dataset: "old", contig: "original", start: 1, end: 4, orientation: "-" } },
    { segment_id: "remaining", kind: "gap", length: 2, refinement_edit_id: "edit-1", original_gap_ids: ["gap-1"],
      refinement_source: { dataset: "cgat_refinement", contig: "patch-1", start: 3, end: 4, orientation: "+" } },
  ] } };
  const initial = normalizeGrtFinalPathByChr(raw);
  const saved = normalizeFinalPathByChr(initial);
  assert.equal(saved.chr1.segments[0].refinement.parentSegmentId, "lgz-parent");
  assert.deepEqual(saved.chr1.segments[0].refinement.parentInterval, [0, 4]);
  assert.equal(saved.chr1.segments[0].start, 4);
  assert.equal(saved.chr1.segments[1].refinement.source.dataset, "cgat_refinement");
  assert.deepEqual(saved.chr1.segments[1].refinement.originalGapIds, ["gap-1"]);
  assert.equal(saved.chr1.segments[1].gapSizeBp, 2);
  assert.deepEqual(normalizeFinalPathByChr(saved), saved);
});

test("unrelated fields are not promoted to refinement lineage", () => {
  assert.equal(normalizeRefinementTrace({ event_id: "old-event" }), null);
  assert.deepEqual(normalizeRefinementTrace({ original_gap_ids: ["gap-1", "gap-1"], parent_interval: [-1, 2] }), { originalGapIds: ["gap-1"] });
});
