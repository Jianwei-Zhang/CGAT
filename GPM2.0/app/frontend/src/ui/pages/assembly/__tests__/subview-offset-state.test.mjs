import test from "node:test";
import assert from "node:assert/strict";

import { resolveSubviewAutoTrackOffsets } from "../subview-offset-state.js";

test("equal-length subview tracks do not receive automatic offsets", () => {
  assert.deepEqual(resolveSubviewAutoTrackOffsets({
    topLengthBp: 1000,
    bottomLengthBp: 1000,
    domainEnd: 1000,
    segmentPairs: [{
      topSegment: { ctgStart: 100, ctgEnd: 200 },
      bottomSegment: { ctgStart: 300, ctgEnd: 400 },
    }],
  }), { topOffsetBp: 0, bottomOffsetBp: 0 });
});

test("automatic subview offsets align the shorter track by the median paired midpoint", () => {
  assert.deepEqual(resolveSubviewAutoTrackOffsets({
    topLengthBp: 600,
    bottomLengthBp: 1000,
    domainEnd: 1000,
    segmentPairs: [
      {
        topSegment: { ctgStart: 100, ctgEnd: 200 },
        bottomSegment: { ctgStart: 300, ctgEnd: 400 },
      },
      {
        topSegment: { ctgStart: 200, ctgEnd: 300 },
        bottomSegment: { ctgStart: 500, ctgEnd: 600 },
      },
    ],
  }), { topOffsetBp: 250, bottomOffsetBp: 0 });
});

test("automatic subview offsets clamp evidence beyond the available domain", () => {
  assert.deepEqual(resolveSubviewAutoTrackOffsets({
    topLengthBp: 1000,
    bottomLengthBp: 400,
    domainEnd: 1000,
    segmentPairs: [{
      topSegment: { ctgStart: 900, ctgEnd: 1000 },
      bottomSegment: { ctgStart: 10, ctgEnd: 20 },
    }],
  }), { topOffsetBp: 0, bottomOffsetBp: 600 });
});
