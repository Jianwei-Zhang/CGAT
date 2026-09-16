import test from "node:test";
import assert from "node:assert/strict";
import { splitReferenceBandHit } from "../reference-band-segments.js";
import { renderAssemblyPage, createState } from "./tabs-semantics-harness.mjs";

const members = [
  { segmentStartBp: 1, segmentEndBp: 1000 },
  { segmentStartBp: 1101, segmentEndBp: 2100 },
];
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
