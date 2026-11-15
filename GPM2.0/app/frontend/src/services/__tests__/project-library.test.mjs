import test from "node:test";
import assert from "node:assert/strict";
import { PROJECT_LIBRARY_KEY, readProjectLibrary, saveProjectLibrary, editPartition, deleteEmptyPartition,
  partitionChoices, partitionAncestors, projectPartition, moveProjectToPartition } from "../project-library.js";
import { WORKSPACE_HISTORY_KEY, readWorkspaceHistory, writeWorkspaceHistory, updateWorkspaceHistory, reconcileWorkspaceHistory } from "../workspace-history.js";

const storage = () => {
  const data = new Map();
  return { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) };
};
function fixture() {
  let library = readProjectLibrary(storage());
  library = editPartition(library, { name: "植物" }); const plants = library.partitions.at(-1).id;
  library = editPartition(library, { name: "水稻", parentId: plants }); const rice = library.partitions.at(-1).id;
  library = editPartition(library, { name: "动物" }); const animals = library.partitions.at(-1).id;
  return { library, plants, rice, animals };
}

test("empty partitions can be created and persisted before any projects exist", () => {
  const s = storage(), { library, plants, rice } = fixture();
  saveProjectLibrary({ ...library, collapsed: [plants] }, s);
  assert.equal(readWorkspaceHistory(s).length, 0);
  assert.deepEqual(readProjectLibrary(s).collapsed, [plants]);
  assert.equal(partitionChoices(readProjectLibrary(s)).find(node => node.id === rice).path, "植物 / 水稻");
  assert.deepEqual(partitionAncestors(library, rice).map(node => node.id), [plants, rice]);
});

test("project moves change only membership and survive canonical path reconciliation", () => {
  const s = storage(), { library, rice } = fixture(); saveProjectLibrary(library, s);
  const record = { path: "D:\\data\\mh63\\", projectName: "mh63", lastUsedAt: 42, note: "keep" };
  writeWorkspaceHistory([record], s);
  moveProjectToPartition("D:/data/mh63", rice, s);
  assert.deepEqual(readWorkspaceHistory(s)[0], { ...record, partitionId: rice });
  reconcileWorkspaceHistory("D:/canonical/mh63", [record.path], s);
  assert.equal(readWorkspaceHistory(s)[0].partitionId, rice);
  moveProjectToPartition("D:/canonical/mh63", "", s);
  assert.equal(readWorkspaceHistory(s)[0].partitionId, "");
});

test("legacy and dangling memberships remain visible in unpartitioned without rewriting user data", () => {
  const { library } = fixture();
  assert.equal(projectPartition(library, { path: "/old" }), "");
  assert.equal(projectPartition(library, { path: "/old", partitionId: "deleted" }), "");
});

test("library no longer evicts the first project when adding the 21st or later", () => {
  const s = storage();
  const records = Array.from({ length: 100 }, (_, i) => ({ path: `/project-${i}`, partitionId: "rice", note: `${i}` }));
  writeWorkspaceHistory(records, s);
  writeWorkspaceHistory(updateWorkspaceHistory(readWorkspaceHistory(s), "/project-100", "Newest"), s);
  assert.equal(readWorkspaceHistory(s).length, 101);
  assert.deepEqual(readWorkspaceHistory(s)[0], records[0]);
});

test("partition moves keep descendant identities and prevent self/descendant cycles", () => {
  const { library, plants, rice, animals } = fixture();
  assert.throws(() => editPartition(library, { id: plants, parentId: rice }), /cycle/);
  assert.throws(() => editPartition(library, { id: plants, parentId: plants }), /cycle/);
  const moved = editPartition(library, { id: plants, parentId: animals });
  assert.equal(partitionChoices(moved).find(node => node.id === rice).path, "动物 / 植物 / 水稻");
  assert.equal(partitionChoices(library, plants).some(node => node.id === rice), false);
  assert.equal(editPartition(moved, { id: plants, parentId: "" }).partitions.find(node => node.id === plants).parentId, "");
});

test("names are trimmed, siblings are unique, and names under different parents can repeat", () => {
  const { library, plants, animals, rice } = fixture();
  assert.throws(() => editPartition(library, { name: " 水稻 ", parentId: plants }), /duplicate/);
  assert.throws(() => editPartition(library, { name: "   " }), /name/);
  assert.throws(() => editPartition(library, { name: "a".repeat(121) }), /name/);
  assert.throws(() => editPartition(library, { name: "X", parentId: "missing" }), /missing/);
  const renamed = editPartition(library, { id: rice, name: " 水稻试验 ", parentId: plants });
  assert.equal(renamed.partitions.find(node => node.id === rice).name, "水稻试验");
  assert.equal(editPartition(library, { name: "水稻", parentId: animals }).partitions.length, 4);
});

test("only empty partitions can be deleted; neither descendants nor project records are removed", () => {
  const { library, plants, rice } = fixture();
  assert.throws(() => deleteEmptyPartition(library, plants, []), /notEmpty/);
  const records = [{ path: "/rice", partitionId: rice }];
  assert.throws(() => deleteEmptyPartition(library, rice, records), /notEmpty/);
  assert.throws(() => deleteEmptyPartition(library, "", records), /missing/);
  assert.equal(deleteEmptyPartition(library, rice, []).partitions.length, 2);
  assert.deepEqual(records, [{ path: "/rice", partitionId: rice }]);
});

test("corrupt, cyclic, or future-version partition storage cannot be silently overwritten", () => {
  for (const raw of ["broken", JSON.stringify({ version: 2, partitions: [], collapsed: [] }),
    JSON.stringify({ version: 1, partitions: [{ id: "a", name: "a", parentId: "a" }], collapsed: [] })]) {
    const s = storage(); s.setItem(PROJECT_LIBRARY_KEY, raw);
    const library = readProjectLibrary(s);
    assert.equal(library.error, "storage");
    assert.throws(() => saveProjectLibrary(library, s), /storage/);
    assert.throws(() => editPartition(library, { name: "new" }), /storage/);
    assert.equal(s.getItem(PROJECT_LIBRARY_KEY), raw);
  }
});

test("missing targets and storage failures are reported rather than showing successful moves", () => {
  const s = storage(), { library, rice } = fixture(); saveProjectLibrary(library, s);
  writeWorkspaceHistory([{ path: "/rice" }], s); const before = s.getItem(WORKSPACE_HISTORY_KEY);
  assert.throws(() => moveProjectToPartition("/rice", "missing", s), /missing/);
  assert.throws(() => moveProjectToPartition("/missing", rice, s), /missing/);
  assert.equal(s.getItem(WORKSPACE_HISTORY_KEY), before);
  const broken = { getItem: s.getItem, setItem() { throw new Error("quota"); } };
  assert.throws(() => moveProjectToPartition("/rice", rice, broken), /storage/);
  assert.throws(() => saveProjectLibrary(library, broken), /storage/);
});
