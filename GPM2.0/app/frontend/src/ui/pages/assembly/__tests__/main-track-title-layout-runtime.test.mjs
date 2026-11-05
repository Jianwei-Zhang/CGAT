import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MAIN_TRACK_TITLE_LAYOUT_EVENT, bindMainTrackTitleLayout, destroyMainTrackTitleLayout, shouldCompactMainTrackTitle } from "../main-track-title-layout-runtime.js";
import { renderAssemblyPage, createState } from "./tabs-semantics-harness.mjs";

const HEADER = "[data-main-view-header]";
const LABEL = "[data-main-chr-title-full][data-main-chr-title-short]";
const widths = { availableWidth: 804, fullTitleWidth: 280, groupWidths: [200, 180, 120], headerGap: 8, toolbarGap: 8 };

test("full-title budget includes all groups/gaps/insets, not current row count or abbreviated width", () => {
  assert.equal(shouldCompactMainTrackTitle(widths), false);
  assert.equal(shouldCompactMainTrackTitle({ ...widths, availableWidth: 803 }), true);
  assert.equal(shouldCompactMainTrackTitle({ ...widths, availableWidth: 804.1 }), false);
  assert.equal(shouldCompactMainTrackTitle({ ...widths, availableWidth: 803.6 }), false, "subpixel rounding slack");
  assert.equal(shouldCompactMainTrackTitle({ ...widths, toolbarInsets: 2 }), true);
  assert.equal(shouldCompactMainTrackTitle({ ...widths, groupWidths: [200, 180, 120, 30] }), true);
  for (const change of [{ availableWidth: 0 }, { availableWidth: NaN }, { availableWidth: Infinity },
    { fullTitleWidth: 0 }, { groupWidths: [] }, { groupWidths: [200, NaN] }, { toolbarGap: -1 }]) {
    assert.equal(shouldCompactMainTrackTitle({ ...widths, ...change }), null);
  }
});

for (const locale of ["en", "zh"]) test(`only English has an abbreviated title; full identity/accessibility/tooltip survive (${locale})`, () => {
  const chrName = 'BSWB<&".1';
  const state = { ...createState({ assembly: { selectedChrName: chrName } }), locale };
  const html = renderAssemblyPage(state);
  const button = html.match(/<button id="assembly-chr-picker-toggle"[^>]+>/)[0];
  assert.match(button, /aria-label="[^"<>]*: BSWB&lt;&amp;&quot;\.1"/);
  assert.match(button, /data-app-tooltip-overflow="\.chr-picker-current"/);
  if (locale === "en") {
    assert.match(html, /data-main-chr-title-full="Chromosome BSWB&lt;&amp;&quot;\.1"/);
    assert.match(html, /data-main-chr-title-short="Chr BSWB&lt;&amp;&quot;\.1"/);
    assert.match(html, /class="chr-picker-current"[^>]*>Chromosome BSWB&lt;&amp;"\.1<\/span>/);
    assert.match(button, /data-app-tooltip="Chromosome BSWB&lt;&amp;&quot;\.1"/);
    assert.equal(html.match(/data-main-chr-title-short=/g)?.length, 1);
  } else {
    assert.doesNotMatch(html, /data-main-chr-title-(?:full|short)/);
    assert.match(html, /class="chr-picker-current">染色体 BSWB&lt;&amp;"\.1<\/span>/);
  }
});

test("empty English selection retains the full Choose chromosome prompt without abbreviation", () => {
  const html = renderAssemblyPage({ ...createState({ assembly: { selectedChrName: "" } }), locale: "en" });
  assert.match(html, /class="chr-picker-current">Choose chromosome<\/span>/);
  assert.doesNotMatch(html, /data-main-chr-title-(?:full|short)/);
});

function fixture({ english = true, observer = true } = {}) {
  const events = new Map(), fontEvents = new Map(), frames = new Map(), observers = [], writes = [], layoutEvents = [];
  let width = 900, fullWidth = 280, frameId = 0, current;
  const listen = map => (type, callback) => {
    const list = map.get(type) || new Set(); list.add(callback); map.set(type, list);
  };
  const unlisten = map => (type, callback) => map.get(type)?.delete(callback);
  const node = (widthFn, style = {}) => ({ style, getBoundingClientRect: () => ({ width: widthFn() }) });
  const makeHeader = () => {
    let text = "Chromosome BSWB01000001.1";
    const label = { dataset: { mainChrTitleFull: text, mainChrTitleShort: "Chr BSWB01000001.1" },
      get textContent() { return text; }, set textContent(value) { text = value; writes.push(value); } };
    const title = node(() => Math.min(label.textContent.startsWith("Chromosome") ? fullWidth : fullWidth - 60, (width - 20) / 2));
    const groups = [200, 180, 120].map(value => {
      const group = node(() => group.width, { display: "flex" }); group.width = value; return group;
    });
    const toolbar = { children: groups, style: { columnGap: "8px" } };
    const header = node(() => width, { columnGap: "8px", paddingLeft: "10px", paddingRight: "10px" });
    header.querySelector = selector => selector === LABEL ? english && label : selector === "[data-main-track-control-title]" ? title
      : selector === "[data-main-track-toolbar]" ? toolbar : null;
    return { header, label, groups, toolbar, title };
  };
  current = makeHeader();
  let ready;
  const fonts = { ready: new Promise(resolve => { ready = resolve; }),
    addEventListener: listen(fontEvents), removeEventListener: unlisten(fontEvents) };
  const win = { Event: class { constructor(type) { this.type = type; } }, getComputedStyle: element => element.style, addEventListener: listen(events), removeEventListener: unlisten(events),
    requestAnimationFrame: callback => { frames.set(++frameId, callback); return frameId; },
    cancelAnimationFrame: id => frames.delete(id),
    ResizeObserver: observer ? class {
      constructor(callback) { this.callback = callback; this.targets = new Set(); observers.push(this); }
      observe(target) { this.targets.add(target); }
      unobserve(target) { this.targets.delete(target); }
      disconnect() { this.targets.clear(); this.disconnected = true; }
    } : undefined };
  const host = { ownerDocument: { defaultView: win, fonts }, isConnected: true,
    dispatchEvent: event => layoutEvents.push({ type: event.type, label: current.label.textContent }),
    closest: () => host, querySelector: selector => selector === `${HEADER} ${LABEL}` ? english && current.label : null,
    querySelectorAll: selector => selector === HEADER ? [current.header] : [] };
  const input = { value: "unfinished draft", focused: true }, popup = { open: true };
  const emit = (map, name) => map.get(name)?.forEach(callback => callback());
  const flush = () => { const pending = [...frames.values()]; frames.clear(); pending.forEach(callback => callback()); };
  const resize = value => { width = value; emit(events, "resize"); flush(); };
  const notify = entries => observers.at(-1).callback(entries);
  const entry = (target, value, height = 30) => ({ target, contentRect: { width: value, height } });
  return { host, input, popup, events, frames, fontEvents, observers, writes, layoutEvents, flush, resize, notify, entry, ready,
    get label() { return current.label; }, get header() { return current.header; }, get groups() { return current.groups; },
    get toolbar() { return current.toolbar; }, setWidth: value => { width = value; }, setFullWidth: value => { fullWidth = value; },
    fontLoaded: () => emit(fontEvents, "loadingdone"), replaceHeader: () => { current = makeHeader(); } };
}

test("wide -> abbreviate before wrapping -> narrow fallback -> restore at FULL-title threshold", () => {
  const f = fixture(); bindMainTrackTitleLayout(f.host);
  assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
  f.resize(800); assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  assert.deepEqual(f.layoutEvents.at(-1), { type: MAIN_TRACK_TITLE_LAYOUT_EVENT, label: "Chr BSWB01000001.1" });
  f.resize(700); assert.equal(f.label.textContent, "Chr BSWB01000001.1", "CSS still owns wrapping when Chr cannot fit");
  f.resize(810); assert.equal(f.label.textContent, "Chr BSWB01000001.1", "do not restore just because short form fits");
  for (let i = 0; i < 5; i++) { f.resize(810); assert.equal(f.label.textContent, "Chr BSWB01000001.1"); }
  f.resize(825); assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
  assert.equal(f.input.value, "unfinished draft"); assert.equal(f.input.focused, true); assert.equal(f.popup.open, true);
  assert.equal(f.toolbar.children, f.groups, "no control moved or replaced");
});

test("container and group widths trigger coalesced updates without window resize; row heights do not", () => {
  const f = fixture(); bindMainTrackTitleLayout(f.host);
  const observed = f.observers[0]; assert.equal(observed.targets.size, 4);
  f.notify([f.entry(f.header, 880), ...f.groups.map(group => f.entry(group, group.width))]); f.flush();
  f.notify([f.entry(f.header, 880, 70)]);
  assert.equal(f.frames.size, 0, "wrapping height must not trigger another classification");
  f.setWidth(800); f.notify([f.entry(f.header, 780)]); f.notify([f.entry(f.header, 780, 70)]);
  assert.equal(f.frames.size, 1); f.flush(); assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  f.setWidth(900); f.groups[1].width = 300;
  f.notify([f.entry(f.header, 880), f.entry(f.groups[1], 300)]); f.flush();
  assert.equal(f.label.textContent, "Chr BSWB01000001.1", "wider parameter content also contributes to budget");
  f.groups[1].width = 180; f.notify([f.entry(f.groups[1], 180)]); f.flush();
  assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
});

test("rebinding observes replacement headers, retains one controller and rechecks cached compact labels", () => {
  const f = fixture(); f.setWidth(800); bindMainTrackTitleLayout(f.host);
  const oldHeader = f.header, oldGroups = f.groups;
  f.replaceHeader(); bindMainTrackTitleLayout(f.host);
  assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  assert.equal(f.observers.length, 1); assert.equal(f.events.get("resize").size, 1);
  assert.equal(f.observers[0].targets.has(oldHeader), false);
  assert.ok(oldGroups.every(group => !f.observers[0].targets.has(group)));
  f.setWidth(900); bindMainTrackTitleLayout(f.host);
  assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
});

test("font readiness/loading rechecks actual typography and the existing long-name cap", async () => {
  const f = fixture(); bindMainTrackTitleLayout(f.host);
  f.setFullWidth(380); f.ready(); await Promise.resolve(); f.flush();
  assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  f.setFullWidth(280); f.fontLoaded(); f.flush(); assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
  f.setFullWidth(1200); f.resize(2000);
  assert.equal(f.label.textContent, "Chromosome BSWB01000001.1", "use capped title allocation, not the unbounded chromosome text width");
});

test("hidden groups do not consume gaps or width, and hidden headers retain the current label", () => {
  const f = fixture(); f.groups[2].style.display = "none"; f.setWidth(700); bindMainTrackTitleLayout(f.host);
  assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
  f.groups[2].style.display = "flex"; f.resize(700); assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  f.resize(0); assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  f.resize(900); assert.equal(f.label.textContent, "Chromosome BSWB01000001.1");
});

test("Chinese never binds; missing ResizeObserver still supports binding and window resize", () => {
  const zh = fixture({ english: false }); bindMainTrackTitleLayout(zh.host);
  assert.equal(zh.observers.length, 0); assert.equal(zh.events.size, 0); assert.deepEqual(zh.writes, []);
  const f = fixture({ observer: false }); bindMainTrackTitleLayout(f.host); f.resize(800);
  assert.equal(f.label.textContent, "Chr BSWB01000001.1");
});

test("dispose cancels pending work and listeners; detached hosts destroy themselves; font promises cannot revive them", async () => {
  const f = fixture(); bindMainTrackTitleLayout(f.host); f.setWidth(800); f.fontLoaded();
  assert.equal(f.frames.size, 1); destroyMainTrackTitleLayout(f.host);
  assert.equal(f.frames.size, 0); assert.equal(f.events.get("resize").size, 0); assert.equal(f.fontEvents.get("loadingdone").size, 0);
  assert.equal(f.observers[0].disconnected, true);
  f.ready(); await Promise.resolve(); assert.equal(f.frames.size, 0);
  bindMainTrackTitleLayout(f.host); assert.equal(f.label.textContent, "Chr BSWB01000001.1");
  f.host.isConnected = false; f.resize(900); assert.equal(f.observers[1].disconnected, true);
});

test("new runtime is title-only and is wired into normal binding, cached-DOM sync and disposal", () => {
  const runtime = readFileSync(new URL("../main-track-title-layout-runtime.js", import.meta.url), "utf8");
  assert.doesNotMatch(runtime, /setState|store\.|persist|innerHTML|appendChild|replaceChildren|cloneNode|createElement|offsetTop|scrollHeight|flexWrap/);
  const bindings = readFileSync(new URL("../bindings.js", import.meta.url), "utf8");
  const page = readFileSync(new URL("../../assembly-page.js", import.meta.url), "utf8");
  assert.match(bindings, /bindMainTrackTitleLayout\(host\)/);
  assert.match(page, /export function syncAssemblyTransientInteractions[\s\S]*?bindMainTrackTitleLayout\(host\)/);
  assert.match(page, /export function disposeAssemblyTransientInteractions[\s\S]*?destroyMainTrackTitleLayout\(host\)/);
});
