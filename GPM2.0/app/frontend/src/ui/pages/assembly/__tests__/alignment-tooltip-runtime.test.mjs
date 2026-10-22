import test from "node:test";
import assert from "node:assert/strict";
import { bindAlignmentTooltips } from "../alignment-tooltip-runtime.js";
import { __testCreateSubviewBandTooltipCoordinator } from "../../assembly-page.js";

function fixture() {
  const timers = new Map(), events = new Map(); let id = 0, tooltip;
  const host = { isConnected: true, children: [], closest() { return this; },
    contains(node) { return this.children.includes(node); }, append(node) { this.children.push(node); },
    addEventListener(type, callback) { const list = events.get(type) || []; list.push(callback); events.set(type, list); },
    ownerDocument: { defaultView: { innerWidth: 900, innerHeight: 600 }, createElement() {
      const classes = new Set(["is-hidden"]);
      tooltip = { style: {}, textContent: "", attrs: {}, offsetWidth: 240, offsetHeight: 100,
        classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value) },
        setAttribute(key, value) { this.attrs[key] = value; } }; return tooltip;
    } },
  };
  const options = { createCoordinator: __testCreateSubviewBandTooltipCoordinator,
    timerApi: { setTimeout(callback, delay) { timers.set(++id, { callback, delay }); return id; }, clearTimeout: key => timers.delete(key) } };
  const fire = (type, target, extra = {}) => events.get(type)?.forEach(callback => callback({ target, clientX: 899, clientY: 599, ...extra }));
  const band = text => ({ isConnected: true, getAttribute: () => text, closest() { return this; }, contains: () => false });
  const flush = () => { const queued = [...timers.values()]; timers.clear(); queued.forEach(timer => timer.callback()); };
  bindAlignmentTooltips(host, options);
  return { host, options, timers, events, fire, band, flush, tooltip: () => tooltip };
}

test("all alignment payloads share the delayed styled panel, escaped text and viewport bounds", () => {
  const h = fixture();
  for (const text of ["ctgA: 1–100 | Ref: 2–101 | Identity: 99%", "GRT evidence · MUMmer · <unsafe>"]) {
    const band = h.band(text);
    h.fire("pointerover", band);
    assert.equal([...h.timers.values()][0].delay, 500);
    assert.equal(h.tooltip().attrs["aria-hidden"], "true");
    h.flush();
    assert.equal(h.tooltip().textContent, text.replaceAll(" | ", "\n").replaceAll(" · ", "\n"));
    assert.equal(h.tooltip().attrs["aria-hidden"], "false");
    assert.equal(h.tooltip().style.left, "652px"); assert.equal(h.tooltip().style.top, "492px");
    h.fire("pointermove", band, { clientX: 20, clientY: 30 }); assert.equal(h.tooltip().style.left, "34px");
    h.fire("pointerout", band); assert.equal(h.tooltip().attrs["aria-hidden"], "true");
  }
});

test("delegation survives patched evidence and route markup replacement without duplicate listeners", () => {
  const h = fixture(); bindAlignmentTooltips(h.host, h.options);
  assert.equal(h.events.get("pointerover").length, 1);
  const old = h.band("old"); h.fire("pointerover", old); old.isConnected = false; h.flush();
  assert.equal(h.tooltip().attrs["aria-hidden"], "true");
  h.host.children = [];
  const next = h.band("new evidence"); h.fire("pointerover", next); h.flush();
  assert.ok(h.host.contains(h.tooltip())); assert.equal(h.tooltip().textContent, "new evidence");
  for (const type of ["scroll", "contextmenu", "pointerdown", "keydown"]) {
    h.fire(type, next); assert.equal(h.tooltip().attrs["aria-hidden"], "true");
    h.fire("pointerover", next); h.flush();
  }
  h.fire("pointerout", next); assert.equal(h.timers.size, 0);
});
