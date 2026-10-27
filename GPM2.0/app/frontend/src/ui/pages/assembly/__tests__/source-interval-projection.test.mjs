import test from "node:test";
import assert from "node:assert/strict";
import { buildSourceIntervalProjection, intersectSourceInterval } from "../source-interval-projection.js";
import { resolveFinalPathSourceRange } from "../final-path-presentation.js";

const selected = { assemblyCtgId: 1, sourceStart: 5001, sourceEnd: 10000 };
const target = { assemblyCtgId: 1, sourceStart: 4001, sourceEnd: 8000, orient: "+" };

test("only intersecting adopted source bases are correlated, with reverse geometry", () => {
  assert.deepEqual(intersectSourceInterval(selected, target),
    { sourceStart: 5001, sourceEnd: 8000, startFraction: 0.25, endFraction: 1 });
  assert.deepEqual(intersectSourceInterval(selected, { ...target, orient: "-" }),
    { sourceStart: 5001, sourceEnd: 8000, startFraction: 0, endFraction: 0.75 });
  assert.equal(intersectSourceInterval(selected, { ...target, sourceEnd: 5000 }), null);
});

test("identical names never correlate unrelated Contigs or unequal known source IDs", () => {
  assert.equal(intersectSourceInterval(selected, { ...target, assemblyCtgId: 2 }), null);
  assert.equal(intersectSourceInterval({ ...selected, sourceSeqId: 1 }, { ...target, sourceSeqId: 2 }), null);
  assert.equal(intersectSourceInterval({ ...selected, contigName: "ctg1" }, { ...target, assemblyCtgId: 2, contigName: "ctg1" }), null);
});

test("source identities support split fragments, but intersection never expands to the full Contig", () => {
  const ctg = { assemblyCtgId: 2, totalLength: 3000,
    sourceFragment: { sourceSeqId: 7, sourceStart: 7001, sourceEnd: 10000 } };
  const projection = buildSourceIntervalProjection(ctg);
  assert.deepEqual(intersectSourceInterval({ ...selected, sourceSeqId: 7 }, projection),
    { sourceStart: 7001, sourceEnd: 10000, startFraction: 0, endFraction: 1 });
});

test("joined Local members intersect source ranges through retained backing parts", () => {
  const projection = buildSourceIntervalProjection({ lengthBp: 4000, localFragment: {
    sourceStart: 4001, sourceEnd: 8000, parts: [{ assemblyCtgId: 1, sourceStart: 4001, sourceEnd: 6000 },
      { assemblyCtgId: 2, sourceStart: 6001, sourceEnd: 8000 }] } }, "-");
  assert.deepEqual(intersectSourceInterval(selected, projection),
    { sourceStart: 5001, sourceEnd: 8000, startFraction: 0, endFraction: 0.75 });
});

test("reference absolute source bases cannot correlate with assembly IDs", () => {
  const projection = buildSourceIntervalProjection({ reference: { chrName: "Chr1", startBp: 4001, endBp: 8000 } });
  assert.equal(intersectSourceInterval(selected, projection), null);
  assert.equal(intersectSourceInterval({ ...selected, referenceChrName: "Chr2" }, projection), null);
  assert.equal(intersectSourceInterval({ ...selected, referenceChrName: "Chr1" }, projection).sourceStart, 5001);
});

test("invalid/missing source ranges fail closed rather than painting a whole Contig", () => {
  assert.equal(buildSourceIntervalProjection({ assemblyCtgId: 1 }), null);
  assert.equal(intersectSourceInterval(null, target), null);
  assert.equal(intersectSourceInterval({ ...selected, sourceStart: NaN }, target), null);
});

test("split source-located rows honor current committed coordinates without double offsets", () => {
  const ctg = { assemblyCtgId: 2, totalLength: 4000,
    sourceFragment: { sourceSeqId: 7, sourceStart: 6001, sourceEnd: 10000, sourceLength: 10000 } };
  const segment = { type: "ctg", splitFragmentCtgId: 2, start: 9000, end: 7001, overallLen: 10000,
    source: { dataset: "Data", contig: "ctg1", start: 6001, end: 10000 } };
  const source = resolveFinalPathSourceRange(segment, [ctg]);
  assert.equal(source.sourceStart, 7001); assert.equal(source.sourceEnd, 9000);
  assert.equal(source.orient, "-");
  assert.deepEqual(intersectSourceInterval(source, buildSourceIntervalProjection(ctg)),
    { sourceStart: 7001, sourceEnd: 9000, startFraction: 0.25, endFraction: 0.75 });
});


test("inclusive endpoints retain exactly one source base at a shared boundary", () => {
  assert.deepEqual(intersectSourceInterval({ ...selected, sourceStart: 8000 }, target),
    { sourceStart: 8000, sourceEnd: 8000, startFraction: 3999 / 4000, endFraction: 1 });
});
