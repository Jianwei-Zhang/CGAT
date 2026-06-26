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
