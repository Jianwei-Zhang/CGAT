import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeGrtProjectView,
} from "../grt-state.js";
import { normalizeFinalPathByChr } from "../final-path-state.js";

function buildRawView() {
  return {
    recipe: {
      workflow: "gpm_grt_precomputed_v1",
      schema_version: "1",
      final_path_schema_version: "1",
      recipe_id: "recipe-1",
      primary_dataset: "primary",
      support_datasets: ["support"],
      reads_qc_enabled: true,
      donor_set_id: "d0",
      tel_donor_set_id: "dtel",
    },
    final_path_by_chr: {
      Chr01: {
        chr: "Chr01",
        q4_length: 8,
        q4_sha256: "q4-sha",
        segments: [
          {
            segment_id: "seg-source",
            kind: "source",
            length: 4,
            event_id: null,
            evidence_ids: ["ev-ref"],
            source: {
              dataset: "primary",
              contig: "primary1",
              start: 1,
              end: 4,
              orientation: "+",
            },
          },
          {
            segment_id: "seg-patch",
            kind: "patch",
            length: 4,
            event_id: "evt-step1",
            evidence_ids: ["ev-step1", "ev-display"],
            source: {
              dataset: "support",
              contig: "donor1",
              start: 1,
              end: 4,
              orientation: "+",
            },
          },
        ],
      },
    },
    source_cards: [
      {
        source_card_key: "support:donor1:Chr01:grt_promoted",
        dataset_name: "support",
        contig_name: "donor1",
        original_assignment: "unplaced",
        target_chr: "Chr01",
        placement_mode: "grt_promoted",
        ref_alignment_status: "no_hit",
        anchor_start: "5",
        orientation: "+",
        ref_evidence_ids_json: "[\"ev-ref-donor\"]",
        accepted_event_ids_json: "[\"evt-step1\"]",
        final_path_segment_ids_json: "[\"seg-patch\"]",
        pairwise_evidence_ids_json: "[\"ev-display\"]",
      },
    ],
    verification: {
      chromosome_count: 1,
      segment_count: 2,
      q4_artifact_sha256: "artifact-sha",
    },
  };
}

test("normalizes the lean App GRT projection without trace payloads", () => {
  const view = normalizeGrtProjectView(buildRawView());
  const patch = view.baselineFinalPathByChr.Chr01.segments[1];

  assert.equal(view.recipe.recipeId, "recipe-1");
  assert.equal(patch.segmentId, "seg-patch");
  assert.equal(patch.eventId, undefined);
  assert.equal(patch.sourceCardKey, undefined);
  assert.equal(patch.evidenceIds, undefined);
  assert.equal(patch.placementMode, undefined);
  assert.equal(patch.refAlignmentStatus, undefined);
  assert.equal(patch.anchorSource, undefined);
  assert.deepEqual(patch.source, {
    dataset: "support",
    contig: "donor1",
    start: 1,
    end: 4,
    orientation: "+",
  });
  assert.deepEqual(view.sourceCards, [{
    sourceCardKey: "support:donor1:Chr01:grt_promoted",
    datasetName: "support",
    contigName: "donor1",
    targetChr: "Chr01",
    placementMode: "grt_promoted",
    refAlignmentStatus: "no_hit",
  }]);
});

test("editable Final Path round-trip preserves source intervals and q4 identity", () => {
  const view = normalizeGrtProjectView(buildRawView());
  const firstRoundTrip = normalizeFinalPathByChr(view.baselineFinalPathByChr);
  const secondRoundTrip = normalizeFinalPathByChr(JSON.parse(JSON.stringify(firstRoundTrip)));
  const segment = secondRoundTrip.Chr01.segments[1];

  assert.equal(segment.eventId, undefined);
  assert.equal(segment.sourceCardKey, undefined);
  assert.deepEqual(segment.evidenceIds, undefined);
  assert.equal(segment.source.dataset, "support");
  assert.equal(secondRoundTrip.Chr01.q4Sha256, "q4-sha");
});

test("project edits do not mutate the immutable Server baseline", () => {
  const view = normalizeGrtProjectView(buildRawView());
  const editable = normalizeFinalPathByChr(view.baselineFinalPathByChr);
  editable.Chr01.segments[1].ctgName = "project-edited-name";
  editable.Chr01.segments[1].source.contig = "project-edited-source";

  assert.equal(view.baselineFinalPathByChr.Chr01.segments[1].ctgName, "donor1");
  assert.equal(view.baselineFinalPathByChr.Chr01.segments[1].source.contig, "donor1");
});
