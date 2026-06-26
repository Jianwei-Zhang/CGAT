import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";

import {
  resolveDefaultBackendExe,
  resolveRootDirFromFileUrl,
} from "../dev-bridge-paths.js";

test("resolveRootDirFromFileUrl preserves Windows drive-letter paths", () => {
  const rootDir = resolveRootDirFromFileUrl(
    "file:///D:/Desktop/GPM/gpm_next/app/frontend/vite.config.js",
    path.win32,
  );
  const backendExe = resolveDefaultBackendExe(rootDir, path.win32);

  assert.equal(rootDir, "D:\\Desktop\\GPM\\gpm_next\\app\\frontend");
  assert.equal(
    backendExe,
    "D:\\Desktop\\GPM\\gpm_next\\app\\backend\\target\\debug\\gpm_next_backend.exe",
  );
  assert.doesNotMatch(backendExe, /^D:\\D:/);
});

test("resolveRootDirFromFileUrl handles POSIX file URLs", () => {
  const rootDir = resolveRootDirFromFileUrl(
    "file:///mnt/d/desktop/gpm/gpm_next/app/frontend/vite.config.js",
    path.posix,
  );

  assert.equal(rootDir, "/mnt/d/desktop/gpm/gpm_next/app/frontend");
});
