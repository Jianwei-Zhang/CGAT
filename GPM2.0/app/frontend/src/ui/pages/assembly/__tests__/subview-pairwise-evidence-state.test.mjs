import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSubviewPairwiseEvidenceKey,
  shouldLoadSubviewPairwiseEvidence,
  shouldRefetchSubviewPairwiseEvidence,
} from "../subview-pairwise-evidence-state.js";

test("pairwise evidence keys are only built for ds-vs-ds subview selections", () => {
  assert.equal(
    buildSubviewPairwiseEvidenceKey({
      mode: "2-contig",
      top: { contigId: 30, role: "support" },
      bottom: { contigId: 2, role: "primary" },
    }),
    "2-contig:support:30:primary:2",
  );
  assert.equal(
    shouldLoadSubviewPairwiseEvidence({
      mode: "2-contig",
      top: { contigId: 30, role: "support" },
      bottom: { contigId: 2, role: "ref" },
    }),
    false,
  );
});

test("cached pairwise evidence covers stricter subview thresholds without refetch", () => {
  const summary = {
    mode: "2-contig",
    top: { contigId: 30, role: "support" },
    bottom: { contigId: 2, role: "primary" },
  };
  const evidence = {
    key: "2-contig:support:30:primary:2",
    status: "loaded",
    loadedMinAlignmentLength: 10000,
    loadedMinMapq: 0,
    hits: [{ alignLength: 12000, mapq: 40 }],
  };

  assert.equal(
    shouldRefetchSubviewPairwiseEvidence({
      summary,
      trackPrefs: {
        alignmentLength: 20000,
        mapq: 10,
      },
      evidence,
    }),
    false,
  );
});

test("lowering subview thresholds below the cached floor requires a refetch", () => {
  const summary = {
    mode: "2-contig",
    top: { contigId: 30, role: "support" },
    bottom: { contigId: 2, role: "primary" },
  };
  const evidence = {
    key: "2-contig:support:30:primary:2",
    status: "loaded",
    loadedMinAlignmentLength: 10000,
    loadedMinMapq: 20,
    hits: [{ alignLength: 12000, mapq: 40 }],
  };

  assert.equal(
    shouldRefetchSubviewPairwiseEvidence({
      summary,
      trackPrefs: {
        alignmentLength: 5000,
        mapq: 0,
      },
      evidence,
    }),
    true,
  );
});

test("composition evidence keys include assembly members and leave reference projection local", () => {
  const summary = {
    mode: "composition",
    members: [
      { assemblyCtgId: 30, source: { role: "support", datasetId: 2 }, lane: "top" },
      { assemblyCtgId: 31, source: { role: "ref" }, reference: {
        chrName: "Chr01", startBp: 1, endBp: 1000,
      }, lane: "top" },
      { assemblyCtgId: 2, source: { role: "primary", datasetId: 1 }, lane: "bottom" },
    ],
  };
  assert.equal(shouldLoadSubviewPairwiseEvidence(summary), true);
  assert.equal(
    buildSubviewPairwiseEvidenceKey(summary),
    "composition:assembly:30@support:2:mother:0:0:|assembly:2@primary:1:mother:0:0:",
  );
  assert.equal(shouldLoadSubviewPairwiseEvidence({
    mode: "composition",
    members: [summary.members[1], summary.members[2]],
  }), false);
});
