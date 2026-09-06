import test from "node:test";
import assert from "node:assert/strict";

import { formatTrackCtgOrientationLabel } from "../track-label-geometry.js";

test("formatTrackCtgOrientationLabel replaces terminal direction suffixes exactly once", () => {
  assert.equal(formatTrackCtgOrientationLabel("ctg1 (+)", "-"), "ctg1 (-)");
  assert.equal(formatTrackCtgOrientationLabel("ctg2 (-) (+)", "+"), "ctg2 (+)");
});

test("formatTrackCtgOrientationLabel defaults invalid directions to forward", () => {
  assert.equal(formatTrackCtgOrientationLabel("ctg3", "unknown"), "ctg3 (+)");
});
