import test from "node:test";
import assert from "node:assert/strict";
import { workspacePathIdentity, updateWorkspaceHistory, reconcileWorkspaceHistory, readWorkspaceHistory, writeWorkspaceHistory } from "../workspace-history.js";

function storage(initial) {
  let value = JSON.stringify(initial); return { getItem: () => value, setItem: (_key, next) => { value = next; } };
}
test("same workspace path spelling preserves order and all existing metadata", () => {
  const records = [{ path: "D:\\data\\sample\\", projectName: "Edited", note: "user note", lastUsedAt: 1 },
    { path: "D:/data/other", projectName: "Other" }];
  const next = updateWorkspaceHistory(records, "D:/data/sample", "", 10);
  assert.equal(next.length, 2); assert.equal(next[0].path, "D:/data/sample");
  assert.equal(next[0].projectName, "Edited"); assert.equal(next[0].note, "user note");
  assert.equal(next[0].lastUsedAt, 10); assert.deepEqual(next[1], records[1]);
});
test("native canonical aliases collapse duplicate legacy cards without losing metadata", () => {
  const s = storage([{ path: "/link", projectName: "Custom", note: "keep", lastUsedAt: 1 },
    { path: "/other", projectName: "Independent" }, { path: "/real", extra: "retain" }]);
  reconcileWorkspaceHistory("/real", ["/link", "/real"], s);
  assert.deepEqual(readWorkspaceHistory(s), [{ path: "/real", projectName: "Custom", note: "keep", lastUsedAt: 1, extra: "retain" },
    { path: "/other", projectName: "Independent" }]);
});
test("distinct copies and case-sensitive paths are never merged by name", () => {
  const s = storage([{ path: "/Project", projectName: "Same" }, { path: "/project", projectName: "Same" }]);
  reconcileWorkspaceHistory("/Project", [], s); assert.equal(readWorkspaceHistory(s).length, 2);
  assert.equal(updateWorkspaceHistory(readWorkspaceHistory(s), "/copy", "Same", 20).length, 3);
});
test("extended Windows and UNC paths normalize structurally without assuming case semantics", () => {
  assert.equal(workspacePathIdentity("\\\\?\\C:\\Data\\Project\\"), "C:/Data/Project");
  assert.equal(workspacePathIdentity("\\\\?\\UNC\\server\\share\\project\\"), "//server/share/project");
  assert.notEqual(workspacePathIdentity("C:/Data"), workspacePathIdentity("C:/data"));
});
test("the shared parser handles legacy strings, corrupt storage, and duplicate writers", () => {
  const s = storage(["/legacy", { path: "/legacy/", note: "note" }, { path: "" }]);
  assert.deepEqual(readWorkspaceHistory(s), [{ path: "/legacy", note: "note", lastUsedAt: 0 }]);
  writeWorkspaceHistory(updateWorkspaceHistory(readWorkspaceHistory(s), "/legacy", "Project", 1), s);
  writeWorkspaceHistory(updateWorkspaceHistory(readWorkspaceHistory(s), "/legacy/", "Project", 2), s);
  assert.equal(readWorkspaceHistory(s).length, 1);
  assert.deepEqual(readWorkspaceHistory({ getItem: () => "broken" }), []);
});

test("literal backslashes in case-sensitive POSIX directory names remain distinct", () => {
  assert.notEqual(workspacePathIdentity("/data/a\\b"), workspacePathIdentity("/data/a/b"));
  assert.equal(updateWorkspaceHistory([{ path: "/data/a\\b" }], "/data/a/b", "Other").length, 2);
});
