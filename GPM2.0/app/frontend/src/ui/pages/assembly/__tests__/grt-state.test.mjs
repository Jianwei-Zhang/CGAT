import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeGrtProjectView,
} from "../grt-state.js";
import { normalizeFinalPathByChr } from "../final-path-state.js";

function buildRawView() {
  return {
    recipe: {
      workflow: "gpm_grt_app_precomputed_v2",
      schema_version: "2",
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
            source_length: 10,
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
            source_length: 12,
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
  assert.equal(patch.overallLen, 12);
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

test("uses one authoritative source length for repeated and N-split GRT slices", () => {
  const raw = buildRawView();
  raw.final_path_by_chr.Chr01.segments = [
    {
      segment_id: "patch-1",
      kind: "patch",
      length: 8,
      source_length: 43_726_252,
      source: {
        dataset: "hifiasm",
        contig: "ptg000002l",
        start: 28_911_536,
        end: 28_911_543,
        orientation: "-",
      },
    },
    {
      segment_id: "patch-2",
      kind: "patch",
      length: 5_493,
      source_length: 43_726_252,
      source: {
        dataset: "hifiasm",
        contig: "ptg000002l",
        start: 22_716_743,
        end: 22_722_235,
        orientation: "-",
      },
    },
    {
      segment_id: "source-left",
      kind: "source",
      length: 30_205_115,
      source_length: 30_370_176,
      source: {
        dataset: "flye",
        contig: "scaffold_50",
        start: 1,
        end: 30_205_115,
        orientation: "+",
      },
    },
    {
      segment_id: "source-right",
      kind: "source",
      length: 164_937,
      source_length: 30_370_176,
      source: {
        dataset: "flye",
        contig: "scaffold_50",
        start: 30_205_229,
        end: 30_370_165,
        orientation: "+",
      },
    },
  ];

  const segments = normalizeGrtProjectView(raw).baselineFinalPathByChr.Chr01.segments;
  assert.deepEqual(segments.map((segment) => segment.overallLen), [
    43_726_252,
    43_726_252,
    30_370_176,
    30_370_176,
  ]);
  assert.deepEqual(
    segments.map((segment) => [segment.start, segment.end]),
    [
      [28_911_543, 28_911_536],
      [22_722_235, 22_716_743],
      [1, 30_205_115],
      [30_205_229, 30_370_165],
    ],
  );
});

test("rejects missing or too-small authoritative source lengths", () => {
  const missing = buildRawView();
  delete missing.final_path_by_chr.Chr01.segments[1].source_length;
  assert.throws(
    () => normalizeGrtProjectView(missing),
    /Invalid GRT source_length for Chr01:seg-patch: missing/,
  );

  const tooSmall = buildRawView();
  tooSmall.final_path_by_chr.Chr01.segments[1].source_length = 3;
  assert.throws(
    () => normalizeGrtProjectView(tooSmall),
    /Invalid GRT source_length for Chr01:seg-patch: 3/,
  );
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

test("schema 2 keeps App-owned display mappings separate from the editable path", () => {
  const raw = buildRawView();
  raw.recipe.final_path_schema_version = "2";
  raw.final_path_by_chr.Chr01.grt_display_available = true;
  raw.final_path_by_chr.Chr01.segments[0].assembly_ctg_id = 101;
  raw.final_path_by_chr.Chr01.segments[0].assembly_source_start = 1;
  raw.final_path_by_chr.Chr01.segments[0].assembly_source_end = 10;
  raw.final_path_by_chr.Chr01.segments[1].assembly_ctg_id = 202;
  raw.final_path_by_chr.Chr01.segments[1].assembly_source_start = 1;
  raw.final_path_by_chr.Chr01.segments[1].assembly_source_end = 12;

  const view = normalizeGrtProjectView(raw);
  const baselineSegment = view.baselineFinalPathByChr.Chr01.segments[1];
  const editableSegment = normalizeFinalPathByChr(view.baselineFinalPathByChr).Chr01.segments[1];

  assert.equal(view.baselineFinalPathByChr.Chr01.grtDisplayAvailable, true);
  assert.equal(baselineSegment.assemblyCtgId, 202);
  assert.equal(baselineSegment.assemblySourceStart, 1);
  assert.equal(baselineSegment.assemblySourceEnd, 12);
  assert.equal(editableSegment.assemblyCtgId, null);
  assert.equal(editableSegment.assemblySourceStart, undefined);
  assert.equal(editableSegment.assemblySourceEnd, undefined);
});
