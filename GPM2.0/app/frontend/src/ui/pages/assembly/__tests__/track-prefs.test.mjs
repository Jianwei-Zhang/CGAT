import test from "node:test";
import assert from "node:assert/strict";
import {
  MIN_TICK_UNIT_KB_OPTIONS,
  normalizeNonNegativeInt,
  normalizePositiveInt,
  normalizeTrackPrefInputValue,
  resolveTrackPrefs,
} from "../track-prefs.js";

test("manual track inputs accept only safe decimal integers within the field range", () => {
  for (const field of ["minTickUnitKb", "maxTickCount", "alignmentLength", "supportDsCtgLen", "mapq"]) {
    for (const invalid of ["", " ", " 1", "1 ", "-1", "+1", "1.5", "1e2", "0x10", "12bp", "１２", "9007199254740992"]) {
      assert.equal(normalizeTrackPrefInputValue(field, invalid), null, `${field}: ${invalid}`);
    }
    assert.equal(normalizeTrackPrefInputValue(field, "0012"), 12);
    assert.equal(normalizeTrackPrefInputValue(field, "0"), ["supportDsCtgLen", "mapq"].includes(field) ? 0 : null);
  }
  assert.equal(normalizeTrackPrefInputValue("mapq", "255"), 255);
  assert.equal(normalizeTrackPrefInputValue("mapq", "256"), null);
  assert.equal(normalizeTrackPrefInputValue("alignmentLength", String(Number.MAX_SAFE_INTEGER)), Number.MAX_SAFE_INTEGER);
});

test("resolveTrackPrefs returns v1 discrete defaults", () => {
  assert.deepEqual(resolveTrackPrefs({}), {
    supportDsCtgLen: 0,
    supportDsCtgLenBp: 0,
    minTickUnitKb: 10000,
    minTickKb: 10000,
    maxTickCount: 10,
    viewSpanKb: 500,
    pixelUnit: 10000,
    tickLength: 10000,
    tickBp: 10000,
    alignmentLength: 10000,
    block_length: 10000,
    mapq: 0,
  });
});

test("min tick unit options include the fixed 100000 kb scale", () => {
  assert.ok(MIN_TICK_UNIT_KB_OPTIONS.includes(100000));
});

test("resolveTrackPrefs snaps legacy pixelUnit to the nearest v1 option", () => {
  assert.equal(resolveTrackPrefs({ pixelUnit: 7499 }).viewSpanKb, 5000);
  assert.equal(resolveTrackPrefs({ pixelUnit: 2600 }).viewSpanKb, 500);
});

test("resolveTrackPrefs keeps positive integers for new v1 track fields", () => {
  assert.deepEqual(
    resolveTrackPrefs({
      viewSpanKb: 1234,
      tickLength: 75000,
      alignmentLength: 6500,
    }),
    {
      supportDsCtgLen: 0,
      supportDsCtgLenBp: 0,
      minTickUnitKb: 10000,
      minTickKb: 10000,
      maxTickCount: 10,
      viewSpanKb: 500,
      pixelUnit: 10000,
      tickLength: 100000,
      tickBp: 100000,
      alignmentLength: 6500,
      block_length: 6500,
      mapq: 0,
    },
  );
});

test("normalizePositiveInt clamps finite positive decimals to at least 1", () => {
  assert.equal(normalizePositiveInt(0.5), 1);
});

test("normalizeNonNegativeInt accepts zero and non-negative decimals", () => {
  assert.equal(normalizeNonNegativeInt(0), 0);
  assert.equal(normalizeNonNegativeInt(12.8), 12);
  assert.equal(normalizeNonNegativeInt(-1), null);
});

test("resolveTrackPrefs keeps free positive integer input for tick scale controls", () => {
  const prefs = resolveTrackPrefs({
    minTickUnitKb: 740,
    maxTickCount: 18,
  });
  assert.equal(prefs.minTickUnitKb, 740);
  assert.equal(prefs.maxTickCount, 18);
});

test("resolveTrackPrefs falls back to defaults for invalid and non-positive values", () => {
  assert.deepEqual(
    resolveTrackPrefs({
      minTickUnitKb: 0,
      maxTickCount: Number.NaN,
      viewSpanKb: 0,
      pixelUnit: Number.NaN,
      tickLength: -3,
      alignmentLength: Number.NaN,
    }),
    {
      supportDsCtgLen: 0,
      supportDsCtgLenBp: 0,
      minTickUnitKb: 10000,
      minTickKb: 10000,
      maxTickCount: 10,
      viewSpanKb: 500,
      pixelUnit: 10000,
      tickLength: 10000,
      tickBp: 10000,
      alignmentLength: 10000,
      block_length: 10000,
      mapq: 0,
    },
  );
});

test("resolveTrackPrefs keeps free non-negative MAPQ input with default 0", () => {
  assert.equal(resolveTrackPrefs({ mapq: 0 }).mapq, 0);
  assert.equal(resolveTrackPrefs({ mapq: 31 }).mapq, 31);
  assert.equal(resolveTrackPrefs({ mapq: 77 }).mapq, 77);
  assert.equal(resolveTrackPrefs({ mapq: -5 }).mapq, 0);
});

test("resolveTrackPrefs keeps free non-negative support ds ctg length input with default 0", () => {
  assert.equal(resolveTrackPrefs({ supportDsCtgLen: 0 }).supportDsCtgLen, 0);
  assert.equal(resolveTrackPrefs({ supportDsCtgLen: 12345 }).supportDsCtgLen, 12345);
  assert.equal(resolveTrackPrefs({ supportDsCtgLen: -1 }).supportDsCtgLen, 0);
});
