import test from "node:test";
import assert from "node:assert/strict";
import { createTauriAssemblyOperations } from "../workflow/tauri/assembly.js";

test("reference IPC expands interleaved CIGAR fragments without losing any hit fields", async () => {
  const member = { sourceKind: "ref_segment", referenceChrId: 6, referenceChrName: "chr06",
    segmentOrder: 2, segmentStartBp: 1001, segmentEndBp: 5000, name: "ref_chr06", anchorStart: 1001,
    totalLength: 4000, refOrient: "+" };
  const wire = { encoding: "reference-hits-v1", items: [{ ...member,
    hitGroups: [[1, 2, 40, "-", 98.44, 60], [2, 1, 6, "+", 99.123456789, 0]],
    hitRows: [[0, 901, 910, 1001, 1010, 9, 10, 1, 10],
      [1, 2, 10, 1002, 1010, 8, 9, 2, 10],
      [0, 881, 900, 1011, 1030, 19, 20, 11, 30]],
  }, { ...member, segmentOrder: 3, hitGroups: [], hitRows: [] }] };
  const operations = createTauriAssemblyOperations({ invokeCommand: async (command, args) => {
    assert.equal(command, "list_reference_track_members");
    assert.equal(args.compact, true);
    return wire;
  } });
  const result = await operations.listReferenceTrackMembers({ workspaceRoot: "workspace", projectId: 1, chrName: "chr06" });
  assert.deepEqual(result.items[0], { ...member, hits: [
    { hitId: 1, datasetId: 2, sourceSeqId: 40, strand: "-", identityPct: 98.44, mapq: 60,
      queryStart: 901, queryEnd: 910, refStart: 1001, refEnd: 1010, matchLength: 9, blockLength: 10, ctgStart: 1, ctgEnd: 10 },
    { hitId: 2, datasetId: 1, sourceSeqId: 6, strand: "+", identityPct: 99.123456789, mapq: 0,
      queryStart: 2, queryEnd: 10, refStart: 1002, refEnd: 1010, matchLength: 8, blockLength: 9, ctgStart: 2, ctgEnd: 10 },
    { hitId: 1, datasetId: 2, sourceSeqId: 40, strand: "-", identityPct: 98.44, mapq: 60,
      queryStart: 881, queryEnd: 900, refStart: 1011, refEnd: 1030, matchLength: 19, blockLength: 20, ctgStart: 11, ctgEnd: 30 },
  ] });
  assert.deepEqual(result.items[1], { ...member, segmentOrder: 3, hits: [] });
});

test("reference IPC continues to accept legacy responses", async () => {
  const items = [{ hits: [{ hitId: 1 }] }];
  const operations = createTauriAssemblyOperations({ invokeCommand: async () => ({ items }) });
  assert.equal((await operations.listReferenceTrackMembers({})).items, items);
});
