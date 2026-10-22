import { readFileSync } from "node:fs";
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
  const band = (text, { classes = [], identity = "95", gap = false } = {}) => ({ isConnected: true,
    getAttribute: name => name === "data-band-identity-pct" ? identity : text,
    matches: selector => selector.split(".").filter(Boolean).every(name => classes.includes(name)),
    closest(selector) { return selector === ".is-gap" ? gap ? {} : null : this; }, contains: () => false });
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


test("tooltip follows blue/orange bands in every view, including transparent Canvas proxies", () => {
  const h = fixture();
  for (const [classes, identity, tone] of [
    [["track-collinearity-band"], "95", "primary"],
    [["track-collinearity-band", "is-companion"], "90", "companion"],
    [["track-collinearity-band"], "0", "primary"],
    [["track-collinearity-band", "is-companion"], "", "neutral"],
    [["grt-display-evidence-band", "is-mummer"], "95", "purple"],
    [["grt-display-evidence-band", "is-minimap2"], "95", "teal"],
    [["grt-result-hover-proxy"], "95", "green"],
  ]) {
    const band = h.band("alignment", { classes, identity });
    h.fire("pointerover", band); h.flush();
    assert.equal(h.tooltip().attrs["data-alignment-tone"], tone);
    h.fire("pointerout", band);
  }
  const gap = h.band("Gap", { classes: ["grt-result-hover-proxy"], gap: true });
  h.fire("pointerover", gap); h.flush();
  assert.equal(h.tooltip().attrs["data-alignment-tone"], "neutral");
});

test("blue and orange tooltip surfaces, borders and ink reuse the shared theme palettes", () => {
  const css = readFileSync(new URL("../../../../styles/subview.css", import.meta.url), "utf8");
  for (const role of ["primary", "companion"]) {
    const rule = css.match(new RegExp(`\\.alignment-band-tooltip\\[data-alignment-tone="${role}"\\]\\s*\\{([^}]*)\\}`))?.[1] || "";
    assert.ok(rule.includes(`background: var(--ctg-${role}-fill)`));
    assert.ok(rule.includes(`border-color: var(--ctg-${role}-stroke)`));
    assert.ok(rule.includes(`color: var(--ctg-${role}-text)`));
  }
});
