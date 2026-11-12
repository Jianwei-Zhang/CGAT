import { readFileSync } from "node:fs";
import { previewMutationStamp } from "../../../services/preview-content-events.js";
import { PREVIEW_MODEL_VERSION, previewOverrideSignature } from "../project-preview-cache.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../state/store.js";
import { getMessages } from "../../i18n/index.js";
import { buildProjectPreviewModel, previewProjectKey, requestPreviewChromosome } from "../project-preview-state.js";
import { projectPreviewDisplayCards, layoutProjectPreviewCard } from "../project-preview-layout.js";
import { projectPreviewSession, toggleProjectPreviewChromosome } from "../project-preview-session.js";
import { renderProjectPreviewCount, loadProjectPreviewData, renderProjectPreviewCard, renderProjectPreviewPage, bindProjectPreviewPage, unbindProjectPreviewPage, restoreProjectPreviewScroll } from "../project-preview-page.js";
import { buildProjectPreviewSvgSnapshot } from "../project-preview-image-export.js";
import { readProjectPreviewImageStyle } from "../project-preview-presentation.js";

const labels = getMessages("en", "projectPreview");
const segment = (length, extra = {}) => ({ type: "ctg", assemblyCtgId: 1, datasetName: "main", ctgName: "a", start: 1, end: length, overallLen: length, ...extra });
function fixture() {
  return buildProjectPreviewModel({
    referenceGenomeId: 1,
    chromosomes: [{ chrName: "chr1", chrLength: 500 }, { chrName: "chr2", chrLength: 2000 }, { chrName: "chr3", chrLength: 300 }],
    project: { primaryDatasetId: 1 }, datasets: [{ datasetId: 1, name: "main" }],
    ctgs: [{ assemblyCtgId: 1, datasetId: 1, datasetName: "main", name: "a", totalLength: 1000, assignedChrName: "chr1", anchorStart: 0 },
      { assemblyCtgId: 2, datasetId: 1, datasetName: "main", name: "context", totalLength: 6000, assignedChrName: "chr3", anchorStart: -1000 }],
    phasedChrTracksByChr: { chr1: [{ label: "chr1A", haplotypeKey: "A" }, { label: "chr1B", haplotypeKey: "B" }] },
    finalPathByChr: {
      chr1A: { segments: [segment(100), { type: "gap", gapSizeBp: 1 }, segment(1, { orient: "-" })] },
      chr1B: { segments: [segment(500)] }, chr2: { segments: [segment(3000)] },
    },
  });
}

test("one project-wide domain includes folded/offscreen paths, Reference and source overhangs without mutating cached cards", () => {
  const cards = fixture(), original = structuredClone(cards), display = projectPreviewDisplayCards(cards);
  const expected = { start: Math.min(0, ...cards.map(card => card.domain.start)), end: Math.max(1, ...cards.map(card => card.domain.end)) };
  assert.ok(expected.start < 0); assert.ok(expected.end > 3000, "the longest context source, not just Final Path, sets the scale");
  for (const card of display) assert.deepEqual(card.domain, expected);
  assert.equal(projectPreviewDisplayCards(cards), display, "reuse immutable display wrappers for DOM/model reconciliation");
  assert.deepEqual(cards, original);
  const updated = cards.map(card => card.chrName === "chr3" ? { ...card, domain: { start: 0, end: 10 } } : card);
  assert.ok(projectPreviewDisplayCards(updated)[0].domain.end < expected.end, "new content can shrink the scale; no stale domain accumulation");
});

test("folding only hides detail rows: each phased Final Path appears once and remains above shared source tracks", () => {
  const [card] = projectPreviewDisplayCards(fixture());
  const closed = renderProjectPreviewCard(card, labels, true, false), open = renderProjectPreviewCard(card, labels, true, true);
  const pathBlock = html => html.slice(html.indexOf("<div class=\"project-preview-paths\">"), html.indexOf("<div class=\"project-preview-details\""));
  assert.equal(pathBlock(open), pathBlock(closed), "opening must neither replace nor resize the authoritative Final Path strips");
  for (const name of ["chr1A", "chr1B"]) assert.equal((open.match(new RegExp(`data-final-path-name="${name}"`, "g")) || []).length, 1);
  assert.ok(open.indexOf("data-final-path-name=\"chr1B\"") < open.indexOf("project-preview-axis"));
  assert.equal((open.match(/project-preview-source-plots/g) || []).length, card.tracks.length);
  assert.match(closed, /class="project-preview-details"[^>]* hidden/); assert.doesNotMatch(open, /class="project-preview-details"[^>]* hidden/);
  assert.match(closed, /aria-expanded="false"/); assert.match(open, /aria-expanded="true"/);
});

test("common geometry stays bounded and adopted intervals follow short/reversed phased parts at every width", () => {
  const [card] = projectPreviewDisplayCards(fixture());
  for (const width of [320, 900, 1800]) {
    const geometry = layoutProjectPreviewCard(card, width);
    for (const parts of geometry.paths.values()) for (const part of parts) {
      assert.ok(part.x >= 0); assert.ok(part.width > 0); assert.ok(part.x + part.width <= width + 1e-7);
    }
    for (const body of geometry.tracks.flat()) for (const patch of body.highlights) {
      const part = patch.patch.part, target = geometry.paths.get(part.pathName)[part.index];
      assert.ok(Math.abs(patch.x - target.x) < 1e-7); assert.ok(Math.abs(patch.width - target.width) < 1e-7);
    }
    assert.ok(geometry.paths.get("chr1A")[1].width >= 8);
    assert.ok(geometry.paths.get("chr1A")[2].width >= 8);
  }
});

test("chromosomes without a Final Path remain in the preview with an explicit empty row", () => {
  const card = projectPreviewDisplayCards(fixture())[2], html = renderProjectPreviewCard(card, labels, true, false);
  assert.match(html, /data-preview-chr="chr3"/); assert.match(html, /Final Path/); assert.ok(html.includes(labels.noPath));
  assert.match(html, /data-preview-open/); assert.match(html, /class="project-preview-details"[^>]* hidden/);
});

test("expansion is independent per chromosome and isolated per project/workspace in the current session", () => {
  const key = "integration-session-one", other = "integration-session-two";
  assert.equal(projectPreviewSession(key).expanded.size, 0);
  toggleProjectPreviewChromosome(key, "chr1"); toggleProjectPreviewChromosome(key, "chr2");
  assert.deepEqual([...projectPreviewSession(key).expanded], ["chr1", "chr2"]);
  toggleProjectPreviewChromosome(key, "chr1");
  assert.deepEqual([...projectPreviewSession(key).expanded], ["chr2"]);
  assert.equal(projectPreviewSession(other).expanded.size, 0);
});

test("phased-strip navigation requests the parent and correct path without destroying live Assembly data", () => {
  const cards = fixture(), store = createStore({ session: { workspacePath: "/integration", projectId: 80 },
    assembly: { selectedChrName: "old", chrCtgs: [{ marker: "live" }], finalPathByChr: { draft: {} }, localView: { marker: "keep" } } });
  store.setState({ projectPreview: { key: previewProjectKey(store.getState()), chromosomes: cards.map(card => ({ chrName: card.chrName })) } });
  const before = store.getState().assembly;
  assert.equal(requestPreviewChromosome(store, "chr1", cards[0].paths[1]), true);
  const next = store.getState().assembly;
  assert.equal(next.previewRequestedChrName, "chr1"); assert.equal(next.activePhasedTrackKey, "B");
  assert.equal(next.activeFinalPathKey, "B"); assert.equal(next.activeFinalPathKeyByChr.chr1, "B");
  for (const key of ["chrCtgs", "localView", "finalPathByChr"]) assert.equal(next[key], before[key]);
  assert.equal(next.selectedChrName, "old");
});

test("export contains complete expanded groups in screen order with shared geometry and persistent inner outlines only", () => {
  const cards = fixture(), state = { locale: "en", session: { workspacePath: "/export-integration", projectId: 1 }, projectPreview: { loaded: true, cards } };
  state.projectPreview.key = previewProjectKey(state);
  Object.assign(state.projectPreview, { modelVersion: PREVIEW_MODEL_VERSION, savedPathSignatures: {},
    localSignature: previewOverrideSignature({}, {}), mutationStamp: previewMutationStamp({ workspaceRoot: state.session.workspacePath, projectId: state.session.projectId }) });
  const style = readProjectPreviewImageStyle(), snapshot = buildProjectPreviewSvgSnapshot(state, { style });
  assert.equal(snapshot.cardBounds.length, 3, "include folded and offscreen cards");
  const first = snapshot.cardBounds[0].svgMarkup;
  const axisIndex = first.indexOf(`>${labels.compositionAxis.slice(0, 6)}`);
  assert.ok(axisIndex > 0);
  assert.ok(first.indexOf(">Final Path<") < axisIndex);
  assert.ok(first.indexOf(">chr1B<") < axisIndex);
  assert.ok(axisIndex < first.indexOf(">Ref<"));
  assert.ok(snapshot.cardBounds[2].svgMarkup.includes(labels.noPath));
  assert.match(first, /data-preview-adopted-outline="1"/); assert.doesNotMatch(first, /stroke-width="3"/);
  const inset = 20 + style.padding + 1, left = inset + style.labelWidth + style.columnGap;
  const plotWidth = snapshot.width - inset - left, display = projectPreviewDisplayCards(cards);
  const geometry = layoutProjectPreviewCard(display[0], plotWidth);
  const x = left + geometry.paths.get("chr1A")[0].x;
  assert.ok(first.includes(`<rect x="${x}"`), "export must use the same project-wide display mapping");
});

test("Project page starts folded, keeps multiple expanded groups and never renders the old compact list", () => {
  const cards = fixture(), state = { locale: "en", session: { workspacePath: "/folded-integration", projectId: 1 }, projectPreview: { loaded: true, cards } };
  const key = previewProjectKey(state); state.projectPreview.key = key;
  const folded = renderProjectPreviewPage(state, { embedded: true, hideHeading: true });
  assert.equal((folded.match(/data-preview-expanded="false"/g) || []).length, 3);
  toggleProjectPreviewChromosome(key, "chr1"); toggleProjectPreviewChromosome(key, "chr2");
  const expanded = renderProjectPreviewPage(state, { embedded: true, hideHeading: true });
  assert.equal((expanded.match(/data-preview-expanded="true"/g) || []).length, 2);
  assert.doesNotMatch(expanded, /project-export-final-path-list|project-preview-heading|id="overview-preview-title"/);
});

// Native DOM is not needed to verify scroll ownership and lifecycle cleanup.
test("scroll restoration waits for summary and preview, persists per project and detaches on departure", () => {
  const cards = fixture(), store = createStore({ activeRoute: "importer", locale: "en", session: { workspacePath: "/scroll-integration", projectId: 42 }, projectExport: { loading: true } });
  const key = previewProjectKey(store.getState()), session = projectPreviewSession(key);
  session.scrollTop = 420; session.scrollLeft = 12;
  const listeners = new Set(), owner = { scrollTop: 0, scrollLeft: 0, addEventListener(_event, fn) { listeners.add(fn); }, removeEventListener(_event, fn) { listeners.delete(fn); } };
  const host = { parentElement: owner, isConnected: true, ownerDocument: { defaultView: { getComputedStyle: () => ({ overflowY: "auto" }) } },
    addEventListener() {}, querySelectorAll: () => [], querySelector: selector => selector === ".project-preview-cards" ? {} : null };
  bindProjectPreviewPage(host, store, { getProjectPreviewCache: async () => ({ available: false }),
    listProjectChromosomes: async () => ({ items: [] }), listChrViewCtgs: async () => ({ items: [] }),
    getProjectAssemblyViewState: async () => ({}), getGrtProjectView: async () => ({}) });
  restoreProjectPreviewScroll(host); assert.equal(owner.scrollTop, 0);
  store.setState({ projectExport: { loading: false }, projectPreview: { key, loaded: true, cards } });
  restoreProjectPreviewScroll(host); assert.equal(owner.scrollTop, 420); assert.equal(owner.scrollLeft, 12);
  owner.scrollTop = 625; for (const fn of listeners) fn(); assert.equal(session.scrollTop, 625);
  unbindProjectPreviewPage(host); assert.equal(listeners.size, 0);
});

test("narrow-screen exports preserve the measured plot width instead of enlarging it to 1000px", () => {
  const state = { locale: "en", session: { workspacePath: "/narrow-export", projectId: 1 }, assembly: { finalPathByChr: {} } };
  state.projectPreview = { key: previewProjectKey(state), loaded: true, cards: fixture(), modelVersion: PREVIEW_MODEL_VERSION,
    savedPathSignatures: {}, localSignature: previewOverrideSignature({}, {}),
    mutationStamp: previewMutationStamp({ workspaceRoot: state.session.workspacePath, projectId: 1 }) };
  const style = readProjectPreviewImageStyle(), screenCardWidth = 560;
  const snapshot = buildProjectPreviewSvgSnapshot(state, { width: screenCardWidth + 40, style });
  const screenPlotWidth = screenCardWidth - 2 * (style.padding + 1) - style.labelWidth - style.columnGap;
  const exportPlotWidth = snapshot.width - 2 * (20 + style.padding + 1) - style.labelWidth - style.columnGap;
  assert.equal(screenPlotWidth, exportPlotWidth);
  const [card] = projectPreviewDisplayCards(state.projectPreview.cards);
  assert.deepEqual(layoutProjectPreviewCard(card, screenPlotWidth), layoutProjectPreviewCard(card, exportPlotWidth));
});

test("content updates preserve unaffected display-card identities when the complete domain is unchanged", () => {
  const cards = fixture(), before = projectPreviewDisplayCards(cards);
  const next = [cards[0], { ...cards[1], unresolvedCount: 1 }, cards[2]];
  const after = projectPreviewDisplayCards(next);
  assert.equal(after[0], before[0]); assert.equal(after[2], before[2]); assert.notEqual(after[1], before[1]);
});

test("clicking the folded strip expands it; a second click opens Assembly while the toggle can fold independently", async () => {
  const cards = fixture(), store = createStore({ activeRoute: "importer", locale: "en", session: { workspacePath: "/click-integration", projectId: 90 }, assembly: { finalPathByChr: {} } });
  const key = previewProjectKey(store.getState());
  store.setState({ projectPreview: { key, loaded: true, cards, chromosomes: cards.map(card => ({ chrName: card.chrName })),
    modelVersion: PREVIEW_MODEL_VERSION, savedPathSignatures: {}, localSignature: previewOverrideSignature({}, {}),
    mutationStamp: previewMutationStamp({ workspaceRoot: "/click-integration", projectId: 90 }) } });
  const toggle = { setAttribute(name, value) { this[name] = value; } }, chevron = {}, details = { hidden: true };
  const card = { dataset: { previewChr: "chr1", previewExpanded: "false", previewMounted: "false" }, querySelectorAll: () => [],
    querySelector: selector => selector === "[data-preview-toggle]" ? toggle : selector === ".project-preview-chevron" ? chevron : selector === ".project-preview-details" ? details : null };
  const events = {}, host = { isConnected: true, contains: () => true, addEventListener: (name, fn) => { events[name] = fn; },
    querySelector: () => null, querySelectorAll: selector => selector === "[data-preview-chr]" ? [card] : [] };
  // Hold the metadata request so the already-validated DOM fixture remains in
  // place while click delegation is tested, then release it after unbinding.
  let complete;
  const metadata = new Promise(resolve => { complete = resolve; });
  bindProjectPreviewPage(host, store, { getProjectPreviewCache: () => metadata });
  const stripTarget = { closest: selector => selector === "[data-preview-chr]" ? card
    : selector === ".project-preview-paths" || selector === ".project-preview-paths, .project-preview-details" || selector === "[data-preview-toggle], .project-preview-paths" ? {}
      : selector === "[data-final-path-name]" ? { dataset: { finalPathName: "chr1B" } } : null };
  events.click({ target: stripTarget });
  assert.equal(card.dataset.previewExpanded, "true"); assert.equal(details.hidden, false); assert.equal(toggle["aria-expanded"], "true");
  assert.equal(store.getState().activeRoute, "importer");
  const toggleTarget = { closest: selector => selector === "[data-preview-chr]" ? card : selector === "[data-preview-toggle], .project-preview-paths" ? {} : null };
  events.click({ target: toggleTarget });
  assert.equal(details.hidden, true); assert.equal(store.getState().activeRoute, "importer");
  events.click({ target: stripTarget }); events.click({ target: stripTarget });
  assert.equal(store.getState().activeRoute, "assembly"); assert.equal(store.getState().assembly.previewRequestedChrName, "chr1");
  assert.equal(store.getState().assembly.activePhasedTrackKey, "B"); assert.equal(store.getState().assembly.activeFinalPathKey, "B");
  unbindProjectPreviewPage(host); complete({ available: false }); await Promise.resolve();
});

test("cold Preview loading retains phased navigation keys through compact inputs and model construction", async () => {
  const store = createStore({ activeRoute: "importer", locale: "en", session: { workspacePath: "/phased-load-integration", projectId: 19 },
    assembly: { finalPathByChr: {} }, initializer: { existingProjects: [{ projectId: 19, primaryDatasetId: 1, phasedAssemblyEnabled: true }], datasets: [{ datasetId: 1, name: "main" }] } });
  assert.equal(await loadProjectPreviewData(null, store, {
    getProjectPreviewCache: async () => ({ available: false }), putProjectPreviewCache: async () => ({ stored: false }),
    listProjectChromosomes: async () => ({ items: [{ chrName: "chr1", chrLength: 1000 }], referenceGenomeId: 1 }),
    listChrViewCtgs: async () => ({ items: [] }), getGrtProjectView: async () => ({}),
    listPhasedChrTracks: async () => ({ tracks: [{ label: "chr1B", haplotypeKey: "B" }] }),
    getProjectAssemblyViewState: async () => ({ finalPathByChr: { chr1B: { mode: "segments", chrName: "chr1B", segments: [segment(100)] } } }),
  }, { background: true }), true);
  const path = store.getState().projectPreview.cards[0].paths[0];
  assert.equal(path.name, "chr1B"); assert.equal(path.phasedTrackKey, "B");
  assert.equal(requestPreviewChromosome(store, "chr1", path), true);
  assert.equal(store.getState().assembly.activeFinalPathKey, "B");
});

test("document-scrolling Project restores its own session and waits until the summary layout is ready", () => {
  const store = createStore({ activeRoute: "importer", locale: "en", session: { workspacePath: "/document-scroll-integration", projectId: 62 } });
  const key = previewProjectKey(store.getState()), session = projectPreviewSession(key);
  session.scrollTop = 800;
  const root = { scrollTop: 0, scrollLeft: 0 }, parent = {}, listeners = new Set();
  const doc = { scrollingElement: root, defaultView: { getComputedStyle: () => ({ overflowY: "visible" }) },
    addEventListener: (_name, fn) => listeners.add(fn), removeEventListener: (_name, fn) => listeners.delete(fn) };
  const host = { ownerDocument: doc, parentElement: parent, isConnected: true, addEventListener() {},
    querySelectorAll: () => [], querySelector: selector => selector === ".project-preview-cards" ? {} : null };
  let ready = false;
  bindProjectPreviewPage(host, store, { isScrollReady: () => ready, getProjectPreviewCache: () => new Promise(() => {}) });
  restoreProjectPreviewScroll(host); assert.equal(root.scrollTop, 0);
  ready = true; restoreProjectPreviewScroll(host); assert.equal(root.scrollTop, 800);
  root.scrollTop = 900; for (const fn of listeners) fn(); assert.equal(session.scrollTop, 900);
  unbindProjectPreviewPage(host); assert.equal(listeners.size, 0);
});

function readyState(locale = "en") {
  const state = { locale, session: { workspacePath: "/refined-preview", projectId: 91 }, assembly: { finalPathByChr: {} } };
  state.projectPreview = { key: previewProjectKey(state), loaded: true, cards: fixture(), modelVersion: PREVIEW_MODEL_VERSION,
    savedPathSignatures: {}, localSignature: previewOverrideSignature({}, {}),
    mutationStamp: previewMutationStamp({ workspaceRoot: state.session.workspacePath, projectId: 91 }) };
  return state;
}
test("Project preview heading counts chromosome groups, not phased paths, and suppresses stale/error counts", () => {
  for (const locale of ["en", "zh"]) {
    const state = readyState(locale);
    assert.match(renderProjectPreviewCount(state), /class="project-section-count"><span aria-hidden="true">·<\/span>3<\/span>/);
    assert.equal(renderProjectPreviewCount({ ...state, projectPreview: { ...state.projectPreview, key: "other-project" } }), "");
    assert.equal(renderProjectPreviewCount({ ...state, projectPreview: { ...state.projectPreview, loading: true } }), "");
    assert.match(renderProjectPreviewCount({ ...state, projectPreview: { ...state.projectPreview, cards: [] } }), />0<\/span>/);
    assert.equal(renderProjectPreviewCount({ ...state, projectPreview: { ...state.projectPreview, error: "failed" } }), "");
  }
});

test("folded styling uses one name-plus-strip row without changing the shared horizontal grid or duplicating paths", () => {
  const css = readFileSync(new URL("../../../styles/project-export.css", import.meta.url), "utf8");
  const root = '[data-overview-preview] .project-preview-card[data-preview-expanded="false"]';
  const rule = selector => [...css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([, selectors]) => selectors.trim() === selector).map(([, , body]) => body).join("\n");
  assert.match(rule(root), /grid-template-columns: 108px minmax\(0, 1fr\)/);
  assert.match(rule(root + ' .project-preview-card-heading'), /grid-column: 1; grid-row: 1/);
  assert.match(rule(root + ' .project-preview-paths'), /grid-column: 2; grid-row: 1/);
  assert.match(rule(root + ' .project-preview-row'), /grid-template-columns: minmax\(0, 1fr\)/);
  const [card] = projectPreviewDisplayCards(fixture());
  const html = renderProjectPreviewCard(card, labels, true, false);
  assert.match(html, /data-preview-path-count="2" style="--preview-path-count:2"/);
  assert.equal((html.match(/data-final-path-strip="1"/g) || []).length, 2);
  assert.equal((html.match(/class="project-preview-card-heading"/g) || []).length, 1);
});

test("preview count in the parent toolbar updates when the independent component loads", async () => {
  const store = createStore({ activeRoute: "importer", locale: "en", session: { workspacePath: "/count-load-refined", projectId: 81 },
    assembly: { finalPathByChr: {} }, initializer: { existingProjects: [{ projectId: 81 }], datasets: [] } });
  const count = { innerHTML: "" }, root = { querySelector: selector => selector === "[data-preview-count]" ? count : null };
  const host = { innerHTML: "", closest: () => root, querySelectorAll: () => [], querySelector: () => null };
  assert.equal(await loadProjectPreviewData(host, store, {
    getProjectPreviewCache: async () => ({ available: false }), putProjectPreviewCache: async () => ({ stored: false }),
    listProjectChromosomes: async () => ({ items: [{ chrName: "chr1" }, { chrName: "chr2" }] }),
    listChrViewCtgs: async () => ({ items: [] }), getGrtProjectView: async () => ({}), getProjectAssemblyViewState: async () => ({}),
  }), true);
  assert.match(count.innerHTML, />2<\/span>/);
});
