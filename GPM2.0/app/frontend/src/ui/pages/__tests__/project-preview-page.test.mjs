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
  assert.match(output, /title="Gap: 1 bp">Gap<\/span>/);
  assert.match(output, /a&lt;ctg&gt;/);
});

test("preview styles keep one chromosome per row and contain the legend", () => {
  const css = readFileSync(new URL("../../../styles/project-preview.css", import.meta.url), "utf8");
  assert.match(css, /\.project-preview-cards[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(css, /\.project-preview-heading[^}]*position:\s*relative/);
  assert.match(css, /\.project-preview-hint[^}]*left:\s*0;[^}]*max-width:\s*100%/);
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
  store.setState({ session: { workspacePath: "/other", projectId: 2 }, projectPreview: null });
  resolve({ items: [] });
  assert.equal(await pending, false);
  assert.equal(store.getState().projectPreview, null);
  store.setState(state());
  const first = loadProjectPreviewData(node, store, options);
  const resolveFirst = resolve;
  assert.equal(await loadProjectPreviewData(node, store, deps()), true);
  resolveFirst({ items: [] });
  assert.equal(await first, false);
  assert.equal(store.getState().projectPreview.cards.length, 1);
});

test("source colors remain dataset-specific and adopted interval outlines are card-scoped hover feedback", () => {
  const css = readFileSync(new URL("../../../styles/project-preview.css", import.meta.url), "utf8");
  assert.match(css, /\.project-preview-used[^}]*background:\s*transparent/);
  assert.match(css, /\.project-preview-card:hover\s+\.project-preview-source-plots\s+\.project-preview-used/);
  assert.match(css, /border-color:\s*var\(--source-color\)/);
  const value = state();
  const cards = buildProjectPreviewModel({ chromosomes: [{ chrName: "Chr1", chrLength: 2000 }], referenceGenomeId: 1,
    ctgs: [{ assemblyCtgId: 1, datasetName: "dsA", name: "a", totalLength: 1000, assignedChrName: "Chr1", anchorStart: 0 },
      { assemblyCtgId: 2, datasetName: "dsB", name: "b", totalLength: 1000, assignedChrName: "Chr1", anchorStart: 0 }],
    finalPathByChr: { Chr1: { segments: [segment] } } });
  value.projectPreview = { key: previewProjectKey(value), loaded: true, cards };
  const output = renderProjectPreviewPage(value);
  const fills = [...output.matchAll(/class="project-preview-contig[^>]*background:(#[0-9a-f]{6});border-color:#[0-9a-f]{6}/g)].map(match => match[1]);
  assert.equal(new Set(fills).size, cards[0].tracks.length);
  assert.match(css, /\.project-preview-contig\s*\{[^}]*height:\s*16px/);
  assert.doesNotMatch(css, /\.project-preview-contig\.is-context\s*\{[^}]*(height|transform|opacity):/);
  assert.match(css, /\.project-preview-final-part > span\s*\{[^}]*text-overflow:\s*clip/);
  assert.match(output, /data-final-path-fit-label/);
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
