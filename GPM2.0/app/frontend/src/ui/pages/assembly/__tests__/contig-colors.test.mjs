import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createContigColorResolver, DEFAULT_CONTIG_PALETTE, getContigPalette } from "../contig-colors.js";
import { renderFinalPathGraph } from "../final-path-card.js";
import { buildViewportScopedSvgMarkup } from "../final-path-export-runtime.js";
import { __test, renderProjectExportPage } from "../../project-export-page.js";

const css = (file) => readFileSync(new URL(`../../../../styles/${file}`, import.meta.url), "utf8");
const palette = DEFAULT_CONTIG_PALETTE;

function segment(id, datasetName, extra = {}) {
  return { segmentId: `seg-${id}`, type: "ctg", assemblyCtgId: id, datasetName,
    ctgName: "same-name", overallLen: 100, start: 1, end: 100, ...extra };
}

const colorContext = {
  primaryCtgs: [{ assemblyCtgId: 1 }, { assemblyCtgId: 4 }],
  supportCtgs: [{ assemblyCtgId: 2 }],
};
const segments = [
  segment(1, "hifiasm"),
  segment(2, "flye"),
  segment(3, "hifiasm", { sourceKind: "ref_segment", referenceChrName: "Chr01", memberStartBp: 1, memberEndBp: 100 }),
  segment(4, "flye", { ctgName: "derived-primary@Chr02" }),
  segment(null, "hifiasm", { segmentId: "source-only", source: { dataset: "flye", contig: "original" } }),
  segment(null, "flye", { segmentId: "split-copy", splitFragmentCtgId: 1, ctgName: "renamed-split@Chr02" }),
];

test("normal ctg colors share root tokens across Main/Local View and Project Export", () => {
  const base = css("base.css");
  const assembly = css("assembly.css");
  const project = css("project-export.css");
  for (const [role, colors] of Object.entries(palette)) {
    for (const [key, value] of Object.entries(colors)) {
      assert.ok(base.includes(`--ctg-${role}-${key}: ${value};`));
      assert.ok(assembly.includes(`var(--ctg-${role}-${key})`));
      assert.ok(project.includes(`var(--ctg-${role}-${key})`));
    }
  }
  for (const [selector, role] of [[".track-ctg", "primary"], [".track-ctg.is-companion", "companion"], [".track-ctg.is-ref.is-active", "ref"]]) {
    const block = assembly.slice(assembly.indexOf(`${selector} {`)).split("}")[0];
    assert.ok(block.includes(`fill: var(--ctg-${role}-fill);`));
    assert.ok(block.includes(`stroke: var(--ctg-${role}-stroke);`));
  }
  assert.ok(assembly.includes(".track-ctg.is-active {\n  fill: #b9d0ea;"), "keep transient selection styling");
});

test("roles follow track IDs, canonical sources and Ref, never display names or chromosome suffixes", () => {
  const resolve = createContigColorResolver({ primaryDatasetName: " HIFIASM ", ...colorContext });
  const before = JSON.stringify(segments);
  assert.deepEqual(segments.map(resolve), ["primary", "companion", "ref", "primary", "companion", "primary"]);
  assert.equal(resolve(segment(99, "flye")), "companion");
  assert.equal(resolve(segment(99, "flye", { source: { dataset: "hifiasm" } })), "primary");
  assert.equal(resolve(segment(99, "")), "primary");
  assert.equal(JSON.stringify(segments), before, "color resolution must not rewrite source or coordinates");
});

test("missing primary dataset metadata does not classify every ctg as a companion", () => {
  for (const primaryDatasetName of ["", "-"]) {
    const resolve = createContigColorResolver({ primaryDatasetName });
    assert.equal(resolve(segment(1, "hifiasm")), "primary");
  }
});

test("Final Path and Project Export render the same stable tone for each ctg without forced selection", () => {
  const entry = { chrName: "Chr02", mode: "segments", segments };
  const graph = renderFinalPathGraph({
    escapeAttr: String, escapeHtml: String, finalPathEntry: entry,
    primaryDatasetName: "hifiasm", ctgColorContext: colorContext,
  });
  const state = {
    session: { workspacePath: "/tmp/ws", projectId: 7, projectName: "p1" },
    initializer: { datasets: [{ datasetId: 1, name: "hifiasm" }], existingProjects: [{ projectId: 7, primaryDatasetId: 1 }] },
    assembly: { chrCtgs: [colorContext.primaryCtgs[0]], supportChrCtgs: colorContext.supportCtgs },
    projectExport: { projectId: 7, primaryCtgsByChr: { Chr02: colorContext.primaryCtgs }, finalPathByChr: { Chr02: entry } },
  };
  const before = JSON.stringify(state);
  const html = renderProjectExportPage(state);
  const roles = ["", " is-companion", " is-ref", "", " is-companion", ""];
  assert.deepEqual([...graph.matchAll(/<rect\s+class="(track-ctg[^"]*)"/g)].map(m => m[1]), roles.map(role => `track-ctg${role}`));
  assert.doesNotMatch(graph, /class="track-ctg(?:-group)? is-active/);
  assert.deepEqual([...html.matchAll(/class="project-export-final-path-preview-ctg([^"]*)"/g)].map(m => m[1]), roles);
  assert.equal(JSON.stringify(state), before);
  const snapshot = __test.buildProjectFinalPathSvgSnapshot({ entries: [{ chrName: "Chr02", entry, lengthBp: 600 }],
    primaryDatasetName: "hifiasm", projectName: "p1", ctgColorContext: colorContext });
  const colors = [...snapshot.svgMarkup.matchAll(/rx="3" fill="([^"]+)" stroke="([^"]+)"/g)].map(m => [m[1], m[2]]);
  assert.deepEqual(colors, [palette.primary, palette.companion, palette.ref, palette.primary, palette.companion, palette.primary].map(p => [p.fill, p.stroke]));
});

test("headless exports have the same palette fallbacks as the app", () => {
  assert.deepEqual(getContigPalette(), palette);
});

test("standalone SVG exports resolve current root tokens instead of leaking app-only CSS variables", () => {
  const originalDocument = globalThis.document;
  const originalGetComputedStyle = globalThis.getComputedStyle;
  try {
    globalThis.document = { documentElement: {} };
    globalThis.getComputedStyle = () => ({ getPropertyValue: key => key === "--ctg-primary-fill" ? " #abc123 " : "" });
    assert.equal(getContigPalette().primary.fill, "#abc123");
    assert.equal(getContigPalette().companion.fill, palette.companion.fill);
    const snapshot = __test.buildProjectFinalPathSvgSnapshot({ entries: [{ chrName: "Chr01", lengthBp: 100,
      entry: { segments: [segments[0]] } }], primaryDatasetName: "hifiasm" });
    assert.match(snapshot.svgMarkup, /fill="#abc123"/);
    const svg = buildViewportScopedSvgMarkup({ svgMarkup: '<svg><rect class="track-ctg" /></svg>', width: 100, height: 50 });
    assert.match(svg, /\.track-ctg\{fill:#abc123;/);
    assert.doesNotMatch(svg, /var\(--ctg-/);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (originalGetComputedStyle === undefined) delete globalThis.getComputedStyle;
    else globalThis.getComputedStyle = originalGetComputedStyle;
  }
});
