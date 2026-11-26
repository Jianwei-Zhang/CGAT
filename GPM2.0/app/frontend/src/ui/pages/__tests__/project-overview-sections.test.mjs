import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  cardHasGaps,
  filterPreviewCards,
  getPreviewFilterState,
  isOverviewSectionExpanded,
  overviewSectionProjectKey,
  resetOverviewSectionsSession,
  setPreviewFilterState,
  toggleOverviewSection,
} from "../project-overview-sections.js";
import { projectCatalogKey, renderProjectCatalog } from "../project-catalog-view.js";
import { renderProjectRefinementCard } from "../project-refinement-view.js";
import { buildProjectPreviewModel, previewProjectKey } from "../project-preview-state.js";
import { PREVIEW_MODEL_VERSION, previewOverrideSignature } from "../project-preview-cache.js";
import { previewMutationStamp } from "../../../services/preview-content-events.js";
import { renderProjectPreviewControls, renderProjectPreviewPage } from "../project-preview-page.js";
import { projectPreviewSession, setProjectPreviewExpandedAll } from "../project-preview-session.js";

function catalogState(count = 2, locale = "en") {
  const makeRow = (id, role, name, len, n50, note = "") => ({
    objectType: role === "reference" ? "reference" : "dataset",
    objectId: id,
    originalName: name,
    displayName: name,
    role,
    note,
    statistics: { sequenceCount: 5, totalLengthBp: len, n50, n90: Math.floor(n50 * 0.7) },
    locations: [],
    availableFileCount: 0,
    fastaAvailable: false,
  });
  const references = [makeRow(1, "reference", "reference", 142_480_000, 27_780_000)];
  const datasets = [makeRow(2, "primary", "assembly", 133_230_000, 25_860_000)];
  for (let index = 2; index < count; index += 1) {
    datasets.push(makeRow(index + 1, "support", `aux_${index}`, 120_000_000, 15_000_000));
  }
  const state = {
    locale,
    session: { workspacePath: `/ws/catalog-${count}`, projectId: count },
    initializer: {
      datasets: datasets.map(row => ({ datasetId: row.objectId, name: row.originalName, contigCount: 5, totalLengthBp: row.statistics.totalLengthBp })),
      references: [{ referenceGenomeId: 1, name: "reference" }],
      existingProjects: [{ projectId: count, supportDatasetIds: [] }],
    },
  };
  state.initializer.projectCatalog = {
    key: projectCatalogKey(state),
    data: { projectId: count, references, datasets },
  };
  return state;
}

test("overview sections remember per-project toggles and respect forceExpanded", () => {
  resetOverviewSectionsSession();
  const stateA = { session: { workspacePath: "/ws/a", projectId: 1 } };
  const stateB = { session: { workspacePath: "/ws/b", projectId: 1 } };
  assert.equal(isOverviewSectionExpanded(stateA, "datasets", { defaultExpanded: true }), true);
  assert.equal(toggleOverviewSection(stateA, "datasets", { defaultExpanded: true }), false);
  assert.equal(isOverviewSectionExpanded(stateA, "datasets", { defaultExpanded: true }), false);
  assert.equal(isOverviewSectionExpanded(stateA, "datasets", { defaultExpanded: true, forceExpanded: true }), true);
  assert.equal(isOverviewSectionExpanded(stateB, "datasets", { defaultExpanded: true }), true);
  resetOverviewSectionsSession(overviewSectionProjectKey(stateA));
  assert.equal(isOverviewSectionExpanded(stateA, "datasets", { defaultExpanded: true }), true);
});

test("Datasets section auto-collapses when > 4 rows with inline summary and stays expanded for <= 4 rows", () => {
  resetOverviewSectionsSession();
  const small = catalogState(2, "en");
  const smallHtml = renderProjectCatalog(small);
  assert.match(smallHtml, /data-section-expanded="true"/);
  assert.match(smallHtml, /aria-expanded="true"/);
  assert.doesNotMatch(smallHtml, /id="project-data-catalog-body"[^>]*hidden/);
  assert.match(smallHtml, /class="project-dataset-note" data-empty="true"/);
  assert.match(smallHtml, /project-dataset-note-dash/);

  const large = catalogState(5, "en");
  const largeHtml = renderProjectCatalog(large);
  assert.match(largeHtml, /data-section-expanded="false"/);
  assert.match(largeHtml, /aria-expanded="false"/);
  assert.match(largeHtml, /id="project-data-catalog-body"[^>]*hidden/);
  assert.match(largeHtml, /class="project-section-summary"[^>]*>Reference 142\.48 Mb · Primary 133\.23 Mb \(N50 25\.86 Mb\) · \+3 auxiliary<\/span>/);

  toggleOverviewSection(large, "datasets", { defaultExpanded: false });
  const reopened = renderProjectCatalog(large);
  assert.match(reopened, /data-section-expanded="true"/);
  assert.doesNotMatch(reopened, /id="project-data-catalog-body"[^>]*hidden/);
});

test("Refinement section auto-collapses when empty while keeping import button accessible and expands for active notices", () => {
  resetOverviewSectionsSession();
  const emptyState = {
    locale: "en",
    session: { workspacePath: "/ws/empty-ref", projectId: 11 },
    projectExport: { workspacePath: "/ws/empty-ref", projectId: 11 },
  };
  const emptyHtml = renderProjectRefinementCard(emptyState);
  assert.match(emptyHtml, /data-section-expanded="false"/);
  assert.match(emptyHtml, /id="project-refinement-body"[^>]*hidden/);
  assert.match(emptyHtml, /class="project-section-summary"[^>]*>No records<\/span>/);
  assert.match(emptyHtml, /data-project-refinement-import/);

  emptyState.initializer = {
    projectRefinementUi: { projectKey: "/ws/empty-ref::11", notice: "Imported 2 gap closures." },
  };
  const withNotice = renderProjectRefinementCard(emptyState);
  assert.match(withNotice, /data-section-expanded="true"/);
  assert.doesNotMatch(withNotice, /id="project-refinement-body"[^>]*hidden/);
});

test("Preview controls expose search for >= 6 chromosomes, gaps filter when gaps exist, and expand/collapse all", () => {
  resetOverviewSectionsSession();
  const chromosomes = Array.from({ length: 6 }, (_, index) => ({ chrName: `OZ20493${index + 1}.1`, chrLength: 1000 }));
  const finalPathByChr = Object.fromEntries(chromosomes.map((chr, index) => [
    chr.chrName,
    {
      segments: index % 2 === 0
        ? [{ type: "ctg", assemblyCtgId: index + 1, datasetName: "main", ctgName: `c${index}`, start: 1, end: 500, overallLen: 500 },
           { type: "gap", gapSizeBp: 100 },
           { type: "ctg", assemblyCtgId: index + 20, datasetName: "main", ctgName: `d${index}`, start: 1, end: 400, overallLen: 400 }]
        : [{ type: "ctg", assemblyCtgId: index + 1, datasetName: "main", ctgName: `c${index}`, start: 1, end: 1000, overallLen: 1000 }],
    },
  ]));
  const cards = buildProjectPreviewModel({
    referenceGenomeId: 1,
    chromosomes,
    project: { primaryDatasetId: 1 },
    datasets: [{ datasetId: 1, name: "main" }],
    ctgs: [],
    finalPathByChr,
  });
  const state = {
    locale: "en",
    session: { workspacePath: "/ws/preview-controls", projectId: 3 },
    assembly: { finalPathByChr: {} },
    projectPreview: {
      loaded: true,
      loading: false,
      error: "",
      cards,
      modelVersion: PREVIEW_MODEL_VERSION,
      savedPathSignatures: {},
      localSignature: previewOverrideSignature({}, {}),
      mutationStamp: previewMutationStamp({ workspaceRoot: "/ws/preview-controls", projectId: 3 }),
    },
  };
  const key = previewProjectKey(state);
  state.projectPreview.key = key;

  assert.equal(cards.filter(cardHasGaps).length, 3);
  const controls = renderProjectPreviewControls(state);
  assert.match(controls, /data-preview-filter-input/);
  assert.match(controls, /data-preview-filter-gaps[^>]*>With gaps \(3\)<\/button>/);
  assert.match(controls, /data-preview-toggle-all[^>]*>Expand all<\/button>/);

  setPreviewFilterState(key, { gapsOnly: true, query: "933" });
  const filtered = filterPreviewCards(cards, getPreviewFilterState(key));
  assert.deepEqual(filtered.map(card => card.chrName), ["OZ204933.1"]);

  const filteredHtml = renderProjectPreviewPage(state, { embedded: true, hideHeading: true });
  assert.equal((filteredHtml.match(/data-preview-chr="/g) || []).length, 1);
  assert.match(filteredHtml, /data-preview-chr="OZ204933\.1"/);

  setProjectPreviewExpandedAll(key, filtered.map(card => card.chrName), true);
  assert.equal(projectPreviewSession(key).expanded.has("OZ204933.1"), true);
  assert.match(renderProjectPreviewControls(state), /data-preview-toggle-all[^>]*>Collapse all<\/button>/);

  setPreviewFilterState(key, { query: "nonexistent", gapsOnly: false });
  const emptyFilterHtml = renderProjectPreviewPage(state, { embedded: true, hideHeading: true });
  assert.match(emptyFilterHtml, /project-preview-filter-empty/);
  assert.match(emptyFilterHtml, /data-preview-filter-clear/);
});

test("empty dataset note hover keeps stable column width via grid overlap without display toggling", () => {
  const css = readFileSync(new URL("../../../styles/importer.css", import.meta.url), "utf8");
  assert.match(css, /\.project-dataset-note\[data-empty="true"\]\s*\{[^}]*display:\s*grid/);
  assert.match(css, /\.project-dataset-note\[data-empty="true"\]\s*>\s*span\s*\{[^}]*grid-area:\s*1\s*\/\s*1/);
  assert.doesNotMatch(css, /\.project-dataset-note\[data-empty="true"\][^{]*\{[^}]*display:\s*(?:none|inline)/);
});
