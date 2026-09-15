import test from "node:test";
import assert from "node:assert/strict";
import {
  readHitIdentityPct, resolveAlignmentBandStyle, sortAlignmentBands,
  alignmentBandSvgAttrs, alignmentBandTooltipMetrics,
} from "../alignment-band-style.js";
import { resolveHitIdentityPct } from "../track-render-geometry.js";

test("missing identity stays unknown, real zero survives, raw match counts remain compatible", () => {
  for (const identityPct of [undefined, null, "", " ", NaN, Infinity, "unknown"]) {
    assert.equal(readHitIdentityPct({ identityPct, mapq: 60 }), null);
  }
  assert.equal(readHitIdentityPct({ identityPct: 0 }), 0);
  assert.equal(readHitIdentityPct({ identity_pct: "93.27" }), 93.27);
  assert.equal(readHitIdentityPct({ match_length: 9327, block_length: 10000 }), 93.27);
  assert.equal(readHitIdentityPct({ matches: 0, blockLength: 100 }), 0);
  assert.equal(readHitIdentityPct({ matches: null, blockLength: 100 }), null);
  assert.equal(readHitIdentityPct({ matches: 100, blockLength: 0 }), null);
  assert.equal(resolveHitIdentityPct({}), 0, "zero threshold still includes unknown hits");
});

test("fixed continuous opaque scale preserves track hues and clamps only the color floor", () => {
  for (const tone of ["primary", "companion"]) {
    assert.deepEqual(resolveAlignmentBandStyle(tone, 0), resolveAlignmentBandStyle(tone, 80));
    const fills = [80, 85, 90, 93.27, 95, 100].map((identity) => resolveAlignmentBandStyle(tone, identity).fill);
    const channels = fills.map((fill) => fill.match(/\d+/g).map(Number));
    fills.forEach((fill) => assert.match(fill, /^rgb\(\d+, \d+, \d+\)$/));
    channels.slice(1).forEach((rgb, index) => rgb.forEach((channel, i) => assert.ok(channel < channels[index][i])));
    assert.notEqual(resolveAlignmentBandStyle(tone, null).fill, fills[0]);
  }
});

test("draw order is stable, high identity wins, filtering never rescales survivors or mutates source", () => {
  const hits = [{ key: "high", identityPct: 95 }, { key: "zero", identityPct: 0 },
    { key: "unknown" }, { key: "tie", identityPct: 95 }, { key: "low", identityPct: 85 }];
  const before = structuredClone(hits);
  assert.deepEqual(sortAlignmentBands(hits).map((hit) => hit.key), ["unknown", "zero", "low", "high", "tie"]);
  assert.deepEqual(hits, before);
  const originalAttrs = new Map(hits.map((hit) => [hit.key, alignmentBandSvgAttrs(hit, "companion")]));
  sortAlignmentBands(hits.filter((hit) => resolveHitIdentityPct(hit) >= 90)).forEach((hit) => {
    assert.equal(alignmentBandSvgAttrs(hit, "companion"), originalAttrs.get(hit.key));
  });
});

test("SVG export attributes and exact tooltip distinguish unknown from zero", () => {
  const attrs = alignmentBandSvgAttrs({ identityPct: 93.27 }, "primary");
  assert.ok(attrs.includes(`fill="${resolveAlignmentBandStyle("primary", 93.27).fill}"`));
  assert.match(attrs, /data-band-identity-pct="93.27"/);
  assert.match(alignmentBandSvgAttrs({}), /data-band-identity-pct=""/);
  assert.equal(alignmentBandTooltipMetrics({ identityPct: 93.27, alignLength: 10000 }), "Identity: 93.27% | Alignment length: 10,000 bp");
  assert.match(alignmentBandTooltipMetrics({ identityPct: 0 }), /^Identity: 0.00%/);
  assert.match(alignmentBandTooltipMetrics({ mapq: 60 }), /^Identity: Unknown/);
});
