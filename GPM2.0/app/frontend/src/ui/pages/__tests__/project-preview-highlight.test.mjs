import test from "node:test";
import assert from "node:assert/strict";
import { createProjectPreviewHighlight } from "../project-preview-highlight.js";
import { buildProjectPreviewModel } from "../project-preview-state.js";
import { renderProjectPreviewCard } from "../project-preview-page.js";
import { getMessages } from "../../i18n/index.js";

const KEY = "data-preview-part-key", ACTIVE = "data-preview-highlighted";
class Node {
  constructor(attrs = {}, parent = null) {
    this.attrs = { ...attrs }; this.parent = parent; this.children = []; this.listeners = new Map(); this.queries = 0;
    parent?.children.push(this);
  }
  getAttribute(name) { return this.attrs[name] ?? null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  contains(node) { for (; node; node = node.parent) if (node === this) return true; return false; }
  closest(selector) {
    if (selector === "[data-preview-chr]" && this.attrs["data-preview-chr"]) return this;
    if (selector === "[data-preview-part-key][data-final-path-kind='ctg']" && this.attrs[KEY]
      && this.attrs["data-final-path-kind"] === "ctg") return this;
    return this.parent?.closest(selector) || null;
  }
  querySelectorAll(selector) {
    assert.equal(selector, "[data-preview-part-key]"); this.queries++;
    const collect = node => node.children.flatMap(child => [...(child.attrs[KEY] ? [child] : []), ...collect(child)]);
    return collect(this);
  }
  addEventListener(name, fn) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set()); this.listeners.get(name).add(fn);
  }
  removeEventListener(name, fn) { this.listeners.get(name)?.delete(fn); }
  emit(name, event = {}) { for (const fn of this.listeners.get(name) || []) fn({ type: name, target: this, ...event }); }
}
function fixture() {
  const host = new Node(), doc = new Node(), win = new Node(); host.ownerDocument = doc; doc.defaultView = win;
  const keyA = JSON.stringify(['Chr1A["quoted"]', 0]), keyB = JSON.stringify(['Chr1A["quoted"]', 2]);
  const card = new Node({ "data-preview-chr": "Chr1" }, host), header = new Node({}, card);
  const source = new Node({ name: "reused-source" }, card);
  const patchA = new Node({ [KEY]: keyA }, source), patchB = new Node({ [KEY]: keyB }, source);
  const refPatch = new Node({ [KEY]: keyA }, card);
  const resultA = new Node({ [KEY]: keyA, "data-final-path-kind": "ctg" }, card), label = new Node({}, resultA);
  const resultB = new Node({ [KEY]: keyB, "data-final-path-kind": "ctg" }, card);
  const phase = new Node({ [KEY]: JSON.stringify(["Chr1B", 0]), "data-final-path-kind": "ctg" }, card);
  const phasePatch = new Node({ [KEY]: phase.attrs[KEY] }, card);
  const gap = new Node({ "data-final-path-kind": "gap" }, card);
  const otherCard = new Node({ "data-preview-chr": "Chr2" }, host);
  const otherResult = new Node({ [KEY]: keyA, "data-final-path-kind": "ctg" }, otherCard);
  const otherPatch = new Node({ [KEY]: keyA }, otherCard);
  const nodes = [patchA, patchB, refPatch, resultA, resultB, phase, phasePatch, gap, otherResult, otherPatch, source, header];
  let enabled = true;
  const runtime = createProjectPreviewHighlight(host, { active: () => enabled }); runtime.start();
  const lit = () => nodes.filter(node => node.getAttribute(ACTIVE) === "1");
  return { host, doc, win, card, header, source, patchA, patchB, refPatch, resultA, resultB, label, phase, phasePatch,
    gap, otherCard, otherResult, otherPatch, runtime, lit, disable: () => { enabled = false; } };
}

test("hover links one exact path/index within one card, including its reference and reused-source interval", () => {
  const f = fixture(); assert.deepEqual(f.lit(), []);
  f.host.emit("pointerover", { target: f.resultA });
  assert.deepEqual(f.lit(), [f.patchA, f.refPatch, f.resultA]);
  assert.equal(f.host.queries, 0, "never scan all cards"); assert.equal(f.otherCard.queries, 0);
  f.host.emit("pointerover", { target: f.resultB });
  assert.deepEqual(f.lit(), [f.patchB, f.resultB], "the same contig's other adopted interval is independent");
  f.host.emit("pointerover", { target: f.phase });
  assert.deepEqual(f.lit(), [f.phase, f.phasePatch], "the same fragment index on another phased path is independent");
  f.runtime.stop();
});

test("label-to-bar traversal neither clears the interval nor rescans the card", () => {
  const f = fixture(); f.host.emit("pointerover", { target: f.label });
  const queries = f.card.queries;
  f.host.emit("pointerout", { target: f.label, relatedTarget: f.resultA });
  f.host.emit("pointerover", { target: f.resultA });
  assert.deepEqual(f.lit(), [f.patchA, f.refPatch, f.resultA]); assert.equal(f.card.queries, queries);
  f.host.emit("pointerout", { target: f.resultA, relatedTarget: f.header }); assert.deepEqual(f.lit(), []);
  f.runtime.stop();
});

test("headers, card blanks, gaps and whole source contigs do not trigger a card-wide highlight", () => {
  const f = fixture();
  for (const target of [f.header, f.card, f.gap, f.source, f.patchA]) {
    f.host.emit("pointerover", { target: f.resultA });
    f.host.emit("pointerover", { target }); assert.deepEqual(f.lit(), []);
  }
  f.runtime.stop();
});

test("keyboard focus highlights only its fragment and escapes or blurs cleanly", () => {
  const f = fixture(); f.host.emit("focusin", { target: f.resultA });
  assert.deepEqual(f.lit(), [f.patchA, f.refPatch, f.resultA]);
  f.host.emit("pointerover", { target: f.resultA }); f.host.emit("pointerleave");
  f.doc.emit("scroll"); assert.deepEqual(f.lit(), [f.patchA, f.refPatch, f.resultA], "hover and scrolling do not cancel keyboard focus");
  f.doc.emit("keydown", { key: "Escape" }); assert.deepEqual(f.lit(), []);
  f.host.emit("focusin", { target: f.resultB });
  f.host.emit("focusout", { target: f.resultB, relatedTarget: f.header }); assert.deepEqual(f.lit(), []);
  f.runtime.stop();
});

test("pointer departure, scrolling, resize, cancellation, clicks and window blur remove transient paint", () => {
  const f = fixture();
  for (const [node, type] of [[f.host, "pointerleave"], [f.host, "pointercancel"], [f.host, "pointerdown"],
    [f.doc, "scroll"], [f.win, "resize"], [f.win, "blur"]]) {
    f.host.emit("pointerover", { target: f.resultA }); assert.equal(f.lit().length, 3);
    node.emit(type); assert.deepEqual(f.lit(), [], type);
  }
  f.host.emit("pointerover", { target: f.resultA, pointerType: "touch" }); assert.deepEqual(f.lit(), []);
  f.runtime.stop();
});

test("virtualization and rerenders clear retained nodes without affecting another card's highlight", () => {
  const f = fixture(); f.host.emit("pointerover", { target: f.resultA });
  f.runtime.clear(f.otherCard); assert.equal(f.lit().length, 3);
  f.runtime.clear(f.card); assert.deepEqual(f.lit(), []);
  f.host.emit("pointerover", { target: f.otherResult }); assert.deepEqual(f.lit(), [f.otherResult, f.otherPatch]);
  f.runtime.clear(); assert.deepEqual(f.lit(), []); f.runtime.stop();
});

test("route/project invalidation blocks highlighting; repeated bind/unbind owns exactly one listener set", () => {
  const f = fixture(); f.runtime.start();
  assert.equal(f.host.listeners.get("pointerover").size, 1);
  f.host.emit("pointerover", { target: f.resultA }); f.disable();
  f.host.emit("pointerover", { target: f.resultA }); assert.deepEqual(f.lit(), []);
  f.runtime.stop(); f.runtime.stop();
  for (const node of [f.host, f.doc, f.win]) for (const listeners of node.listeners.values()) assert.equal(listeners.size, 0);
  f.runtime.start(); assert.equal(f.host.listeners.get("pointerover").size, 1); f.runtime.stop();
});

test("card markup pairs reused and reversed fragments by path/index, not source names, without changing scientific data", () => {
  const segment = { type: "ctg", assemblyCtgId: 1, datasetName: "dsA", ctgName: "raw_ctg", overallLen: 1000 };
  const [card] = buildProjectPreviewModel({ chromosomes: [{ chrName: 'Chr"1', chrLength: 2000 }], referenceGenomeId: 1,
    datasets: [{ datasetId: 1, name: "dsA" }], project: { primaryDatasetId: 1 },
    ctgs: [{ assemblyCtgId: 1, datasetId: 1, datasetName: "dsA", name: "raw_ctg", totalLength: 1000,
      assignedChrName: 'Chr"1', anchorStart: 0 }],
    finalPathByChr: { 'Chr"1': { segments: [{ ...segment, start: 1, end: 100 }, { type: "gap", gapSizeBp: 1 },
      { ...segment, start: 601, end: 650, orient: "-" }] } } });
  const before = JSON.stringify(card), labels = getMessages("en", "projectPreview");
  const html = renderProjectPreviewCard(card, labels, true, { interactive: true });
  const keys = [...html.matchAll(/data-preview-part-key="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(keys, ['[&quot;Chr\\&quot;1&quot;,0]', '[&quot;Chr\\&quot;1&quot;,2]',
    '[&quot;Chr\\&quot;1&quot;,0]', '[&quot;Chr\\&quot;1&quot;,2]']);
  assert.equal((html.match(/tabindex="0" role="img"/g) || []).length, 2);
  const gap = html.match(/<span class="project-preview-final-part is-gap"[^>]*>/)[0];
  assert.doesNotMatch(gap, /data-preview-part-key|tabindex/);
  const standalone = renderProjectPreviewCard(card, labels);
  assert.doesNotMatch(standalone, /tabindex="0" role="img"/);
  assert.doesNotMatch(html, /data-preview-highlighted/);
  assert.equal(JSON.stringify(card), before);
});


test("reference adoption emits the same exact fragment key on the reference interval and result bar", () => {
  const [card] = buildProjectPreviewModel({ chromosomes: [{ chrName: "Chr1", chrLength: 2000 }], referenceGenomeId: 1,
    datasets: [], project: {}, ctgs: [], finalPathByChr: { Chr1: { segments: [
      { type: "gap", gapSizeBp: 10 }, { type: "ctg", sourceKind: "ref_segment", referenceChrName: "Chr1",
        start: 501, end: 600, memberStartBp: 1, memberEndBp: 2000, overallLen: 2000 },
    ] } } });
  const output = renderProjectPreviewCard(card, getMessages("en", "projectPreview"), true, { interactive: true });
  const keys = [...output.matchAll(/data-preview-part-key="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(keys, ['[&quot;Chr1&quot;,1]', '[&quot;Chr1&quot;,1]']);
  assert.equal((output.match(/tabindex="0" role="img"/g) || []).length, 1);
  assert.match(output, /data-preview-reference-highlight-start=/);
});
