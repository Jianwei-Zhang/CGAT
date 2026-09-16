import test from "node:test";
import assert from "node:assert/strict";
import { splitReferenceBandHit } from "../reference-band-segments.js";
import { buildTrackRectsWithMinGap } from "../track-render-geometry.js";
import { renderAssemblyPage, createState } from "./tabs-semantics-harness.mjs";

const members = [
  { segmentStartBp: 1, segmentEndBp: 1000 },
  { segmentStartBp: 1101, segmentEndBp: 2100 },
];

test("reference visual gaps translate fragments without shrinking their base-length scale", () => {
  const ctgs = [
    { startBp: 1, lengthBp: 440000, laneIndex: 0 },
    { startBp: 440101, lengthBp: 160000, laneIndex: 0 },
    { startBp: 600201, lengthBp: 7800000, laneIndex: 0 },
  ];
  const scale = { windowStart: 0, domainSpanBp: 30000000, innerWidth: 1800 };
  const natural = buildTrackRectsWithMinGap(ctgs, scale);
  const displayed = buildTrackRectsWithMinGap(ctgs, { ...scale, minGapPx: 15, preserveWidths: true });
  displayed.forEach((rect, index) => {
    assert.equal(rect.width, natural[index].width);
    if (index) assert.ok(rect.x - displayed[index - 1].x - displayed[index - 1].width >= 15 - 1e-8);
  });
});

test("crowded reference names are hidden but the full fragment hover title remains", () => {
  const fragments = [
    { segmentStartBp: 1, segmentEndBp: 100, name: "reference-first-long-name" },
    { segmentStartBp: 201, segmentEndBp: 300, name: "reference-second-long-name" },
    { segmentStartBp: 401, segmentEndBp: 30000000, name: "reference-last" },
  ];
  const html = renderAssemblyPage(createState({ assembly: {
    selectedChrName: "Chr01", chromosomes: [{ chrName: "Chr01", chrLength: 30000000 }],
    refTrackMembers: fragments,
  } }));
  assert.equal([...html.matchAll(/track-reference-member-label is-ref is-collision-hidden/g)].length, 2);
  assert.match(html, /<title>reference-first-long-name \| start=1 \| end=100<\/title>/);
  assert.match(html, /track-reference-member-label is-ref"/);
});
test("legacy bands skip reference gaps and preserve orientation without claiming exact mapping", () => {
  const hit = { refStart: 1, refEnd: 2100, ctgStart: 1, ctgEnd: 2100 };
  for (const reversed of [false, true]) {
    const parts = splitReferenceBandHit(hit, members, reversed);
    assert.deepEqual(parts.map((part) => [part.refStart, part.refEnd]), [[1,1000], [1101,2100]]);
    assert.deepEqual(parts.map((part) => [Math.round(part.ctgStart), Math.round(part.ctgEnd)]),
      reversed ? [[1101,2100], [1,1000]] : [[1,1000], [1101,2100]]);
    assert.ok(parts.every((part) => part.referenceProjectionApproximate));
  }
  assert.deepEqual(splitReferenceBandHit({ ...hit, refStart: 1001, refEnd: 1100 }, members), []);
  const exact = { ...hit, refEnd: 1000, ctgEnd: 950 };
  assert.deepEqual(splitReferenceBandHit(exact, members), [exact]);
  const tinyQuery = { ...hit, ctgStart: 8, ctgEnd: 8 };
  for (const reversed of [false, true]) {
    const parts = splitReferenceBandHit(tinyQuery, members, reversed);
    assert.ok(parts.every(part => part.ctgStart === 8 && part.ctgEnd === 8));
  }
});

test("rendered bands end on reference fragment rectangles after the minimum visual gap is applied", () => {
  const state = createState({ assembly: {
    selectedChrName: "Chr01", chromosomes: [{ chrName: "Chr01", chrLength: 2100 }],
    refTrackMembers: members,
    chrCtgs: [{ assemblyCtgId: 1, name: "ctg", totalLength: 2000, refOrient: "+",
      hits: [{ refStart: 1, refEnd: 1000, ctgStart: 1, ctgEnd: 1000, blockLength: 2000 },
        { refStart: 1101, refEnd: 2100, ctgStart: 1001, ctgEnd: 2000, blockLength: 2000 }] }],
    trackView: { alignmentLength: 1 },
  } });
  const html = renderAssemblyPage(state);
  const refs = [...html.matchAll(/class="track-reference-member[^\"]*"\s+x="([\d.]+)"[\s\S]*?width="([\d.]+)"/g)];
  const bands = [...html.matchAll(/<polygon class="track-collinearity-band[^>]*data-band-approximate="0"[^>]*points="([^"]+)"/g)];
  assert.equal(refs.length, 2);
  assert.equal(bands.length, 2);
  bands.forEach((band, index) => {
    const xs = band[1].trim().split(/\s+/).slice(0,2).map((point) => Number(point.split(",")[0]));
    const left = Number(refs[index][1]), right = left + Number(refs[index][2]);
    assert.ok(xs.every((x) => x >= left - 0.02 && x <= right + 0.02), `${xs} inside ${left}..${right}`);
    assert.ok(Math.abs(Math.min(...xs) - left) <= 0.02);
    assert.ok(Math.abs(Math.max(...xs) - right) <= 0.02);
  });
});

test("minimum visual gaps never truncate a band at the nominal ruler end", () => {
  const fragments = Array.from({ length: 30 }, (_, i) => ({ segmentStartBp: i * 101 + 1, segmentEndBp: i * 101 + 100 }));
  const last = fragments.at(-1);
  const state = createState({ assembly: {
    selectedChrName: "Chr01", chromosomes: [{ chrName: "Chr01", chrLength: last.segmentEndBp }],
    refTrackMembers: fragments,
    chrCtgs: [{ assemblyCtgId: 1, name: "ctg", totalLength: 100, refOrient: "+",
      hits: [{ refStart: last.segmentStartBp, refEnd: last.segmentEndBp, ctgStart: 1, ctgEnd: 100, blockLength: 100 }] }],
    trackView: { alignmentLength: 1 },
  } });
  const html = renderAssemblyPage(state);
  const rect = [...html.matchAll(/class="track-reference-member[^\"]*"\s+x="([\d.]+)"[\s\S]*?width="([\d.]+)"/g)].at(-1);
  const polygon = html.match(/<polygon class="track-collinearity-band[^>]*points="([^"]+)"/);
  const xs = polygon[1].split(/\s+/).slice(0, 2).map(point => Number(point.split(",")[0]));
  assert.ok(Math.abs(Math.max(...xs) - Number(rect[1]) - Number(rect[2])) <= 0.02);
});
