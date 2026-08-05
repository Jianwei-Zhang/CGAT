import test from "node:test";
import assert from "node:assert/strict";

import { renderAssemblyPage } from "../../assembly-page.js";

function createState(grtTrace = {}) {
  const baselineSegment = {
    segmentId: "seg-patch",
    type: "source",
    grtKind: "patch",
    datasetId: 2,
    datasetName: "flye",
    originId: "donor_unplaced",
    ctgName: "donor_unplaced",
    assemblyCtgId: 202,
    lengthBp: 800,
    orient: "+",
    eventId: "evt-step1",
    evidenceIds: ["ev-step1", "ev-display"],
    sourceCardKey: "flye:donor_unplaced:Chr01:grt_promoted",
    placementMode: "grt_promoted",
    refAlignmentStatus: "no_hit",
    anchorSource: "grt_final_path",
    source: {
      dataset: "flye",
      contig: "donor_unplaced",
      start: 1,
      end: 800,
      orientation: "+",
    },
  };
  return {
    locale: "en",
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
      projectName: "grt-project",
    },
    initializer: {
      datasets: [
        { datasetId: 1, name: "hifiasm" },
        { datasetId: 2, name: "flye" },
      ],
      existingProjects: [{
        projectId: 7,
        projectName: "grt-project",
        primaryDatasetId: 1,
        supportDatasetIds: [2],
        phasedAssemblyEnabled: false,
        autoPipelineDone: true,
      }],
    },
    assembly: {
      loading: false,
      activeTab: "assembly",
      summary: "",
      selectedChrName: "Chr01",
      selectedCtgId: null,
      chromosomes: [{
        chrName: "Chr01",
        chrOrder: 1,
        chrLength: 100_000,
        ctgCount: 1,
        placedBp: 800,
      }],
      chrPickerOpen: false,
      membersCardCollapsed: false,
      chrCtgs: [],
      supportDatasetId: 2,
      supportChrCtgs: [{
        assemblyCtgId: 202,
        name: "donor_unplaced",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 800,
        anchorStart: 10,
        refOrient: "+",
        placementMode: "grt_promoted",
        grtPlacementMode: "grt_promoted",
        grtSourceCardKey: "flye:donor_unplaced:Chr01:grt_promoted",
        refAlignmentStatus: "no_hit",
        grtRefAlignmentStatus: "no_hit",
        hits: [],
      }],
      refTrackMembers: [],
      phasedChrTracks: [],
      isChrPhased: false,
      activeHitsTrackKey: "primary",
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
      trackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10_000,
        maxTickCount: 10,
        alignmentLength: 10_000,
        mapq: 0,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10_000,
        maxTickCount: 10,
        alignmentLength: 10_000,
        mapq: 0,
      },
      finalPathTrackView: { minTickUnitKb: 10_000, maxTickCount: 10 },
      finalPathByChr: {
        Chr01: {
          chrName: "Chr01",
          segments: [{ ...baselineSegment }],
          q4Length: 800,
          q4Sha256: "q4-sha",
          updatedAt: "",
        },
      },
      finalPathViewMode: "graph",
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      supportMirroredCtgs: [],
      trackScrollState: {},
      subviewTrackScrollState: {},
      finalPathTrackScrollState: {},
      subview: {},
      newSequences: { loading: false, error: "", items: [] },
      error: "",
      actionStatus: "",
      actionError: "",
      junctionLoading: false,
      junctionStatus: "",
      junctionError: "",
      junctionReport: null,
      grtProjectView: {
        recipe: { recipeId: "recipe-1" },
        baselineFinalPathByChr: {
          Chr01: {
            chrName: "Chr01",
            segments: [{ ...baselineSegment }],
            q4Length: 800,
            q4Sha256: "q4-sha",
          },
        },
        objectAttempts: [
          {
            attemptId: "attempt-terminal",
            chr: "Chr01",
            objectId: "terminal-right",
            objectKind: "terminal",
            status: "unresolved",
            reason: "no_candidate",
            candidateCount: 0,
          },
          {
            attemptId: "attempt-other-chr",
            chr: "Chr02",
            objectId: "gap-other",
            objectKind: "gap",
            status: "unresolved",
            reason: "no_candidate",
            candidateCount: 0,
          },
        ],
        sourceCards: [
          {
            sourceCardKey: "flye:donor_unplaced:Chr01:grt_promoted",
            datasetName: "flye",
            contigName: "donor_unplaced",
            targetChr: "Chr01",
            placementMode: "grt_promoted",
            refAlignmentStatus: "no_hit",
          },
          {
            sourceCardKey: "flye:donor_cross:Chr01:cross_chr_grt_usage",
            datasetName: "flye",
            contigName: "donor_cross",
            targetChr: "Chr01",
            placementMode: "cross_chr_grt_usage",
            refAlignmentStatus: "multi_hit",
          },
        ],
        verification: {},
      },
      grtTrace,
    },
  };
}

test("renders immutable baseline, unresolved workflow results, and explicit GRT usage status", () => {
  const html = renderAssemblyPage(createState());

  assert.match(html, /data-grt-trace-panel="true"/);
  assert.match(html, /Server precomputed baseline/);
  assert.match(html, /Project-level Final Path edits below never overwrite it/);
  assert.match(html, /data-grt-baseline-segment-id="seg-patch"/);
  assert.match(html, /data-grt-trace-kind="event" data-grt-trace-id="evt-step1"/);
  assert.match(html, /unresolved \(workflow result\)/);
  assert.match(html, /terminal-right/);
  assert.doesNotMatch(html, /gap-other/);
  assert.match(html, /grt_promoted/);
  assert.match(html, /cross_chr_grt_usage/);
  assert.match(html, /Ref status: no_hit/);
  assert.match(html, /Ref status: multi_hit/);
  assert.match(html, /Anchor source: GRT Final Path/);
  assert.match(html, /data-grt-placement-mode="grt_promoted"/);
  assert.doesNotMatch(html, /Program error/);
});

test("renders source, event, and evidence links from an opened trace detail", () => {
  const html = renderAssemblyPage(createState({
    loading: false,
    error: "",
    kind: "event",
    id: "evt-step1",
    detail: {
      event_id: "evt-step1",
      final_path_segment_id: "seg-patch",
      source_card_key: "flye:donor_unplaced:Chr01:grt_promoted",
      evidence_ids: ["ev-step1", "ev-display"],
    },
  }));

  assert.match(html, /data-grt-trace-close="true"/);
  assert.match(html, /data-grt-trace-kind="source-card"/);
  assert.match(html, /data-grt-trace-kind="event" data-grt-trace-id="evt-step1"/);
  assert.match(html, /data-grt-trace-kind="evidence" data-grt-trace-id="ev-step1"/);
  assert.match(html, /data-grt-trace-kind="evidence" data-grt-trace-id="ev-display"/);
  assert.match(html, /data-grt-locate-final-path-segment-id="seg-patch"/);
});
