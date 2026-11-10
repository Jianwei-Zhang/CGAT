import test from "node:test";
import assert from "node:assert/strict";
import { measureNativeSubviewHeight, resolveNativeSubviewFit, fitNativeSubviewWindow } from "../subview-native-fit.js";

function geometry(patch = {}) {
  return { height: 354, innerSize: { width: 1350, height: 700 }, outerSize: { width: 1350, height: 700 },
    position: { x: 100, y: 100 }, scale: 1.25,
    area: { position: { x: 0, y: 0 }, size: { width: 2560, height: 1400 } }, ...patch };
}
test("first open measures the natural content rather than a 560px flex window", () => {
  const node = { getBoundingClientRect: () => ({ top: 0, height: 560 }),
    querySelector: () => ({ getBoundingClientRect: () => ({ top: 0, bottom: 348, height: 348 }) }) };
  assert.equal(measureNativeSubviewHeight(node), 354);
  const fitted = resolveNativeSubviewFit(geometry());
  assert.deepEqual(fitted, { width: 1350, height: 443, x: 100, y: 100 });
});
test("large content is capped to the work area, excluding taskbar and window frame", () => {
  const fit = resolveNativeSubviewFit(geometry({ height: 5000,
    outerSize: { width: 1366, height: 739 }, position: { x: 2500, y: 1350 } }));
  assert.equal(fit.height, 1321); assert.equal(fit.width, 1350);
  assert.equal(fit.x, 1174); assert.equal(fit.y, 20);
});
test("small screens constrain initial width and retain practical minimum height", () => {
  const fit = resolveNativeSubviewFit(geometry({ height: 40,
    area: { position: { x: 0, y: 0 }, size: { width: 1024, height: 768 } } }));
  assert.equal(fit.width, 984); assert.equal(fit.height, 275);
  assert.equal(fit.x, 20);
});
test("monitor origins may be negative and are not clamped to Main or desktop zero", () => {
  const fit = resolveNativeSubviewFit(geometry({ position: { x: -2500, y: -200 },
    area: { position: { x: -1920, y: -300 }, size: { width: 1920, height: 1080 } } }));
  assert.equal(fit.x, -1900); assert.equal(fit.y, -200);
});
test("missing or invalid measurements never collapse a native window", () => {
  assert.equal(measureNativeSubviewHeight({ querySelector: () => null }), null);
  assert.equal(resolveNativeSubviewFit(geometry({ height: null })), null);
  assert.equal(resolveNativeSubviewFit(geometry({ height: NaN })), null);
  assert.equal(resolveNativeSubviewFit(geometry({ scale: 0 })), null);
});
function fixture({ small = false, monitorFails = false } = {}) {
  const calls = [], area = { position: { x: 0, y: 0 }, size: { width: small ? 1000 : 1920, height: 1080 } };
  let width = 1080, height = 560;
  const peer = { setTimeout,
    screen: { availWidth: 1920, availHeight: 1080 },
    __TAURI__: { window: { currentMonitor: async () => {
      if (monitorFails) throw Error("no monitor API"); return { workArea: area };
    } }, dpi: { PhysicalSize: class { constructor(width, height) { this.width = width; this.height = height; } },
      PhysicalPosition: class { constructor(x, y) { this.x = x; this.y = y; } } } },
  };
  const node = { ownerDocument: { defaultView: peer }, getBoundingClientRect: () => ({ top: 0, height }),
    querySelector: () => ({ getBoundingClientRect: () => {
      const contentHeight = width < 1080 ? 390 : 348;
      return { top: 0, bottom: contentHeight, height: contentHeight };
    } }) };
  const handle = { innerSize: async () => ({ width, height }), outerSize: async () => ({ width, height }),
    outerPosition: async () => ({ x: 100, y: 100 }), scaleFactor: async () => 1,
    async setSize(size) { calls.push(["size", size.width, size.height]); width = size.width; height = size.height; },
    async setPosition(position) { calls.push(["position", position.x, position.y]); },
  };
  return { node, peer, handle, calls };
}
test("hidden native window fits before showing without requiring animation frames", async () => {
  const f = fixture(); await fitNativeSubviewWindow(f.node, f.handle);
  assert.deepEqual(f.calls, [["size", 1080, 354]]);
});
test("constrained width is applied first, then wrapped controls are remeasured", async () => {
  const f = fixture({ small: true }); await fitNativeSubviewWindow(f.node, f.handle);
  assert.deepEqual(f.calls, [["size", 968, 560], ["size", 968, 396], ["position", 16, 100]]);
});
test("monitor lookup failure uses the native peer screen without blocking opening", async () => {
  const f = fixture({ monitorFails: true }); await fitNativeSubviewWindow(f.node, f.handle);
  assert.deepEqual(f.calls, [["size", 1080, 354]]);
});
test("closed, docked or manually resized views cancel a pending fit", async () => {
  const f = fixture(); let alive = true;
  f.handle.innerSize = async () => { alive = false; return { width: 1080, height: 560 }; };
  assert.equal(await fitNativeSubviewWindow(f.node, f.handle, () => alive), null);
  assert.deepEqual(f.calls, []);
});
test("manual resize during width reflow cannot be overwritten by the later height fit", async () => {
  const f = fixture({ small: true }); let automatic = true;
  const resize = f.handle.setSize;
  f.handle.setSize = async size => { await resize(size); automatic = false; };
  assert.equal(await fitNativeSubviewWindow(f.node, f.handle, () => automatic), null);
  assert.deepEqual(f.calls, [["size", 968, 560]]);
});


test("late fitting measures full content even when its container was scrolled", () => {
  const panel = { getBoundingClientRect: () => ({ height: 900, bottom: 700 }) };
  const node = { getBoundingClientRect: () => ({ top: 0 }),
    querySelector: selector => selector === "[data-subview-panel]" ? panel : { scrollTop: 200 } };
  assert.equal(measureNativeSubviewHeight(node), 906);
});
