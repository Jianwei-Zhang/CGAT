import test from "node:test";
import assert from "node:assert/strict";

import {
  loadProjectAssemblyViewState,
  persistProjectAssemblyViewState,
} from "../project-view-state.js";

test("loadProjectAssemblyViewState normalizes segment-based finalPathByChr, finalPathViewMode, and membersCardCollapsed", async () => {
  const result = await loadProjectAssemblyViewState(
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
    },
    {
      async getProjectAssemblyViewState() {
        return {
          supportDatasetId: 22,
          trackView: {},
          supportDsCtgLenRulesByChr: {
            Chr01: [{ startBp: 1, endBp: 5000000, supportDsCtgLen: 100000 }],
          },
          supportMirroredCtgs: [],
          hiddenPrimaryCtgIds: [],
          hiddenPrimaryCtgIdsByChr: { Chr01: [9, "9", 0], "": [1] },
          trackDragOffsets: [],
          subviewTrackDragOffsets: [],
          subviewAnchorStateByKey: {
            "2-contig|chr:Chr01|a|b": {
              activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
              manualAnchors: [{
                manualAnchorId: "m1",
                endpointA: { endpointKey: "a", contigId: 9, cutBp: 100 },
                endpointB: { endpointKey: "b", contigId: 10, cutBp: 200 },
              }],
            },
            "": { activeAnchors: [{ hitKey: "bad", edge: "left" }] },
          },
          trackScrollState: {},
          subviewTrackScrollState: {},
          finalPathTrackScrollState: {
            viewportKey: "7:Chr01:graph:10000:10",
            scrollLeft: 320,
          },
          membersCardCollapsed: false,
          finalPathViewMode: "degap",
          degapProjectState: {
            settingsPanelDismissed: true,
            jobs: [{
              jobId: "CtgA_vs_CtgB_Left-job",
              left: { assemblyCtgId: 9, start: 1200, end: 1 },
              right: { assemblyCtgId: 10, start: 1, end: 800 },
            }],
          },
          finalPathByChr: {
            Chr01: {
              mode: "segments",
              chrName: "Chr01",
              segments: [
                {
                  segmentId: "seg-1",
                  type: "ctg",
                  assemblyCtgId: 9,
                  datasetName: "",
                  ctgName: "flye_ctg9",
                  originId: "utig4-001122l",
                  overallLen: 1200,
                  start: 1,
                  end: 1200,
                },
              ],
              updatedAt: "1",
            },
            bad: {
              mode: "unknown",
            },
          },
        };
      },
    },
  );

  assert.deepEqual(result.finalPathByChr, {
    Chr01: {
      mode: "segments",
      chrName: "Chr01",
      totalLength: 1200,
      segments: [
        {
          segmentId: "seg-1",
          type: "ctg",
          assemblyCtgId: 9,
          datasetName: "",
          ctgName: "flye_ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 1,
          end: 1200,
        },
      ],
      updatedAt: "1",
    },
  });
  assert.equal(result.finalPathViewMode, "degap");
  assert.deepEqual(result.supportDsCtgLenRulesByChr, {
    Chr01: [{ startBp: 1, endBp: 5000000, supportDsCtgLen: 100000 }],
  });
  assert.deepEqual(result.hiddenPrimaryCtgIdsByChr, { Chr01: [9] });
  assert.equal(result.membersCardCollapsed, false);
  assert.deepEqual(result.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 320,
  });
  assert.equal(result.degapProjectState.settingsPanelDismissed, true);
  assert.equal(result.degapProjectState.jobs[0].jobId, "CtgA_vs_CtgB_Left-job");
  assert.deepEqual(result.subviewAnchorStateByKey, {
    "2-contig|chr:Chr01|a|b": {
      activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
      manualAnchors: [{
        manualAnchorId: "m1",
        sourceHitKey: "",
        sourceEdge: "left",
        direction: "",
        offsetBp: null,
        endpointA: { endpointKey: "a", contigId: 9, cutBp: 100 },
        endpointB: { endpointKey: "b", contigId: 10, cutBp: 200 },
      }],
    },
  });
});

test("persistProjectAssemblyViewState sends and returns normalized segment-based finalPathByChr and membersCardCollapsed", async () => {
  const sent = [];

  const result = await persistProjectAssemblyViewState(
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: 22,
      trackView: {},
      supportDsCtgLenRulesByChr: {
        Chr01: [{ startBp: 1, endBp: 5000000, supportDsCtgLen: 100000 }],
      },
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: { Chr01: [9, "9", 0], "": [1] },
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {
        "2-contig|chr:Chr01|a|b": {
          activeAnchors: [{ hitKey: "hit-1", edge: "right" }],
          manualAnchors: [{
            endpointA: { endpointKey: "b", contigId: 10, cutBp: 200 },
            endpointB: { endpointKey: "a", contigId: 9, cutBp: 100 },
          }],
        },
      },
      trackScrollState: {},
      subviewTrackScrollState: {},
      finalPathTrackScrollState: {
        viewportKey: "7:Chr01:graph:10000:10",
        scrollLeft: 320,
      },
      membersCardCollapsed: false,
      finalPathViewMode: "table",
      degapProjectState: {
        settingsPanelDismissed: true,
        jobs: [{
          jobId: "CtgA_vs_CtgB_Right-job",
          left: { assemblyCtgId: 9, start: 1, end: 1200 },
          right: { assemblyCtgId: 10, start: 800, end: 1 },
        }],
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              assemblyCtgId: 9,
              datasetName: "",
              ctgName: "flye_ctg9",
              originId: "utig4-001122l",
              overallLen: 1200,
              start: 1,
              end: 1200,
            },
          ],
          updatedAt: "1",
        },
        broken: {
          mode: "unknown",
        },
      },
    },
    {
      async setProjectAssemblyViewState(payload) {
        sent.push(payload);
        return payload;
      },
    },
  );

  assert.deepEqual(sent[0].finalPathByChr, {
    Chr01: {
      mode: "segments",
      chrName: "Chr01",
      totalLength: 1200,
      segments: [
        {
          segmentId: "seg-1",
          type: "ctg",
          assemblyCtgId: 9,
          datasetName: "",
          ctgName: "flye_ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 1,
          end: 1200,
        },
      ],
      updatedAt: "1",
    },
  });
  assert.deepEqual(result.finalPathByChr, sent[0].finalPathByChr);
  assert.deepEqual(sent[0].supportDsCtgLenRulesByChr, {
    Chr01: [{ startBp: 1, endBp: 5000000, supportDsCtgLen: 100000 }],
  });
  assert.deepEqual(result.supportDsCtgLenRulesByChr, sent[0].supportDsCtgLenRulesByChr);
  assert.equal(sent[0].finalPathViewMode, "table");
  assert.deepEqual(sent[0].hiddenPrimaryCtgIdsByChr, { Chr01: [9] });
  assert.deepEqual(result.hiddenPrimaryCtgIdsByChr, { Chr01: [9] });
  assert.equal(result.finalPathViewMode, "table");
  assert.deepEqual(sent[0].subviewAnchorStateByKey, {
    "2-contig|chr:Chr01|a|b": {
      activeAnchors: [{ hitKey: "hit-1", edge: "right" }],
      manualAnchors: [{
        manualAnchorId: "manual:a:100:b:200",
        sourceHitKey: "",
        sourceEdge: "left",
        direction: "",
        offsetBp: null,
        endpointA: { endpointKey: "a", contigId: 9, cutBp: 100 },
        endpointB: { endpointKey: "b", contigId: 10, cutBp: 200 },
      }],
    },
  });
  assert.deepEqual(result.subviewAnchorStateByKey, sent[0].subviewAnchorStateByKey);
  assert.equal(sent[0].membersCardCollapsed, false);
  assert.equal(result.membersCardCollapsed, false);
  assert.deepEqual(sent[0].finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 320,
  });
  assert.deepEqual(result.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 320,
  });
  assert.equal(sent[0].degapProjectState.settingsPanelDismissed, true);
  assert.equal(result.degapProjectState.jobs[0].jobId, "CtgA_vs_CtgB_Right-job");
});

test("loadProjectAssemblyViewState defaults membersCardCollapsed to true", async () => {
  const result = await loadProjectAssemblyViewState(
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
    },
    {
      async getProjectAssemblyViewState() {
        return {
          supportDatasetId: null,
          trackView: {},
        };
      },
    },
  );

  assert.equal(result.membersCardCollapsed, true);
});
