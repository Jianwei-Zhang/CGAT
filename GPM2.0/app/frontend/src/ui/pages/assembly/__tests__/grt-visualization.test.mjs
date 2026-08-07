import test from "node:test";
import assert from "node:assert/strict";

import { renderAssemblyPage } from "../../assembly-page.js";

function createState() {
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
      chrCtgs: [{
        assemblyCtgId: 101,
        name: "primary_grt",
        originId: "primary_grt",
        totalLength: 1000,
        datasetId: 1,
        grtSourceCardKey: "flye:donor_unplaced:Chr01:grt_promoted",
        grtPlacementMode: "grt_promoted",
        grtRefAlignmentStatus: "no_hit",
      }],
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
          mode: "segments",
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
            mode: "segments",
            chrName: "Chr01",
            segments: [{ ...baselineSegment }],
            q4Length: 800,
            q4Sha256: "q4-sha",
          },
        },
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
    },
  };
}

test("renders passive GRT placement status and a current-path baseline reset", () => {
  const html = renderAssemblyPage(createState());

  assert.doesNotMatch(html, /data-grt-trace-panel="true"/);
  assert.doesNotMatch(html, /Server precomputed baseline/);
  assert.doesNotMatch(html, /data-grt-trace-kind=/);
  assert.doesNotMatch(html, /data-grt-locate-/);
  assert.match(html, /grt_promoted/);
  assert.match(html, /Ref status: no_hit/);
  assert.match(html, /Anchor source: GRT Final Path/);
  assert.match(html, /class="grt-status-badge is-grt_promoted"/);
  assert.doesNotMatch(html, /class="grt-status-badge is-grt_promoted"[^>]*role="button"/);
  assert.match(html, /data-final-path-restore-grt-baseline="Chr01"/);
  assert.doesNotMatch(html, /Program error/);
});

test("does not render persistent trace controls from GRT metadata", () => {
  const state = createState();
  state.assembly.grtProjectView.sourceCards = [];
  const html = renderAssemblyPage(state);

  assert.doesNotMatch(html, /data-grt-trace/);
  assert.doesNotMatch(html, /data-grt-locate/);
  assert.doesNotMatch(html, /object-attempt/);
});
