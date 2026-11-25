import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import config, { macLocalViewIpcPolicy } from "../vite.config.js";

const popup = "/local-view.html?view=local-123&token=0123456789abcdef";
const transform = (platform, path, server) => macLocalViewIpcPolicy(platform).transformIndexHtml.handler("", { path, server });

test("only the Mac popup restricts fetch before its bootstrap; the release has no dev socket", () => {
  assert.ok(config.plugins.some(plugin => plugin.name === macLocalViewIpcPolicy().name));
  for (const platform of ["macos", "darwin"]) {
    for (const path of ["/local-view.html", popup]) {
      for (const server of [undefined, {}]) {
        const [meta] = transform(platform, path, server);
        assert.equal(meta.tag, "meta");
        assert.equal(meta.injectTo, "head-prepend");
        assert.equal(meta.attrs["http-equiv"], "Content-Security-Policy");
        assert.equal(meta.attrs.content, server ? "connect-src 'self' ws://127.0.0.1:5174" : "connect-src 'self'");
      }
    }
    assert.equal(transform(platform, "/index.html"), undefined);
  }
  for (const platform of ["win32", "windows", "linux"]) assert.equal(transform(platform, popup), undefined);
});

test("Local View geometry permissions stay with the popup, not its opener", () => {
  const capability = name => JSON.parse(readFileSync(new URL(`../../src-tauri/capabilities/${name}.json`, import.meta.url)));
  const main = capability("default"), child = capability("local-view");
  assert.deepEqual(main.windows, ["main"]);
  assert.deepEqual(child.windows, ["local-view-*"]);
  for (const name of ["set-size", "set-position", "set-title", "show"]) {
    assert.ok(child.permissions.includes(`core:window:allow-${name}`));
    assert.ok(!main.permissions.includes(`core:window:allow-${name}`));
  }
});
