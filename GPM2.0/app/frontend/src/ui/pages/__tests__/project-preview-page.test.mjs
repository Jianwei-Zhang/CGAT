import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createStore } from "../../../state/store.js";
import { buildProjectPreviewModel, previewProjectKey } from "../project-preview-state.js";
import { loadProjectPreviewData, renderProjectPreviewPage } from "../project-preview-page.js";

function state() {
  return { locale: "zh", activeRoute: "projectPreview", session: { workspacePath: "/ws", projectId: 1 },
    initializer: { datasets: [{ datasetId: 1, name: "dsA" }], existingProjects: [{ projectId: 1, primaryDatasetId: 1 }] },
    assembly: { selectedChrName: "Chr2", finalPathByChr: {} } };
}
const segment = { type: "ctg", assemblyCtgId: 1, datasetName: "dsA", ctgName: "a<ctg>", overallLen: 1000, start: 1, end: 1000 };
function host() {
  return { innerHTML: "", querySelectorAll: () => [], contains: () => true,
    addEventListener(name, handler) { this[name] = handler; } };
}
function deps() {
  return {
    async listProjectChromosomes() { return { referenceGenomeId: 1, items: [{ chrName: "Chr1", chrLength: 2000 }] }; },
    async listChrViewCtgs() { return { items: [{ assemblyCtgId: 1, datasetName: "dsA", name: "a<ctg>", totalLength: 1000,
      assignedChrName: "Chr1", anchorStart: 0 }] }; },
    async getProjectAssemblyViewState() { return { finalPathByChr: { Chr1: { mode: "segments", segments: [segment] } } }; },
    async getGrtProjectView() { return {}; },
  };
}

test("preview uses single-line heading, icon refresh, hides unpositioned information, and labels gaps", () => {
  const value = state();
  const cards = buildProjectPreviewModel({ chromosomes: [{ chrName: "Chr1", chrLength: 2000 }], referenceGenomeId: 1,
    ctgs: [{ assemblyCtgId: 2, datasetName: "dsA", name: "unknown", totalLength: 100,
      assignedChrName: "Chr1", anchorStart: null }],
    finalPathByChr: { Chr1: { segments: [segment, { type: "gap", gapSizeBp: 1 }] } } });
  value.projectPreview = { key: previewProjectKey(value), loaded: true, cards };
  const output = renderProjectPreviewPage(value);
  assert.match(output, /class="project-preview-card"/);
  assert.doesNotMatch(output, /<button[^>]*class="project-preview-card"/);
  assert.match(output, /project-preview-refresh[^>]*aria-label="刷新"[^>]*>[\s\S]*?<svg/);
  assert.doesNotMatch(output, /project-preview-refresh[^>]*>刷新/);
  assert.doesNotMatch(output, /project-preview-unpositioned|data-preview-unpositioned|未定位/);
  assert.match(output, /data-final-path-gap-label="1"/);
  assert.match(output, /data-final-path-kind="gap"[^>]*background:var\(--gap-marker-fill, #ffffff\)/);
  assert.match(output, /title="Gap: 1 bp">Gap<\/span>/);
  assert.match(output, /data-final-path-kind="gap"[^>]*data-final-path-length="1"/);
  assert.match(output, /data-final-path-kind="gap"[^>]*color:var\(--gap-marker-text, #1b1b1b\)/);
  assert.match(output, /a&lt;ctg&gt;/);
});

test("preview styles keep one chromosome per row and contain the legend", () => {
  const css = readFileSync(new URL("../../../styles/project-preview.css", import.meta.url), "utf8");
  assert.match(css, /\.project-preview-cards[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(css, /\.project-preview-heading[^}]*position:\s*relative/);
  assert.match(css, /\.project-preview-hint[^}]*left:\s*0;[^}]*max-width:\s*100%/);
});

test("hover and keyboard focus promote the whole preview card, not just its header", () => {
  const css = readFileSync(new URL("../../../styles/project-preview.css", import.meta.url), "utf8");
  const base = readFileSync(new URL("../../../styles/base.css", import.meta.url), "utf8");
  const theme = readFileSync(new URL("../../../styles/theme.css", import.meta.url), "utf8");

  const stateRule = css.match(/\.project-preview-card:hover,\s*\n\.project-preview-card:focus-within\s*\{([^}]*)\}/)?.[1];
  assert.ok(stateRule, "hover and focus-within must share one rule");
  assert.match(stateRule, /border-color:\s*var\(--preview-card-ring/);
  // The ring is inset and the glow stays narrower than the 16px card gap, so
  // the card never looks inflated and never covers a neighbour's border.
  assert.match(stateRule, /box-shadow:\s*inset 0 0 0 1px var\(--preview-card-ring[^;]*\),\s*0 2px 8px var\(--preview-card-glow/);
  assert.doesNotMatch(stateRule, /var\(--shadow-md\)|var\(--shadow-lg\)/);
  assert.doesNotMatch(stateRule, /box-shadow:\s*0 0 0 1px/);
  // The title row must carry the same inset ring as the card, otherwise the
  // header's opaque background hides it and the title frame reads thinner than
  // the lower frame. Frame, title divider and lower edges share one 2px weight.
  const headerStateRule = css.match(/\.project-preview-card:hover \.project-preview-card-header,\s*\n\.project-preview-card:focus-within \.project-preview-card-header\s*\{([^}]*)\}/)?.[1];
  assert.ok(headerStateRule, "header hover and focus-within must share one rule");
  assert.match(headerStateRule, /border-bottom-color:\s*var\(--preview-card-ring/);
  assert.match(headerStateRule, /box-shadow:\s*inset 0 0 0 1px var\(--preview-card-ring[^;]*\);/);
  const headerBaseRule = css.match(/^\.project-preview-card-header\s*\{([^}]*)\}/m)?.[1];
  assert.ok(headerBaseRule);
  assert.match(headerBaseRule, /border-bottom:\s*1px solid var\(--border-subtle/);
  assert.match(headerBaseRule, /width:\s*calc\(100% \+ 32px\)/, "header spans the card's full width");
  // Hover must not add a thicker divider of its own.
  assert.doesNotMatch(headerStateRule, /border-bottom-width|border-bottom:\s*2px/);
  // Focus keeps an outline for forced-colors mode, drawn inside the header strip.
  assert.match(css, /\.project-preview-card-header:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--preview-card-ring[^}]*outline-offset:\s*-3px;/);
  // Ring and glow are themed and stay visible on both surfaces.
  assert.match(base, /--preview-card-ring:\s*#3f6fa3;/);
  assert.match(base, /--preview-card-glow:\s*rgba\(63, 111, 163, 0\.18\);/);
  assert.match(theme, /--preview-card-ring:\s*#8ab6e6;/);
  // Per-source outlines stay scoped to their own interval inside the card.
  assert.match(css, /\.project-preview-card:hover \.project-preview-source-plots \.project-preview-used/);
});

test("loading preview preserves assembly state and in-memory path edits", async () => {
  const value = state();
  value.assembly.finalPathByChr = { Chr1: { mode: "segments", segments: [{ ...segment, end: 500 }] } };
  const store = createStore(value), before = structuredClone(store.getState().assembly);
  assert.equal(await loadProjectPreviewData(host(), store, deps()), true);
  assert.deepEqual(store.getState().assembly, before);
  assert.equal(store.getState().projectPreview.cards[0].paths[0].length, 500);
});

test("late preview requests cannot overwrite a different project or a newer request", async () => {
  let resolve;
  const options = deps();
  options.listProjectChromosomes = () => new Promise(done => { resolve = done; });
  const store = createStore(state()), node = host();
  const pending = loadProjectPreviewData(node, store, options);
  await new Promise(done => setImmediate(done));
  store.setState({ session: { workspacePath: "/other", projectId: 2 }, projectPreview: null });
  resolve({ items: [] });
  assert.equal(await pending, false);
  assert.equal(store.getState().projectPreview, null);
  store.setState(state());
  const first = loadProjectPreviewData(node, store, options);
  await new Promise(done => setImmediate(done));
  const resolveFirst = resolve;
  assert.equal(await loadProjectPreviewData(node, store, deps(), { force: true }), true);
  resolveFirst({ items: [] });
  assert.equal(await first, false);
  assert.equal(store.getState().projectPreview.cards.length, 1);
});

test("source colors follow Assembly roles and adopted interval outlines are card-scoped hover feedback", () => {
  const css = readFileSync(new URL("../../../styles/project-preview.css", import.meta.url), "utf8");
  assert.match(css, /\.project-preview-used[^}]*background:\s*transparent/);
  assert.match(css, /\.project-preview-card:hover\s+\.project-preview-source-plots\s+\.project-preview-used/);
  assert.match(css, /border-color:\s*var\(--source-color\)/);
  const value = state();
  const cards = buildProjectPreviewModel({ chromosomes: [{ chrName: "Chr1", chrLength: 2000 }], referenceGenomeId: 1,
    datasets: [{ datasetId: 1, name: "dsA" }, { datasetId: 2, name: "dsB" }],
    project: { primaryDatasetId: 1, supportDatasetIds: [2] },
    ctgs: [{ assemblyCtgId: 1, datasetId: 1, datasetName: "dsA", name: "a", totalLength: 1000, assignedChrName: "Chr1", anchorStart: 0 },
      { assemblyCtgId: 2, datasetId: 2, datasetName: "dsB", name: "b", totalLength: 1000, assignedChrName: "Chr1", anchorStart: 0 }],
    finalPathByChr: { Chr1: { segments: [segment] } } });
  value.projectPreview = { key: previewProjectKey(value), loaded: true, cards };
  const output = renderProjectPreviewPage(value);
  assert.match(output, /background:var\(--ctg-primary-fill, #d2dfef\)/);
  assert.match(output, /background:var\(--ctg-companion-fill, #e7dec4\)/);
  assert.match(output, /border-color:var\(--ctg-companion-stroke, #8a7551\)/);
  assert.match(css, /\.project-preview-contig\s*\{[^}]*height:\s*16px/);
  assert.doesNotMatch(css, /\.project-preview-contig\.is-context\s*\{[^}]*(height|transform|opacity):/);
  assert.match(css, /\.project-preview-final-part > span\s*\{[^}]*text-overflow:\s*clip/);
  assert.match(output, /data-final-path-fit-label/);
  assert.match(output, /data-preview-source-fit-label="1"/);
  assert.match(css, /\.project-preview-contig-label\s*\{[^}]*text-overflow:\s*clip/);
  assert.match(output, /--source-color:/);
});

test("preview and project-export heading typography matches the Assembly chromosome heading", () => {
  const preview = readFileSync(new URL("../../../styles/project-preview.css", import.meta.url), "utf8");
  const exported = readFileSync(new URL("../../../styles/project-export.css", import.meta.url), "utf8");
  const assembly = readFileSync(new URL("../../../styles/assembly.css", import.meta.url), "utf8");
  for (const rule of [preview.match(/\.project-preview-heading h2\s*\{([^}]*)\}/)?.[1],
    exported.match(/\.project-export-head h3\s*\{([^}]*)\}/)?.[1],
    assembly.match(/\.chr-title\s*\{([^}]*)\}/)?.[1]]) {
    assert.ok(rule);
    assert.match(rule, /font-size:\s*var\(--font-heading\)/);
    assert.match(rule, /font-weight:\s*700/);
  }
});


test("rendered reference carries its adopted-path anchor rather than a fixed zero origin", () => {
  const value = state();
  const cards = buildProjectPreviewModel({ chromosomes: [{ chrName: "Chr1", chrLength: 2000 }], referenceGenomeId: 1,
    datasets: [{ datasetId: 1, name: "dsA" }, { datasetId: 2, name: "dsB" }],
    project: { primaryDatasetId: 1, supportDatasetIds: [2] },
    ctgs: [{ assemblyCtgId: 1, datasetId: 1, datasetName: "dsA", name: "a", totalLength: 1000,
      assignedChrName: "Chr1", anchorStart: -500 }],
    finalPathByChr: { Chr1: { segments: [segment] } } });
  value.projectPreview = { key: previewProjectKey(value), loaded: true, cards };
  const output = renderProjectPreviewPage(value);
  assert.match(output, /class="project-preview-reference"[^>]*data-preview-reference-path="Chr1"[^>]*data-preview-reference-index="0"[^>]*data-preview-reference-offset="500"[^>]*style="left:20\.00000%;width:80\.00000%/);
  assert.match(output, /data-final-path-domain="2500"/);
});
