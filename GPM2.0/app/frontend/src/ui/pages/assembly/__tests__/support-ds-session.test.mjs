import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSupportDsStorageKey,
  loadSupportDsState,
  reconcileSupportDsSelection,
  saveSupportDsState,
} from "../support-ds-session.js";

class MemoryStorage {
  constructor() {
    this.data = new Map();
  }

  getItem(key) {
    return this.data.has(key) ? this.data.get(key) : null;
  }

  setItem(key, value) {
    this.data.set(key, String(value));
  }

  removeItem(key) {
    this.data.delete(key);
  }
}

test("buildSupportDsStorageKey normalizes workspace path and project id", () => {
  assert.equal(
    buildSupportDsStorageKey("  /tmp/workspace  ", "42.9"),
    "gpm_next:assembly-support-ds:/tmp/workspace:42",
  );
});

test("saveSupportDsState and loadSupportDsState round-trip the selection", () => {
  const storage = new MemoryStorage();

  saveSupportDsState("/tmp/workspace", 42, { supportDatasetId: 77 }, storage);

  assert.equal(
    storage.getItem("gpm_next:assembly-support-ds:/tmp/workspace:42"),
    JSON.stringify({ supportDatasetId: 77 }),
  );
  assert.deepEqual(loadSupportDsState("/tmp/workspace", 42, storage), {
    supportDatasetId: 77,
  });
});

test("reconcileSupportDsSelection clears stale selection when candidates change", () => {
  const storage = new MemoryStorage();
  const workspacePath = "/tmp/workspace";
  const projectId = 42;
  const storageKey = buildSupportDsStorageKey(workspacePath, projectId);

  storage.setItem(storageKey, JSON.stringify({ supportDatasetId: 77 }));

  const result = reconcileSupportDsSelection({
    workspacePath,
    projectId,
    currentSelection: 77,
    candidateIds: [88, 99],
    storage,
  });

  assert.deepEqual(result, {
    supportDatasetId: null,
    invalidated: true,
  });
  assert.equal(storage.getItem(storageKey), null);
  assert.equal(loadSupportDsState(workspacePath, projectId, storage), null);
});

test("reconcileSupportDsSelection preserves valid selection for set candidates", () => {
  const storage = new MemoryStorage();
  const workspacePath = "/tmp/workspace";
  const projectId = 42;

  const result = reconcileSupportDsSelection({
    workspacePath,
    projectId,
    currentSelection: 77,
    candidateIds: new Set([77, 88]),
    storage,
  });

  assert.deepEqual(result, {
    supportDatasetId: 77,
    invalidated: false,
  });
  assert.equal(storage.getItem(buildSupportDsStorageKey(workspacePath, projectId)), null);
});

test("reconcileSupportDsSelection clears stale selection for set candidates", () => {
  const storage = new MemoryStorage();
  const workspacePath = "/tmp/workspace";
  const projectId = 42;
  const storageKey = buildSupportDsStorageKey(workspacePath, projectId);

  storage.setItem(storageKey, JSON.stringify({ supportDatasetId: 77 }));

  const result = reconcileSupportDsSelection({
    workspacePath,
    projectId,
    currentSelection: 77,
    candidateIds: new Set([88, 99]),
    storage,
  });

  assert.deepEqual(result, {
    supportDatasetId: null,
    invalidated: true,
  });
  assert.equal(storage.getItem(storageKey), null);
});
