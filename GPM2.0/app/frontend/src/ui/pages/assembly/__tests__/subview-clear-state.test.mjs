import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSubviewClearProjection,
  clearSubviewRecordsForSummary,
} from "../subview-clear-state.js";
import { buildSubviewAnchorStateKey } from "../subview-anchor-state.js";
import { buildSubviewCompositionHistoryKey } from "../subview-history-state.js";
import { getSubviewState } from "../subview-state.js";

const summaries = {
  "2-contig": {
    mode: "2-contig",
    top: { role: "support", contigId: 30 },
    bottom: { role: "primary", contigId: 2 },
  },
  "track-pair": {
    mode: "track-pair",
    topTrack: { role: "support", source: "mother", datasetId: 22 },
    bottomTrack: { role: "primary", source: "mother" },
  },
  composition: {
    mode: "composition",
    members: [{ entityKey: "assembly:30", lane: "top" }],
    layoutGapBp: 20_000,
  },
};

function createAssembly(mode) {
  const summary = summaries[mode];
  const activePairKey = buildSubviewAnchorStateKey(summary, "Chr01");
  const compositionKey = buildSubviewCompositionHistoryKey("Chr01");
  const otherChrCompositionKey = buildSubviewCompositionHistoryKey("Chr02");
  const otherCurrentChrPairKey = "2-contig|chr:Chr01|other-saved-pair";
  return {
    selectedChrName: "Chr01",
    chrCtgs: [{ assemblyCtgId: 2, name: "primary-2" }],
    trackView: { alignmentLength: 1_000, mapq: 0 },
    finalPathByChr: { Chr01: [{ segmentId: "path-1" }] },
    grtResultByChr: { Chr01: { baselineKey: "grt-1" } },
    subviewTrackDragOffsets: [{ slot: "top", contigId: 30, offsetBp: 40 }],
    subviewCompositionViewport: { bpPerPx: 4, leftBp: 120, topPx: 8 },
    subviewTrackScrollState: { viewportKey: "old-subview", scrollLeft: 90 },
    subviewHistoryByKey: {
      ...(activePairKey ? { [activePairKey]: { marker: "active-pair" } } : {}),
      [compositionKey]: { marker: "current-composition" },
      [otherChrCompositionKey]: { marker: "other-chromosome" },
      [otherCurrentChrPairKey]: { marker: "other-current-chromosome-pair" },
    },
    subviewAnchorStateByKey: {
      ...(activePairKey ? { [activePairKey]: { marker: "active-anchors" } } : {}),
      "2-contig|chr:Chr02|other-pair": { marker: "other-anchor-state" },
      [otherCurrentChrPairKey]: { marker: "other-current-chromosome-anchors" },
    },
    subview: {
      mode,
      historyKey: mode === "composition" ? compositionKey : activePairKey,
      selectedAContigId: 2,
      selectedARole: "primary",
      selectedBContigId: 30,
      selectedBRole: "support",
      selectedTrackSelections: [
        { role: "primary", source: "mother" },
        { role: "support", source: "mother", datasetId: 22 },
      ],
      activeAnchors: [{ hitKey: "old-hit", edge: "left" }],
      manualAnchors: [{ manualAnchorId: "old-manual" }],
      flippedCtgs: [{ slot: "top", contigId: 30 }],
      trackPairHiddenCtgs: [{ trackRole: "support", contigId: 30 }],
      trackPairSelectedCtgs: [{ trackRole: "primary", contigId: 2 }],
      message: "old message",
      error: "old error",
      summary,
      pairwiseEvidence: {
        key: "old-evidence",
        requestKey: "old-request",
        status: "loading",
      },
    },
  };
}

for (const mode of Object.keys(summaries)) {
  test(`clear projection removes only the current ${mode} Subview state`, () => {
    const assembly = createAssembly(mode);
    const mainState = {
      chrCtgs: assembly.chrCtgs,
      trackView: assembly.trackView,
      finalPathByChr: assembly.finalPathByChr,
      grtResultByChr: assembly.grtResultByChr,
    };

    const result = buildSubviewClearProjection(assembly);
    const clearedSubview = getSubviewState(result.assembly);

    assert.equal(result.changed, true);
    assert.equal(clearedSubview.mode, "2-contig");
    assert.equal(clearedSubview.summary, null);
    assert.equal(clearedSubview.historyKey, undefined);
    assert.equal(clearedSubview.pairwiseEvidence, undefined);
    assert.deepEqual(clearedSubview.selectedTrackSelections, []);
    assert.deepEqual(clearedSubview.activeAnchors, []);
    assert.deepEqual(clearedSubview.manualAnchors, []);
    assert.deepEqual(clearedSubview.flippedCtgs, []);
    assert.deepEqual(clearedSubview.trackPairHiddenCtgs, []);
    assert.deepEqual(clearedSubview.trackPairSelectedCtgs, []);
    assert.equal(clearedSubview.message, "");
    assert.equal(clearedSubview.error, "");
    assert.deepEqual(result.assembly.subviewTrackDragOffsets, []);
    assert.deepEqual(result.assembly.subviewCompositionViewport, {});
    assert.deepEqual(result.assembly.subviewTrackScrollState, { viewportKey: "", scrollLeft: 0 });

    const activePairKey = buildSubviewAnchorStateKey(summaries[mode], "Chr01");
    if (activePairKey) {
      assert.equal(result.assembly.subviewHistoryByKey[activePairKey], undefined);
      assert.equal(result.assembly.subviewAnchorStateByKey[activePairKey], undefined);
    }
    assert.equal(result.assembly.subviewHistoryByKey["composition:Chr01"], undefined);
    assert.deepEqual(result.assembly.subviewHistoryByKey["composition:Chr02"], {
      marker: "other-chromosome",
    });
    assert.deepEqual(result.assembly.subviewHistoryByKey["2-contig|chr:Chr01|other-saved-pair"], {
      marker: "other-current-chromosome-pair",
    });
    assert.deepEqual(result.assembly.subviewAnchorStateByKey["2-contig|chr:Chr02|other-pair"], {
      marker: "other-anchor-state",
    });
    assert.deepEqual(result.assembly.subviewAnchorStateByKey["2-contig|chr:Chr01|other-saved-pair"], {
      marker: "other-current-chromosome-anchors",
    });
    assert.deepEqual({
      chrCtgs: result.assembly.chrCtgs,
      trackView: result.assembly.trackView,
      finalPathByChr: result.assembly.finalPathByChr,
      grtResultByChr: result.assembly.grtResultByChr,
    }, mainState);

    const repeated = buildSubviewClearProjection(result.assembly);
    assert.equal(repeated.changed, false);
    assert.equal(repeated.assembly, result.assembly);
  });
}


test("clearing a selected summary removes only that pair history and anchors", () => {
  const selected = summaries["2-contig"];
  const selectedKey = buildSubviewAnchorStateKey(selected, "Chr01");
  const unrelatedKey = "track-pair|chr:Chr01|other";
  const assembly = {
    selectedChrName: "Chr01",
    subviewHistoryByKey: {
      [selectedKey]: { marker: "selected-history" },
      [unrelatedKey]: { marker: "unrelated-history" },
      "composition:Chr02": { marker: "other-chromosome" },
    },
    subviewAnchorStateByKey: {
      [selectedKey]: { marker: "selected-anchors" },
      [unrelatedKey]: { marker: "unrelated-anchors" },
    },
  };

  const result = clearSubviewRecordsForSummary(assembly, selected);

  assert.equal(result.subviewHistoryByKey[selectedKey], undefined);
  assert.equal(result.subviewAnchorStateByKey[selectedKey], undefined);
  assert.deepEqual(result.subviewHistoryByKey[unrelatedKey], { marker: "unrelated-history" });
  assert.deepEqual(result.subviewAnchorStateByKey[unrelatedKey], { marker: "unrelated-anchors" });
  assert.deepEqual(result.subviewHistoryByKey["composition:Chr02"], {
    marker: "other-chromosome",
  });
});
