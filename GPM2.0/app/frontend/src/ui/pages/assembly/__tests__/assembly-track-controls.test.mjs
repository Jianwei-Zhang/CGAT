import {
  test,
  assert,
  readStylesheetTree,
  __testApplySupportDatasetSelection,
  __testSyncSupportDatasetSelection,
  renderAssemblyPage,
  createState,
  createStore,
  createSupportDsStorageMock,
} from "./tabs-semantics-harness.mjs";

test("assembly main view renders v1-style collapsible menus with selectable presets and numeric track inputs", () => {
  const html = renderAssemblyPage(createState());

  assert.doesNotMatch(html, /assembly-v1-tool-strip/);
  assert.match(html, /assembly-track-inline-controls/);
  assert.doesNotMatch(html, /data-tool-menu="you-can"/);
  assert.doesNotMatch(html, /data-tool-menu="about-chr"/);
  assert.doesNotMatch(html, /搜索 contig 名称或 ID/);
  assert.doesNotMatch(html, /打开 \/ 收起染色体列表/);
  assert.doesNotMatch(html, /查看当前 contig/);
  assert.doesNotMatch(html, /id="assembly-print-view-button"/);
  assert.doesNotMatch(html, /id="assembly-export-chr-ctg-pmolecule-button"/);
  assert.doesNotMatch(html, /id="assembly-export-agp-button"/);
  assert.doesNotMatch(html, /Controls \/ 控件/);
  assert.match(html, /辅ds_ctg_len\(bp\)/);
  assert.match(html, /最小刻度单位\(kb\)/);
  assert.match(html, /最多可展示数/);
  assert.match(html, /Alignment Length\(bp\)/);
  assert.match(html, /MAPQ/);
  assert.ok(html.indexOf("辅 ds") < html.indexOf("辅ds_ctg_len"));
  assert.ok(html.indexOf("辅ds_ctg_len") < html.indexOf("最小刻度单位"));
  assert.ok(html.indexOf("最小刻度单位") < html.indexOf("最多可展示数"));
  assert.ok(html.indexOf("最多可展示数") < html.indexOf("Alignment Length"));
  assert.ok(html.indexOf("Alignment Length") < html.indexOf("MAPQ"));

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="supportDsCtgLen">/,
  );
  assert.match(
    html,
    /<input\s+id="assembly-track-support-ds-ctg-len"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="0"\s+autocomplete="off"[^>]*>/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开辅ds_ctg_len\(bp\)候选值" aria-expanded="false" aria-controls="assembly-track-support-ds-ctg-len-menu">/,
  );
  assert.match(html, /<div id="assembly-track-support-ds-ctg-len-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="0"/);
  assert.match(html, /data-track-combo-value="1000"/);
  assert.match(html, /data-track-combo-value="10000"/);
  assert.match(html, /data-track-combo-value="100000"/);

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="minTickUnitKb">/,
  );
  assert.match(
    html,
    /<input\s+id="assembly-track-min-tick-unit-kb"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="10000"\s+autocomplete="off"[^>]*>/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开最小刻度单位\(kb\)候选值" aria-expanded="false" aria-controls="assembly-track-min-tick-unit-kb-menu">/,
  );
  assert.match(html, /<span class="assembly-track-control-marker" aria-hidden="true">▾<\/span>/);
  assert.match(html, /<div id="assembly-track-min-tick-unit-kb-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="250"/);
  assert.match(html, /data-track-combo-value="500"/);
  assert.match(html, /data-track-combo-value="750"/);
  assert.match(html, /data-track-combo-value="1000"/);
  assert.match(html, /data-track-combo-value="10000"/);

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="maxTickCount">/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开最多可展示数候选值" aria-expanded="false" aria-controls="assembly-track-max-tick-count-menu">/,
  );
  assert.match(html, /<div id="assembly-track-max-tick-count-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="5"/);
  assert.match(html, /data-track-combo-value="10"/);
  assert.match(html, /data-track-combo-value="15"/);
  assert.match(html, /data-track-combo-value="20"/);

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="alignmentLength">/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开Alignment Length\(bp\)候选值" aria-expanded="false" aria-controls="assembly-track-alignment-length-menu">/,
  );
  assert.match(html, /<div id="assembly-track-alignment-length-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="1000"/);
  assert.match(html, /data-track-combo-value="10000"/);
  assert.match(html, /data-track-combo-value="100000"/);
  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="mapq">/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开MAPQ候选值" aria-expanded="false" aria-controls="assembly-track-mapq-menu">/,
  );
  assert.match(html, /<div id="assembly-track-mapq-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(
    html,
    /<input\s+id="assembly-track-mapq"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="0"\s+autocomplete="off"[^>]*>/,
  );
  assert.match(html, /data-track-combo-value="0"/);
  assert.match(html, /data-track-combo-value="30"/);
  assert.match(html, /data-track-combo-value="60"/);
  assert.match(html, /data-track-combo-value="90"/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-min-tick-unit-kb-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-max-tick-count-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-alignment-length-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-mapq-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-support-ds-ctg-len-options">/);
});

test("support ds ctg len rules dialog renders close in header and actions in footer", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDsCtgLenRulesDialogOpen: true,
        supportDsCtgLenRulesByChr: {
          Chr01: [
            { startBp: 1, endBp: 5_000_000, supportDsCtgLen: 100000 },
            { startBp: 5_000_001, endBp: 10_000_000, supportDsCtgLen: 0 },
          ],
        },
        trackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
          supportDsCtgLen: 0,
        },
      },
    }),
  );
  const headMatch = html.match(
    /<div class="assembly-support-ds-len-rules-head">([\s\S]*?)<\/div>\s*<div class="assembly-support-ds-len-rules-body">/,
  );
  assert.ok(headMatch, "expected dialog header");
  assert.match(headMatch[1], /data-support-ds-ctg-len-rules-close="1"/);
  assert.doesNotMatch(headMatch[1], /data-support-ds-ctg-len-rules-reset="1"/);
  assert.doesNotMatch(headMatch[1], /data-support-ds-ctg-len-rules-save="1"/);

  const footMatch = html.match(
    /<div class="assembly-support-ds-len-rules-foot">([\s\S]*?)<\/div>\s*<\/div>\s*<\/article>/,
  );
  assert.ok(footMatch, "expected dialog footer");
  assert.match(footMatch[1], /data-support-ds-ctg-len-rules-add="1"/);
  assert.match(footMatch[1], /data-support-ds-ctg-len-rules-reset="1"/);
  assert.match(footMatch[1], /data-support-ds-ctg-len-rules-save="1"/);
});

test("track combo styles keep dropdown menu unclipped", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-track-combo\s*\{[^}]*overflow:\s*visible;/);
  assert.doesNotMatch(css, /\.assembly-track-combo\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-select-shell\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-fixed-select\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-fixed-select\s*\{[^}]*text-overflow:\s*ellipsis;/);
  assert.match(css, /\.assembly-track-fixed-select\s*\{[^}]*white-space:\s*nowrap;/);
});

test("final path card body css keeps a shared bottom padding for graph and table modes", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-body\s*\{[\s\S]*padding-bottom:\s*\d+px;/);
});

test("assembly card spacing css uses one shared stack gap instead of a standalone final-path margin", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-track-content-stack\s*\{[^}]*display:\s*grid;/);
  assert.match(css, /\.assembly-track-content-stack\s*\{[^}]*gap:\s*8px;/);
  assert.doesNotMatch(css, /\.final-path-card\s*\{[^}]*margin-top:\s*\d+px;/);
});

test("main track panel css uses the same horizontal inset rhythm as subview and final path cards", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.card\s*\{[^}]*padding:\s*10px;/);
  assert.match(css, /\.assembly-track-panel\s*\{[^}]*padding:\s*10px;/);
  assert.match(css, /\.assembly-track-panel\s*\{[^}]*gap:\s*8px;/);
  assert.doesNotMatch(css, /\.assembly-track-panel\s*\{[^}]*padding:\s*6px;/);
});

test("final path table body css keeps a graph-like minimum height without vertical centering", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-table-body\s*\{[^}]*min-height:\s*\d+px;/);
  assert.doesNotMatch(css, /\.final-path-card-table-body\s*\{[^}]*align-items:\s*center;/);
  assert.doesNotMatch(css, /\.final-path-card-table-body\s*\{[^}]*place-items:\s*center;/);
});

test("final path index header css centers the # label over the index column", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-list-head\s*>\s*:first-child\s*\{[\s\S]*justify-content:\s*center;/);
  assert.match(css, /\.final-path-card-list-head\s*>\s*:first-child\s*\{[\s\S]*text-align:\s*center;/);
});

test("final path table css uses responsive grids instead of the old fixed 1550px layout", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(css, /\.final-path-card-list-head\s*\{[^}]*min-width:\s*1550px;/);
  assert.doesNotMatch(css, /\.final-path-card-list\s*\{[^}]*min-width:\s*1550px;/);
  assert.doesNotMatch(css, /\.final-path-card-list-head\s*\{[^}]*grid-template-columns:\s*78px minmax\(1450px,\s*1fr\);/);
  assert.doesNotMatch(css, /\.final-path-sort-row\s*\{[^}]*grid-template-columns:\s*78px minmax\(1450px,\s*1fr\);/);
  assert.match(css, /\.final-path-card-list-head,\s*\.final-path-sort-row\s*\{[\s\S]*grid-template-columns:\s*64px minmax\(0,\s*1fr\);/);
  assert.match(css, /\.final-path-card-list-head-card,\s*\.final-path-sort-card-grid\s*\{[\s\S]*grid-template-columns:\s*var\(--final-path-table-columns\);/);
});

test("final path header css places the mode toggle after title and highlights the active mode", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-head\s*\{[^}]*justify-content:\s*space-between;/);
  assert.match(css, /\.final-path-card-title-row\s*\{[^}]*display:\s*inline-flex;/);
  assert.match(css, /\.final-path-card-head-controls\s*\{[^}]*justify-content:\s*flex-end;/);
  assert.match(css, /\.final-path-card-toggle-button\.is-active\s*\{[^}]*font-weight:\s*700;/);
  assert.match(css, /\.final-path-export\s*\{[^}]*position:\s*relative;/);
  assert.match(css, /\.final-path-export-menu\s*\{[^}]*position:\s*absolute;/);
});

test("track tick label css does not force middle anchor", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(css, /\.track-tick-label\s*\{[^}]*text-anchor:\s*middle;/);
});

test("subview candidate row uses left flow for inline placement next to guide text", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.subview-candidate-row\s*\{[^}]*justify-content:\s*flex-start;/);
});

test("subview selection panel exposes a stable local refresh anchor", () => {
  const html = renderAssemblyPage(createState());

  assert.match(html, /<article class="card subview-selection-panel" data-subview-panel="1">/);
});

test("subview band tooltip keeps each contig interval on its own unwrapped line", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.subview-band-tooltip\s*\{[^}]*white-space:\s*pre;/);
  assert.doesNotMatch(css, /\.subview-band-tooltip\s*\{[^}]*white-space:\s*pre-line;/);
});

test("subview hit bands follow top-track color", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.subview-track-svg\s+\.track-collinearity-band\s*\{[^}]*fill:\s*rgba\(97,\s*129,\s*170,\s*0\.24\);[^}]*stroke:\s*rgba\(97,\s*129,\s*170,\s*0\.38\);/,
  );
  assert.match(
    css,
    /\.subview-track-svg\s+\.track-collinearity-band\.is-companion\s*\{[^}]*fill:\s*rgba\(154,\s*126,\s*78,\s*0\.22\);[^}]*stroke:\s*rgba\(154,\s*126,\s*78,\s*0\.34\);/,
  );
});

test("transparent hit-band proxies are hidden only after canvas is ready", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.assembly-track-scroll\.is-track-band-canvas-ready\s+\.subview-track-svg\s+\.track-collinearity-band\[data-track-band-proxy="1"\]\s*\{[^}]*fill:\s*transparent;[^}]*stroke:\s*transparent;/,
  );
  assert.doesNotMatch(
    css,
    /(^|\n)\.subview-track-svg\s+\.track-collinearity-band\[data-track-band-proxy="1"\]\s*\{[^}]*fill:\s*transparent;/,
  );
});

test("hidden contig css uses dashed chips, blue hidden tag, and outline-only bars", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.ctg-chip\.is-hidden-contig\s*\{[\s\S]*border-style:\s*dashed;/);
  assert.match(css, /\.ctg-chip-hidden-tag\s*\{[\s\S]*color:\s*#2e567f;/);
  assert.match(css, /\.track-ctg\.is-hidden-contig,\s*\.track-ctg\.is-hidden-contig\.is-active,\s*\.track-ctg\.is-hidden-contig\.is-multi-selected\s*\{[\s\S]*fill:\s*none;/);
  assert.match(
    css,
    /\.track-ctg\.is-hidden-contig,\s*\.track-ctg\.is-hidden-contig\.is-active,\s*\.track-ctg\.is-hidden-contig\.is-multi-selected\s*\{[\s\S]*pointer-events:\s*all;/,
  );
});

test("mirror contig css preserves fill color while keeping interaction enabled", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.track-ctg\.is-mirror,\s*\.track-ctg\.is-mirror\.is-active,\s*\.track-ctg\.is-mirror\.is-multi-selected,\s*\.track-ctg\.is-mirror\.is-subview-selected\s*\{[\s\S]*pointer-events:\s*all;/,
  );
  assert.doesNotMatch(
    css,
    /\.track-ctg\.is-mirror,\s*\.track-ctg\.is-mirror\.is-active,\s*\.track-ctg\.is-mirror\.is-multi-selected,\s*\.track-ctg\.is-mirror\.is-subview-selected\s*\{[\s\S]*fill:\s*none;/,
  );
  assert.doesNotMatch(css, /\.track-ctg\.is-mirror\.is-companion/);
});

test("mirror contig labels do not force bold font weight", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(css, /\.track-ctg-label\.is-mirror\s*\{[\s\S]*font-weight:/);
});

test("track labels stay on one line and truncate overflow", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-track-label-row\s*\{[^}]*white-space:\s*nowrap;/);
  assert.match(css, /\.assembly-track-label-row\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-label-row\s*\{[^}]*text-overflow:\s*ellipsis;/);
  assert.match(css, /\.assembly-track-label-row\s*>\s*span\s*\{[^}]*white-space:\s*nowrap;/);
  assert.match(css, /\.assembly-track-label-row\s*>\s*span\s*\{[^}]*text-overflow:\s*ellipsis;/);
});

test("assembly main view shows 3-track labels when support ds is available", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /辅\(flye\)/);
  assert.match(html, /ref_chr1/);
  assert.match(html, /主\(hifiasm\)/);
  assert.match(html, /Ctrl\/Cmd 选中任意两个ctg进入subview-ctg/);
  assert.doesNotMatch(html, /Junction 检查/);
  assert.doesNotMatch(html, /subview2-a-ctg-id/);
  assert.doesNotMatch(html, /enter-subview-2/);
});

test("main primary track label is selectable for track-level context menu actions", () => {
  const html = renderAssemblyPage(
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
    }),
  );

  assert.match(
    html,
    /class="assembly-track-label-row[^"]*is-track-selectable[^"]*"[^>]*data-track-label-role="primary"[^>]*data-track-label-selectable="1"[^>]*title="主\(hifiasm\)"[^>]*>\s*<span>主\(hifiasm\)<\/span>/,
  );
});

test("main assembly ctg labels expose runtime lookup metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-alpha", refOrient: "-", assignedChrName: "Chr01", memberCount: 1, totalLength: 10_000_000, anchorStart: 100 },
        ],
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", refOrient: "+", assignedChrName: "Chr01", memberCount: 1, totalLength: 10_000_000, anchorStart: 150 },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /<text class="track-ctg-label[^"]*"[^>]*data-track-label-for-contig-id="2"[^>]*data-track-label-role="primary"[^>]*>ctg-alpha \(-\)<\/text>/);
  assert.match(html, /<text class="track-ctg-label[^"]*"[^>]*data-track-label-for-contig-id="30"[^>]*data-track-label-role="support"[^>]*>support-ctg \(\+\)<\/text>/);
});

test("assembly rendering keeps a fixed 20px visual gap between adjacent support-track contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 200,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const matches = [...html.matchAll(/<rect\s+class="track-ctg is-companion"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/g)];
  assert.ok(matches.length >= 2, "expected at least two support-track contig bars");
  const firstX = Number(matches[0][1]);
  const firstWidth = Number(matches[0][2]);
  const secondX = Number(matches[1][1]);
  const visibleGapPx = secondX - (firstX + firstWidth);
  assert.ok(visibleGapPx >= 19.9, `expected visible gap >= 20px, got ${visibleGapPx}`);
});

test("assembly rendering force-separates dense short tail support-track contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 25_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 31,
            name: "support-tail-1",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 200,
          },
          {
            assemblyCtgId: 32,
            name: "support-tail-2",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 300,
          },
          {
            assemblyCtgId: 33,
            name: "support-tail-3",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 400,
          },
          {
            assemblyCtgId: 34,
            name: "support-tail-4",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 500,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const matches = [...html.matchAll(/<rect\s+class="track-ctg is-companion"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/g)];
  assert.ok(matches.length >= 5, "expected dense support-track bars to be rendered");

  const rects = matches.map((match) => ({
    x: Number(match[1]),
    width: Number(match[2]),
  }));
  for (let index = 1; index < rects.length; index += 1) {
    const previous = rects[index - 1];
    const current = rects[index];
    const visibleGapPx = current.x - (previous.x + previous.width);
    assert.ok(visibleGapPx >= 19.9, `expected visible gap >= 20px, got ${visibleGapPx}`);
  }
});

test("assembly rendering does not clip right-side dense primary contigs after forced gap adjustment", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 25_000_000,
            anchorStart: 10,
          },
          {
            assemblyCtgId: 6,
            name: "ctg-tail-1",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 20,
          },
          {
            assemblyCtgId: 7,
            name: "ctg-tail-2",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 30,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-tail-3",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 40,
          },
        ],
      },
    }),
  );

  const svgMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgMatch, "expected rendered assembly track svg");
  const svgWidth = Number(svgMatch[1]);

  const primaryMatches = [...html.matchAll(/<rect\s+class="track-ctg(?![^"]*is-companion)[^"]*"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/g)];
  assert.ok(primaryMatches.length >= 4, "expected dense primary-track contig bars");

  const maxRight = Math.max(...primaryMatches.map((match) => Number(match[1]) + Number(match[2])));
  assert.ok(
    maxRight <= svgWidth + 0.01,
    `expected right-most primary contig to be fully visible within svg width, got ${maxRight} > ${svgWidth}`,
  );
});

test("main track does not render outside tilted labels for narrow contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "main-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*is-outside/);
  assert.match(html, /<title>main-very-long-contig-label \|/);
  assert.match(html, /<title>support-very-long-contig-label \|/);
});

test("track contig labels use assembly orient before reference orient", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "primary-flipped",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 10,
            orient: "-",
            refOrient: "+",
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-flipped",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 10,
            orient: "-",
            refOrient: "+",
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, />primary-flipped \(-\)<\/text>/);
  assert.match(html, />support-flipped \(-\)<\/text>/);
  assert.doesNotMatch(html, />primary-flipped \(\+\)<\/text>/);
  assert.doesNotMatch(html, />support-flipped \(\+\)<\/text>/);
});

test("assembly visible ctg labels strip chr suffix while hover titles keep full names", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        supportDatasetId: 22,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ptg000009l@Chr22",
            refOrient: "+",
            assignedChrName: "Chr22",
            memberCount: 1,
            totalLength: 500_000,
            anchorStart: 100,
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "Ctg1617@Chr22",
            refOrient: "-",
            assignedChrName: "Chr22",
            memberCount: 1,
            totalLength: 500_000,
            anchorStart: 320,
          },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "Ctg1617@Chr22" },
            bottom: { contigId: 2, role: "primary", contigName: "ptg000009l@Chr22" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, />ptg000009l \(\+\)<\/text>/);
  assert.match(html, />Ctg1617 \(-\)<\/text>/);
  assert.match(html, /<strong>ptg000009l<\/strong>/);
  assert.match(html, /title="ptg000009l@Chr22"/);
  assert.match(html, /class="subview-candidate-badge" title="ptg000009l@Chr22"><strong>A<\/strong>ptg000009l/);
  assert.match(html, /class="subview-candidate-badge" title="Ctg1617@Chr22"><strong>B<\/strong>Ctg1617/);
  assert.match(html, /<title>ptg000009l@Chr22 \| start=/);
  assert.match(html, /<title>Ctg1617@Chr22 \| start=/);
  assert.doesNotMatch(html, />ptg000009l@Chr22 \(\+\)<\/text>/);
  assert.doesNotMatch(html, />Ctg1617@Chr22 \(-\)<\/text>/);
  assert.doesNotMatch(html, /<strong>ptg000009l@Chr22<\/strong>/);
  assert.doesNotMatch(html, /<strong>A<\/strong>ptg000009l@Chr22/);
});

test("main track hides labels that do not fit inside bars and keeps hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "main-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(html, />main-very-long-contig-label \(\+\)<\/text>/);
  assert.doesNotMatch(html, />support-very-long-contig-label \(\+\)<\/text>/);
  assert.match(html, /<title>main-very-long-contig-label \|/);
  assert.match(html, /<title>support-very-long-contig-label \|/);
});

test("main track keeps narrow contig bars visible without outside labels", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "main-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const primaryRectMatch = html.match(
    /<rect\s+class="track-ctg(?![^"]*is-companion)[^"]*"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"[\s\S]*?<\/rect>/,
  );
  assert.ok(primaryRectMatch, "expected a primary-track contig bar");

  const companionRectMatch = html.match(
    /<rect\s+class="track-ctg is-companion[^"]*"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"[\s\S]*?<\/rect>/,
  );
  assert.ok(companionRectMatch, "expected a companion-track contig bar");
  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*is-outside/);
  assert.match(html, /<title>main-very-long-contig-label \|/);
  assert.match(html, /<title>support-very-long-contig-label \|/);
});

test("main track hides right-edge overflow labels instead of widening the svg", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 25_000_000,
            anchorStart: 10,
          },
          {
            assemblyCtgId: 6,
            name: "ctg53",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 20,
          },
          {
            assemblyCtgId: 7,
            name: "ctg502",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 30,
          },
          {
            assemblyCtgId: 8,
            name: "ctg497",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 40,
          },
          {
            assemblyCtgId: 9,
            name: "ctg50",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 50,
          },
          {
            assemblyCtgId: 10,
            name: "ctg49",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 60,
          },
        ],
      },
    }),
  );

  const svgMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgMatch, "expected rendered assembly track svg");

  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*is-outside/);
  assert.match(html, /<title>ctg53 \|/);
  assert.match(html, /<title>ctg497 \|/);
});

test("max-scale main track keeps svg width equal to inner width even with a right-edge overflow label", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [
          { chrName: "Chr01", chrOrder: 1, chrLength: 30_000_000, ctgCount: 2, placedBp: 28_100_000 },
        ],
        trackView: {
          minTickUnitKb: 10_000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 28_000_000,
            anchorStart: 1,
          },
          {
            assemblyCtgId: 6,
            name: "right-edge-overflow-label-very-very-very-long-contig-name",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 100_000,
            anchorStart: 29_000_000,
          },
        ],
      },
    }),
  );

  const innerWidthMatch = html.match(
    /data-track-role="primary"[\s\S]*?data-track-inner-width="([^"]+)"/,
  );
  assert.ok(innerWidthMatch, "expected primary track inner width");
  const innerWidth = Number(innerWidthMatch[1]);

  const svgWidthMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected primary track svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.equal(
    svgWidth,
    innerWidth,
    `expected max-scale primary svg width ${svgWidth} to match inner width ${innerWidth}`,
  );
});

test("companion collinearity band ctg edge stays within the rendered ctg bar after visual gap adjustment", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
            hits: [],
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 10_000_000,
                refStart: 1000,
                refEnd: 10_001_000,
                blockLength: 10_000_000,
              },
            ],
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 200,
            hits: [],
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const supportRectMatch = html.match(/<rect\s+class="track-ctg is-companion"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/);
  assert.ok(supportRectMatch, "expected first companion ctg bar");
  const supportRectX = Number(supportRectMatch[1]);
  const supportRectRight = supportRectX + Number(supportRectMatch[2]);

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected companion-track collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));

  const ctgEdgeLeft = points[0][0];
  const ctgEdgeRight = points[1][0];
  assert.ok(ctgEdgeLeft >= supportRectX - 0.1, `expected band left edge >= bar left edge, got ${ctgEdgeLeft} < ${supportRectX}`);
  assert.ok(
    ctgEdgeRight <= supportRectRight + 0.1,
    `expected band right edge <= bar right edge, got ${ctgEdgeRight} > ${supportRectRight}`,
  );
});

test("mapq threshold filters out low-quality collinearity hits", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 60,
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [],
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-mapq",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 800,
                refStart: 100,
                refEnd: 900,
                blockLength: 1200,
                mapq: 30,
              },
              {
                ctgStart: 900,
                ctgEnd: 1800,
                refStart: 1000,
                refEnd: 1900,
                blockLength: 1200,
                mapq: 60,
              },
            ],
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const companionBandCount = (html.match(/track-collinearity-band is-companion/g) || []).length;
  const sceneMatch = html.match(
    /<script type="application\/json" data-track-band-canvas-scene>([^<]*"kind":"main-track"[^<]*)<\/script>/,
  );
  assert.ok(sceneMatch, "expected a main-track canvas scene");
  const scene = JSON.parse(sceneMatch[1]);
  assert.equal(companionBandCount, 1);
  assert.equal(scene.bands.length, 1);
});

test("mapq input displays manual non-negative value without snapping to presets", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 77,
        },
      },
    }),
  );
  assert.match(
    html,
    /<input\s+id="assembly-track-mapq"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="77"\s+autocomplete="off"[^>]*>/,
  );
});

test("support ds sync persists fallback selection when restored value is invalid", () => {
  const storage = createSupportDsStorageMock(JSON.stringify({ supportDatasetId: 999 }));
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/workspace-sync-persist", projectId: 77 },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 77, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: null,
      },
    }),
  );

  const result = __testSyncSupportDatasetSelection(store, storage);

  assert.deepEqual(result, { changed: true, supportDatasetId: 22 });
  assert.equal(storage.setCalls.length, 1);
  assert.deepEqual(JSON.parse(storage.readRawValue()), { supportDatasetId: 22 });
});

test("support ds sync selects first option after first support dataset is appended", () => {
  const storage = createSupportDsStorageMock(null);
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/workspace-sync-first-append", projectId: 78 },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        ],
        existingProjects: [{ projectId: 78, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
      assembly: {
        supportDatasetId: null,
      },
    }),
  );

  assert.deepEqual(
    __testSyncSupportDatasetSelection(store, storage),
    { changed: false, supportDatasetId: null },
  );

  store.setState({
    ...store.getState(),
    initializer: {
      ...store.getState().initializer,
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 78, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });

  const result = __testSyncSupportDatasetSelection(store, storage);

  assert.deepEqual(result, { changed: true, supportDatasetId: 22 });
  assert.equal(storage.setCalls.length, 1);
  assert.deepEqual(JSON.parse(storage.readRawValue()), { supportDatasetId: 22 });
});

test("support dataset selection persists project-scoped main track view state", async () => {
  const persisted = [];
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/ws", projectId: 7 },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: null,
        supportChrCtgs: [],
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 8,
                datasetName: "",
                ctgName: "flye_ctg8",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 250,
          maxTickCount: 15,
          alignmentLength: 10000,
          mapq: 30,
        },
      },
    }),
  );

  await __testApplySupportDatasetSelection(store, 22, {
    async loadSupportChrCtgs() {
      return [{ assemblyCtgId: 30, name: "Ctg30" }];
    },
    async persistProjectAssemblyViewState(payload) {
      persisted.push(payload);
    },
  });

  assert.equal(store.getState().assembly.supportDatasetId, 22);
  assert.deepEqual(persisted, [
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: 22,
      trackView: {
        supportDsCtgLen: 10000,
        minTickUnitKb: 250,
        maxTickCount: 15,
        alignmentLength: 10000,
        mapq: 30,
      },
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: store.getState().assembly.finalPathByChr,
    },
  ]);
});
