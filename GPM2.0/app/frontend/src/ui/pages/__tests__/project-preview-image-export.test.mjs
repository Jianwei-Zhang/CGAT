import { readProjectPreviewImageStyle } from "../project-preview-presentation.js";
import { paginateProjectPreview, renderProjectPreviewPdf } from "../project-preview-pdf-export.js";
import { PDFDocument, PDFName } from "pdf-lib";
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


test("image refuses loading, stale and empty previews; only rasterization limits oversized canvases", async () => {
  for (const change of [preview => { preview.loading = true; }, preview => { preview.cards = []; },
    preview => { preview.modelVersion--; }, preview => { preview.error = "bad"; }]) {
    const { state } = fixture(1); change(state.projectPreview);
    assert.throws(() => buildProjectPreviewSvgSnapshot(state), /not ready/);
  }
  const { state } = fixture(1);
  state.projectPreview.cards = Array.from({ length: 1000 }, () => state.projectPreview.cards[0]);
  const snapshot = buildProjectPreviewSvgSnapshot(state);
  assert.ok(snapshot.rasterScale < 1);
  assert.equal(snapshot.cardBounds.length, 1000);
  await assert.rejects(renderProjectPreviewPng(snapshot), /过大.*SVG.*PDF/);
});

test("download uses the native save/binary chain, locks duplicate clicks and does not mutate state", async () => {
  const f = fixture(), before = JSON.stringify(f.state), writes = [];
  let release;
  const pending = exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async args => { assert.equal(args.defaultPath, "test_project__preview.svg");
      assert.deepEqual(args.filters, [{ name: "SVG", extensions: ["svg"] }, { name: "PNG", extensions: ["png"] }, { name: "PDF", extensions: ["pdf"] }]); return "D:/preview.png"; },
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
    assert.equal(calls[0].args.defaultPath, "test_project__preview.svg");
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
  const style = readProjectPreviewImageStyle();
  const bodyLeft = 20 + style.padding + 1, left = bodyLeft + style.labelWidth + style.columnGap;
  const geometry = layoutProjectPreviewCard(state.projectPreview.cards[0], 1440 - bodyLeft - left);
  const patch = geometry.tracks.flat().flatMap(body => body.highlights)[0];
  const snapshot = buildProjectPreviewSvgSnapshot(state, { highlightAdopted: true });
  const outlines = [...snapshot.svgMarkup.matchAll(/<rect x="([^"]+)" y="[^"]+" width="([^"]+)" height="14" fill="none" stroke="[^"]+" stroke-width="2" data-preview-adopted-outline="1"/g)];
  assert.ok(outlines.length >= 2, "both result and source intervals retain a thicker inner outline");
  assert.ok(outlines.some(match => Math.abs(Number(match[1]) - (left + patch.x + 1)) < 1e-7
    && Math.abs(Number(match[2]) - (patch.width - 2)) < 1e-7));
  assert.doesNotMatch(snapshot.svgMarkup, /stroke-width="3"/);
});


for (const target of ["D:/预览.svg", "D:/预览.SVG", "D:/folder.with.dot/预览"]) {
  test(`SVG is UTF-8 and does not rasterize: ${target}`, async () => {
    const f = fixture(1), writes = [];
    assert.equal(await exportProjectPreviewImage(f.host, f.store, {
      pickSaveFilePath: async () => target,
      renderProjectPreviewPng: () => assert.fail("SVG must not need a canvas"),
      writeFinalPathExportBinaryFile: async args => writes.push(args),
    }), true);
    assert.equal(writes[0].outputPath, target.endsWith("预览") ? `${target}.svg` : target);
    const svg = Buffer.from(writes[0].bytesBase64, "base64").toString("utf8");
    assert.match(svg, /^<svg/); assert.match(svg, /来源组合/); assert.match(svg, />chr01</);
    assert.doesNotMatch(svg, /�/);
  });
}

test("PDF dispatch uses the common snapshot and save transport", async () => {
  const f = fixture(), writes = [];
  assert.equal(await exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async () => "D:/preview.PDF",
    renderProjectPreviewPdf: async snapshot => { assert.match(snapshot.svgMarkup, />chr12</); return "PDFbytes"; },
    renderProjectPreviewPng: () => assert.fail("PDF renderer handles its own bounded pages"),
    writeFinalPathExportBinaryFile: async args => writes.push(args),
  }), true);
  assert.equal(writes[0].bytesBase64, "PDFbytes"); assert.equal(writes[0].outputPath, "D:/preview.PDF");
});

test("unsupported extensions are rejected without writing mislabeled image bytes", async () => {
  const f = fixture(1);
  assert.equal(await exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async () => "D:/preview.jpg",
    writeFinalPathExportBinaryFile: () => assert.fail("unsupported format must not be saved"),
  }), false);
  assert.match(f.error.textContent, /SVG、PNG 或 PDF/); assert.equal(f.button.disabled, false);
});

test("export uses the App's resting rounded cards, header, role dots, typography and context-label policy", () => {
  const f = fixture(1), style = readProjectPreviewImageStyle();
  const svg = buildProjectPreviewSvgSnapshot(f.state).svgMarkup;
  assert.match(svg, /rx="6"/); assert.match(svg, /height="16"[^>]*rx="2"/);
  assert.match(svg, /height="6"[^>]*rx="3"/);
  assert.ok(svg.includes(`fill="${style.header}"`));
  assert.match(svg, /<circle[^>]*r="3.5"/); assert.match(svg, /10.0 kb/);
  assert.match(svg, /font-size="11.004/);
  assert.doesNotMatch(svg, />primary0(?:<| )/);
  assert.doesNotMatch(svg, /stroke-width="3"/); // Persistent thin outlines remain; hover/focus thickening is excluded.
});

test("export resolves live theme/font/radius styles instead of leaking CSS variables", () => {
  const previous = globalThis.getComputedStyle;
  const root = {}, nodes = { ".project-preview-card": { borderTopLeftRadius: "9px", paddingLeft: "18px" },
    ".project-preview-row": { gridTemplateColumns: "120px 900px", columnGap: "12px" },
    ".project-preview-contig": { borderTopLeftRadius: "4px" } };
  const variables = { "--surface-panel": "#17212e", "--surface-subtle": "#1d2938", "--text-primary": "#e5edf7" };
  globalThis.getComputedStyle = node => node === root
    ? { fontSize: "16px", fontFamily: "Test Font", getPropertyValue: name => variables[name] || "" } : node;
  try {
    const style = readProjectPreviewImageStyle({ ownerDocument: { documentElement: root }, querySelector: selector => nodes[selector] });
    const svg = buildProjectPreviewSvgSnapshot(fixture(1).state, { style }).svgMarkup;
    assert.match(svg, /fill="#17212e"/); assert.match(svg, /fill="#1d2938"/); assert.match(svg, /fill="#e5edf7"/);
    assert.match(svg, /rx="9"/); assert.match(svg, /height="16"[^>]*rx="4"/);
    assert.match(svg, /font-family="Test Font"/); assert.doesNotMatch(svg, /var\(--/);
  } finally { globalThis.getComputedStyle = previous; }
});

test("PDF is parseable, paginated at whole-card boundaries and retains every chromosome", async () => {
  const snapshot = buildProjectPreviewSvgSnapshot(fixture().state), pages = paginateProjectPreview(snapshot);
  assert.ok(pages.length > 1);
  for (const card of snapshot.cardBounds) {
    assert.equal(pages.filter(page => {
      const top = Number(/viewBox="0 ([^ ]+)/.exec(page.snapshot.svgMarkup)[1]);
      return card.top >= top && card.bottom <= top + page.snapshot.height;
    }).length, 1);
  }
  const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/aQAAAAASUVORK5CYII=";
  const rendered = [];
  const bytes = await renderProjectPreviewPdf(snapshot, async page => { rendered.push(page); return png; });
  const pdf = await PDFDocument.load(Buffer.from(bytes, "base64"));
  assert.equal(pdf.getPageCount(), pages.length); assert.equal(rendered.length, pages.length);
  assert.equal((rendered.map(page => page.svgMarkup).join("").match(/>chr\d+</g) || []).length, snapshot.cardBounds.length);
  for (const page of pdf.getPages()) {
    assert.equal(page.getWidth(), 841.89); assert.equal(page.getHeight(), 595.28);
    assert.equal(page.node.Resources().lookup(PDFName.of("XObject")).keys().length, 1);
  }
});

test("PDF pages bypass the full-overview PNG size limit and fit even an unusually tall card", () => {
  const f = fixture(1);
  f.state.projectPreview.cards = Array.from({ length: 300 }, () => f.state.projectPreview.cards[0]);
  const snapshot = buildProjectPreviewSvgSnapshot(f.state);
  assert.ok(snapshot.rasterScale < 1);
  const pages = paginateProjectPreview(snapshot);
  assert.ok(pages.every(page => page.snapshot.rasterScale >= 1));
  assert.ok(pages.every(page => page.y >= 24 && page.width <= 841.89 - 48));
  snapshot.cardBounds = [{ top: 0, bottom: 2000 }];
  const [tall] = paginateProjectPreview(snapshot);
  assert.ok(tall.height <= 595.28 - 48); assert.ok(tall.width < 841.89 - 48);
});

for (const stage of ["render", "save"]) test(`PDF ${stage} failure is visible and unlocks the button`, async () => {
  const f = fixture(1);
  assert.equal(await exportProjectPreviewImage(f.host, f.store, {
    pickSaveFilePath: async () => "D:/preview.pdf",
    renderProjectPreviewPdf: async () => { if (stage === "render") throw new Error("PDF render failed"); return "bytes"; },
    writeFinalPathExportBinaryFile: async () => { throw new Error("PDF save failed"); },
  }), false);
  assert.match(f.error.textContent, new RegExp(`PDF ${stage} failed`));
  assert.equal(previewImageExportIsRunning(f.store), false); assert.equal(f.button.disabled, false);
});
