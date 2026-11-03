import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { decodeReferenceTracks } from "../workflow/reference-transport.js";
import { hasDeferredReferenceHits, readReferenceHits, iterateReferenceHits, iterateReferenceHitEntries } from "../workflow/reference-evidence.js";
import { createTauriAssemblyOperations } from "../workflow/tauri/assembly.js";
import { packReferenceWire } from "./reference-transport-fixture.mjs";

const golden = JSON.parse(readFileSync(new URL("../../../../backend/testdata/reference_transport_v2.json", import.meta.url)));
const expected = decodeReferenceTracks(golden.legacy);

for (const format of ["legacy", "packed"]) {
  test(`${format}: Rust-shared rows preserve every field/order, interleaving, empty members, zero MAPQ and precision`, () => {
    assert.deepEqual(decodeReferenceTracks(golden[format]), expected);
    const result = decodeReferenceTracks(golden[format], { deferHits: true });
    for (const [index, member] of result.items.entries()) {
      assert.ok(hasDeferredReferenceHits(member));
      assert.equal(Object.hasOwn(member, "hits"), false, "deferred is explicit, not a fabricated empty hits array");
      assert.deepEqual(readReferenceHits(member), expected.items[index].hits);
      assert.equal(readReferenceHits(member), readReferenceHits(member), "immutable evidence shares derived arrays");
      for (const datasetId of [1, 2, 3, 99]) {
        assert.deepEqual(readReferenceHits(member, { datasetId }), expected.items[index].hits.filter(hit => hit.datasetId === datasetId));
      }
    }
  });

  test(`${format}: deferred evidence survives structuredClone and JSON cache round trips`, () => {
    const deferred = decodeReferenceTracks(golden[format], { deferHits: true });
    for (const clone of [structuredClone(deferred), JSON.parse(JSON.stringify(deferred))]) {
      assert.deepEqual(clone, deferred);
      assert.deepEqual(clone.items.map(member => readReferenceHits(member)), expected.items.map(item => item.hits));
    }
  });

  test(`${format}: render-time filtering does not renumber dataset-filtered anchor indices or mutate packed rows`, () => {
    const member = decodeReferenceTracks(golden[format], { deferHits: true }).items[0];
    const before = JSON.stringify(member);
    const entries = [...iterateReferenceHitEntries({ ...member, referenceDatasetId: 2 }, {
      acceptRow: (_group, row, index) => row[5] >= 15 || index === 2,
    })];
    assert.deepEqual(entries.map(entry => entry.index), [1, 2]);
    assert.deepEqual(entries.map(entry => entry.hit), expected.items[0].hits.filter(hit => hit.datasetId === 2).slice(1));
    assert.equal(JSON.stringify(member), before);
    assert.deepEqual([...iterateReferenceHits(member)], expected.items[0].hits);
  });
}

test("packed negotiation is explicit; old servers returning v1 still support deferred consumers", async () => {
  for (const wire of [golden.legacy, golden.packed]) {
    const calls = [];
    const operations = createTauriAssemblyOperations({ invokeCommand: async (command, args) => { calls.push({ command, args }); return wire; } });
    const full = await operations.listReferenceTrackMembers({ workspaceRoot: "scope", projectId: 1, chrName: "chr06" });
    assert.deepEqual(full, expected);
    assert.equal(calls[0].args.encoding, undefined);
    const deferred = await operations.listReferenceTrackMembers({ workspaceRoot: "scope", projectId: 1, chrName: "chr06", deferHits: true });
    assert.equal(calls[1].args.encoding, "reference-hits-v2");
    assert.equal(calls[1].args.compact, true);
    assert.deepEqual(readReferenceHits(deferred.items[0]), expected.items[0].hits);
  }
});

test("big signed deltas retain exact safe-integer coordinates, including crossing zero", () => {
  const safe = Number.MAX_SAFE_INTEGER;
  const legacy = structuredClone(golden.legacy);
  legacy.items[0].hitRows = [[0, safe, safe, safe, safe, 1, 1, safe, safe], [0, -safe, 0, 0, safe, 1, 1, 0, safe]];
  const packed = packReferenceWire(legacy);
  assert.deepEqual(decodeReferenceTracks(packed), decodeReferenceTracks(legacy));
});

test("legacy object arrays are still usable without hidden state or reference-only assumptions", () => {
  const hits = [{ hitId: 1, datasetId: 2 }];
  const member = { hits };
  assert.equal(readReferenceHits(member), hits);
  assert.deepEqual([...iterateReferenceHits(member)], hits);
  assert.deepEqual(readReferenceHits(member, { datasetId: 99 }), []);
  assert.equal(decodeReferenceTracks({ items: [member] }).items[0], member);
});

test("malformed packed evidence fails explicitly rather than silently dropping rows", () => {
  const original = golden.packed.items[0];
  const malformed = [
    { ...original, hitCount: original.hitCount + 1 },
    { ...original, hitCount: original.hitCount - 1 },
    { ...original, hitCount: -1 },
    { ...original, hitData: original.hitData.slice(0, -4) },
    { ...original, hitData: "!!!!" },
    { ...original, hitData: Buffer.from([99, ...Array(8).fill(0)]).toString("base64"), hitCount: 1 },
    { ...original, hitData: Buffer.from(Array(15).fill(128)).toString("base64"), hitCount: 1 },
    { ...original, hitGroups: [[1, 2, 40, "+", NaN, 60]] },
  ];
  for (const member of malformed) assert.throws(() => decodeReferenceTracks({ encoding: "reference-hits-v2", items: [member] }));
  const unsafe = structuredClone(golden.legacy);
  unsafe.items[0].hitRows = [[0, 9007199254740992n, 1, 1, 1, 1, 1, 1, 1]];
  assert.throws(() => decodeReferenceTracks(packReferenceWire(unsafe)));
  assert.throws(() => decodeReferenceTracks({ encoding: "unknown", items: [] }), /Unsupported/);
});

test("separate immutable payloads never share a stale materialized cache", () => {
  const first = decodeReferenceTracks(golden.packed, { deferHits: true }).items[0];
  const next = decodeReferenceTracks(structuredClone(golden.packed), { deferHits: true }).items[0];
  assert.deepEqual(readReferenceHits(first), readReferenceHits(next));
  assert.notEqual(readReferenceHits(first), readReferenceHits(next));
});

test("shared derived views cannot be mutated into scientific cache corruption; ordinary API arrays remain mutable", () => {
  const member = decodeReferenceTracks(golden.packed, { deferHits: true }).items[0];
  const hits = readReferenceHits(member);
  assert.throws(() => { hits[0].refStart = 999; }, TypeError);
  assert.throws(() => hits.pop(), TypeError);
  assert.deepEqual(readReferenceHits(member), expected.items[0].hits);
  const ordinary = decodeReferenceTracks(golden.packed);
  assert.equal(Object.isFrozen(ordinary.items[0].hits), false);
  assert.equal(Object.isFrozen(ordinary.items[0].hits[0]), false);
});

test("excluded dataset views still reject truncated varints instead of accepting incomplete evidence", () => {
  const member = structuredClone(golden.packed.items[0]);
  const bytes = Buffer.from(member.hitData, "base64");
  bytes[bytes.length - 1] |= 128;
  member.hitData = bytes.toString("base64");
  const deferred = decodeReferenceTracks({ encoding: "reference-hits-v2", items: [member] }, { deferHits: true }).items[0];
  assert.throws(() => Array.from(iterateReferenceHits(deferred, { datasetId: 99 })), /Invalid/);
});
