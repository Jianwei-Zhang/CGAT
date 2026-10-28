import { layoutProjectPreviewCard } from "../project-preview-layout.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../state/store.js";
import { previewMutationStamp } from "../../../services/preview-content-events.js";
import { buildProjectPreviewModel, previewProjectKey } from "../project-preview-state.js";
import { PREVIEW_MODEL_VERSION, previewOverrideSignature } from "../project-preview-cache.js";
import { buildProjectPreviewSvgSnapshot, exportProjectPreviewImage, previewImageExportIsRunning,
  renderProjectPreviewPng, syncPreviewImageDownloadButton } from "../project-preview-image-export.js";

function fixture(count = 12) {
  const chromosomes = Array.from({ length: count }, (_, i) => ({ chrName: `chr${String(i + 1).padStart(2, "0")}`, chrLength: 10000 }));
  const inputs = { chromosomes, referenceGenomeId: 1, project: { primaryDatasetId: 1, supportDatasetIds: [2] },
    datasets: [{ datasetId: 1, name: "pre" }, { datasetId: 2, name: "assembly" }],
    ctgs: chromosomes.flatMap((chr, i) => [
      { assemblyCtgId: i * 2 + 1, datasetId: 1, datasetName: "pre", name: `primary${i}`, totalLength: 10000, assignedChrName: chr.chrName, anchorStart: 0 },
      { assemblyCtgId: i * 2 + 2, datasetId: 2, datasetName: "assembly", name: `donor${i}`, totalLength: 9000, assignedChrName: chr.chrName, anchorStart: -100, orient: "-" },
    ]), finalPathByChr: Object.fromEntries(chromosomes.map((chr, i) => [chr.chrName, { segments: [
      { type: "ctg", assemblyCtgId: i * 2 + 2, datasetName: "assembly", start: 100, end: 120, overallLen: 9000 },
      { type: "gap", gapSizeBp: 1 },
    ] }])) };
  const state = { locale: "zh", activeRoute: "projectExport", session: { workspacePath: "D:/ws", projectId: 1, projectName: "test<project>" },
    assembly: { finalPathByChr: {} } };
  state.projectPreview = { loaded: true, key: previewProjectKey(state), modelVersion: PREVIEW_MODEL_VERSION,
    mutationStamp: previewMutationStamp({ workspaceRoot: "D:/ws", projectId: 1 }),
    savedPathSignatures: {}, localSignature: previewOverrideSignature({}, {}), cards: buildProjectPreviewModel(inputs) };
  const button = { disabled: false }, error = { hidden: true, textContent: "" };
  const host = { querySelector: selector => selector === "[data-preview-download]" ? button
    : selector === "[data-preview-export-error]" ? error : null };
  const store = createStore(state);
  return { state: store.getState(), store, host, button, error };
}

test("complete image includes all offscreen chromosome cards and complete source bodies, without UI actions", () => {
  const { state } = fixture(), before = JSON.stringify(state);
  const snapshot = buildProjectPreviewSvgSnapshot(state);
  assert.match(snapshot.svgMarkup, /<title>test&lt;project&gt;<\/title>/);
  assert.doesNotMatch(snapshot.svgMarkup, /<text[^>]*>(?:预览|Preview)(?: ·|<)/);
  for (let i = 1; i <= 12; i++) assert.match(snapshot.svgMarkup, new RegExp(`>chr${String(i).padStart(2, "0")}<`));
  assert.equal((snapshot.svgMarkup.match(/data-source-length="9000"/g) || []).length, 12);
  assert.match(snapshot.svgMarkup, />pre</); assert.match(snapshot.svgMarkup, />assembly</);
  assert.match(snapshot.svgMarkup, />Ref</); assert.match(snapshot.svgMarkup, />Final Path</);
  assert.doesNotMatch(snapshot.svgMarkup, /foreignObject|<button|进入装配|刷新|项目明细|data-grt|style=|var\(--/);
  assert.ok(snapshot.height > 12 * 120);
  assert.ok(snapshot.rasterScale >= 1 && snapshot.rasterScale <= 2);
  assert.equal(JSON.stringify(state), before);
});


test("image refuses loading, stale and empty previews and oversized complete canvases", () => {
  for (const change of [preview => { preview.loading = true; }, preview => { preview.cards = []; },
    preview => { preview.modelVersion--; }, preview => { preview.error = "bad"; }]) {
    const { state } = fixture(1); change(state.projectPreview);
    assert.throws(() => buildProjectPreviewSvgSnapshot(state), /not ready/);
  }
  const { state } = fixture(1);
  state.projectPreview.cards = Array.from({ length: 1000 }, () => state.projectPreview.cards[0]);
  assert.throws(() => buildProjectPreviewSvgSnapshot(state), /过大/);
});

test("download uses the native save/binary chain, locks duplicate clicks and does not mutate state", async () => {
  const f = fixture(), before = JSON.stringify(f.state), writes = [];
  let release;
  const pending = exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async args => { assert.equal(args.defaultPath, "test_project__preview.png"); return "D:/preview.png"; },
    renderProjectPreviewPng: snapshot => { assert.match(snapshot.svgMarkup, />chr12</); return new Promise(resolve => { release = resolve; }); },
    writeFinalPathExportBinaryFile: async args => writes.push(args),
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.button.disabled, true); assert.equal(previewImageExportIsRunning(f.store), true);
  assert.equal(await exportProjectPreviewImage(f.host, f.store), false);
  release("PNGbytes"); assert.equal(await pending, true);
  assert.deepEqual(writes, [{ outputPath: "D:/preview.png", bytesBase64: "PNGbytes", stateOrLocale: f.state }]);
  assert.equal(f.button.disabled, false); assert.equal(previewImageExportIsRunning(f.store), false);
  assert.equal(JSON.stringify(f.store.getState()), before);
});

test("canceling Save is silent and does not render or write a file", async () => {
  const f = fixture(); let calls = 0;
  assert.equal(await exportProjectPreviewImage(f.host, f.store, { pickSaveFilePath: async () => "",
    renderProjectPreviewPng: () => calls++, writeFinalPathExportBinaryFile: () => calls++ }), false);
  assert.equal(calls, 0); assert.equal(f.error.hidden, true); assert.equal(f.button.disabled, false);
});

for (const stage of ["dialog", "raster"]) test(`project switch during ${stage} cannot write an obsolete preview`, async () => {
  const f = fixture(); let writes = 0;
  const switchProject = () => f.store.setState({ session: { workspacePath: "D:/other", projectId: 2 }, projectPreview: null });
  const result = await exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async () => { if (stage === "dialog") switchProject(); return "D:/preview.png"; },
    renderProjectPreviewPng: async () => { switchProject(); return "PNGbytes"; },
    writeFinalPathExportBinaryFile: async () => writes++,
  });
  assert.equal(result, false); assert.equal(writes, 0); assert.equal(f.error.hidden, true);
  assert.equal(f.button.disabled, true);
});

test("a changed same-project preview is rejected before file write", async () => {
  const f = fixture(); let writes = 0;
  assert.equal(await exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async () => "D:/preview.png",
    renderProjectPreviewPng: async () => {
      f.store.setState({ projectPreview: { ...f.store.getState().projectPreview, cards: [...f.state.projectPreview.cards] } }); return "bytes";
    }, writeFinalPathExportBinaryFile: async () => writes++,
  }), false);
  assert.equal(writes, 0);
});

test("raster and save failures are visible, escaped as text, and release the export lock", async () => {
  for (const step of ["raster", "save"]) {
    const f = fixture();
    assert.equal(await exportProjectPreviewImage(f.host, f.store, {
      pickSaveFilePath: async () => "D:/preview.png",
      renderProjectPreviewPng: async () => { if (step === "raster") throw new Error("<decode failed>"); return "bytes"; },
      writeFinalPathExportBinaryFile: async () => { throw new Error("permission denied"); },
    }), false);
    assert.equal(f.error.hidden, false);
    assert.match(f.error.textContent, step === "raster" ? /<decode failed>/ : /permission denied/);
    assert.equal(previewImageExportIsRunning(f.store), false); assert.equal(f.button.disabled, false);
  }
});

test("PNG encoding uses the complete snapshot dimensions and always releases its object URL", async () => {
  const original = { Image: globalThis.Image, document: globalThis.document,
    create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  const sizes = [], revoked = []; let canvas;
  URL.createObjectURL = () => "blob:preview"; URL.revokeObjectURL = url => revoked.push(url);
  globalThis.Image = class { set src(url) { queueMicrotask(() => this.onload()); } };
  globalThis.document = { createElement: tag => {
    assert.equal(tag, "canvas");
    canvas = { getContext: () => ({ scale: (...args) => sizes.push(args), drawImage: (...args) => sizes.push(args.slice(1)) }),
      toDataURL: () => "data:image/png;base64,PNG" }; return canvas;
  } };
  try {
    const snapshot = buildProjectPreviewSvgSnapshot(fixture().state);
    assert.equal(await renderProjectPreviewPng(snapshot), "PNG");
    assert.equal(canvas.width, Math.floor(snapshot.width * snapshot.rasterScale));
    assert.equal(canvas.height, Math.floor(snapshot.height * snapshot.rasterScale));
    assert.deepEqual(sizes[1], [0, 0, snapshot.width, snapshot.height]);
    canvas.toDataURL = () => "data:,";
    globalThis.document.createElement = () => canvas;
    await assert.rejects(renderProjectPreviewPng(snapshot), /Failed to encode/);
    assert.deepEqual(revoked, ["blob:preview", "blob:preview"]);
  } finally {
    globalThis.Image = original.Image; globalThis.document = original.document;
    URL.createObjectURL = original.create; URL.revokeObjectURL = original.revoke;
  }
});


test("default save and binary transports receive the real native command contract", async () => {
  const f = fixture(), calls = [], previous = globalThis.window;
  globalThis.window = { __TAURI__: { core: { invoke: async (command, args) => {
    calls.push({ command, args });
    if (command === "pick_save_file_path") return "D:/complete-preview.png";
    if (command === "write_final_path_export_binary_file") {
      assert.equal(args.outputPath, "D:/complete-preview.png");
      assert.equal(args.bytesBase64, "PNG"); return { outputPath: args.outputPath };
    }
    throw new Error(`Unexpected command ${command}`);
  } } } };
  try {
    assert.equal(await exportProjectPreviewImage(f.host, f.store, { renderProjectPreviewPng: async () => "PNG" }), true);
    assert.deepEqual(calls.map(call => call.command), ["pick_save_file_path", "write_final_path_export_binary_file"]);
    assert.equal(calls[0].args.defaultPath, "test_project__preview.png");
  } finally { globalThis.window = previous; }
});


test("the Overview toolbar action outside Preview follows loading and export lock state", async () => {
  const f = fixture(1), previewHost = { closest: selector => selector === "[data-overview-project]" ? f.host : null };
  f.button.disabled = true;
  syncPreviewImageDownloadButton(previewHost, f.store); assert.equal(f.button.disabled, false);
  f.store.setState({ projectPreview: { ...f.store.getState().projectPreview, loading: true } });
  syncPreviewImageDownloadButton(previewHost, f.store); assert.equal(f.button.disabled, true);
  f.store.setState({ projectPreview: { ...f.store.getState().projectPreview, loading: false } });
  let release;
  const pending = exportProjectPreviewImage(f.host, f.store, { pickSaveFilePath: () => new Promise(resolve => { release = resolve; }) });
  syncPreviewImageDownloadButton(previewHost, f.store); assert.equal(f.button.disabled, true);
  release(""); await pending;
  syncPreviewImageDownloadButton(previewHost, f.store); assert.equal(f.button.disabled, false);
});

test("PNG keeps one row per dataset, retaining source context without an unpositioned text list", () => {
  const f = fixture(1), card = f.state.projectPreview.cards[0];
  card.tracks[1].unpositioned.push({ name: "NEVER_POSITIONED", length: 500, start: null, reverse: false, highlights: [] });
  const before = buildProjectPreviewSvgSnapshot(f.state);
  assert.doesNotMatch(before.svgMarkup, /NEVER_POSITIONED|未定位|Unpositioned/);
  card.tracks[1].unpositioned = [];
  assert.equal(buildProjectPreviewSvgSnapshot(f.state).height, before.height);
});


test("image export shares the on-screen Final Path mapping for adopted outlines", () => {
  const { state } = fixture(1);
  const geometry = layoutProjectPreviewCard(state.projectPreview.cards[0], 1440 - 176 - 28);
  const patch = geometry.tracks.flat().flatMap(body => body.highlights)[0];
  const snapshot = buildProjectPreviewSvgSnapshot(state);
  const outlines = [...snapshot.svgMarkup.matchAll(/<rect x="([^"]+)" y="[^"]+" width="([^"]+)" height="14" fill="none"/g)];
  assert.equal(outlines.length, 1);
  assert.ok(Math.abs(Number(outlines[0][1]) - (176 + patch.x)) < 1e-7);
  assert.ok(Math.abs(Number(outlines[0][2]) - patch.width) < 1e-7);
});
