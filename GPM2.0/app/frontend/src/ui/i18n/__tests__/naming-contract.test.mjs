import { previewMutationStamp } from "../../../services/preview-content-events.js";
import { renderFinalPathCard } from "../../pages/assembly/final-path-card.js";
import test from "node:test";
import assert from "node:assert/strict";
import { getMessages, t } from "../index.js";
import { APP_SETTINGS_COPY } from "../../shell/app-settings-panel.js";
import { projectLabels } from "../../pages/projects-view.js";
import { chrAlignmentCopy } from "../../pages/assembly/contig-chr-alignments.js";
import { buildFinalPathTsvText } from "../../pages/assembly/final-path-export-runtime.js";
import { __test as exportTest, renderProjectExportPage } from "../../pages/project-export-page.js";
import { renderAssemblyPage, createState } from "../../pages/assembly/__tests__/tabs-semantics-harness.mjs";

function leaves(value, prefix = "") {
  return Object.entries(value).flatMap(([key, item]) => typeof item === "string"
    ? [[`${prefix}${key}`, item]] : leaves(item, `${prefix}${key}.`));
}

for (const domain of ["assembly", "importer", "workspace", "shell", "projectPreview"]) {
  test(`human-facing ${domain} copy expands shorthand while retaining bilingual keys/placeholders`, () => {
    const en = new Map(leaves(getMessages("en", domain))), zh = new Map(leaves(getMessages("zh", domain)));
    assert.deepEqual([...en.keys()], [...zh.keys()]);
    for (const [key, value] of en) {
      const placeholder = text => (text.match(/\{[^{}]+\}/g) || []).sort();
      assert.deepEqual(placeholder(value), placeholder(zh.get(key)), `${domain}.${key}`);
      for (const text of [value, zh.get(key)]) {
        assert.doesNotMatch(text.replace(/\{[^{}]*\}/g, ""), /(?<![\w-])(?:ds|ctgs?|len|chr|ref|seq)(?![\w-])/i,
          `${domain}.${key}: ${text}`);
      }
    }
  });
}

test("major titles, minor labels, actions and real system options have distinct English roles", () => {
  const assembly = getMessages("en", "assembly"), workspace = getMessages("en", "workspace");
  assert.equal(assembly.page.primaryAlignmentViewTitle, "Main View");
  assert.equal(assembly.page.phasedTrackGrtNoticeTitle, "GRT Results Are Temporarily Unavailable");
  assert.equal(assembly.page.membersCardTitle, "{projectLabel}_{currentChrLabel} Primary Dataset Members");
  assert.equal(assembly.trackControls.supportDatasetLengthRulesTitle, "Auxiliary Contig Length Rules");
  assert.equal(assembly.trackControls.supportDatasetLengthBp, "Auxiliary contig length (bp)");
  assert.equal(assembly.trackControls.supportDataset, "Auxiliary dataset");
  assert.equal(assembly.trackControls.alignmentLengthBp, "Alignment length (bp)");
  assert.equal(assembly.contextMenu.hideSelectedContigs, "Hide selected contigs ({count})");
  assert.equal(assembly.contextMenu.addToSubviewTop, "Top track", "submenu destinations execute actions");
  assert.equal(assembly.subview.tools.compositionManager.lanes.top, "Top Track", "the actual lane value stays Title Case");
  assert.equal(assembly.trackControls.unconfigured, "Not Configured");
  assert.equal(workspace.buttons.createProject, "Create project");
  assert.equal(workspace.cards.primaryDataset, "Primary dataset");
  assert.equal(APP_SETTINGS_COPY.en.title, "App Settings");
  assert.equal(APP_SETTINGS_COPY.en.system, "Follow System");
  assert.equal(APP_SETTINGS_COPY.en.follow, "Follow Interface");
  assert.equal(projectLabels({ locale: "en" }).extractedOption, "Extracted Directory");
  assert.equal(projectLabels({ locale: "en" }).extracted, "Extracted directory");
  assert.equal(chrAlignmentCopy.en.title, "Cross-Chromosome Alignments");
  assert.equal(chrAlignmentCopy.en.openAction, "Cross-chromosome alignments…");
});

test("Chinese controls use the approved full names rather than exposing source-field abbreviations", () => {
  const assembly = getMessages("zh", "assembly");
  assert.equal(assembly.trackControls.supportDataset, "辅助数据集");
  assert.equal(assembly.trackControls.supportDatasetLengthBp, "辅助组装 Contig 长度 (bp)");
  assert.equal(assembly.page.membersCardTitle, "{projectLabel}_{currentChrLabel} 主数据集成员");
  assert.equal(assembly.page.finalPathOverallLenCol, "Contig 长度");
  assert.equal(assembly.page.finalPathOriginIdCol, "来源 ID");
  assert.equal(assembly.page.finalPathDetailUsedBy, "使用染色体");
});

test("user identifiers and names remain verbatim inside the recased system copy", () => {
  const projectName = "my_ds.ctg_LEN_miXeD", chrName = "NC_141021.1", dataset = "ds ctg MiXeD Dataset";
  assert.equal(t("en", "workspace.cards.selectedProject", { projectName }), `Selected Project: ${projectName}`);
  assert.equal(t("en", "assembly.trackControls.supportTrackLabelWithName", { name: dataset }), `Auxiliary Dataset Track (${dataset})`);
  const state = createState({ locale: "en", session: { projectName }, assembly: {
    selectedChrName: chrName, chromosomes: [{ chrName, chrOrder: 1, ctgCount: 1, placedBp: 100 }],
    finalPathByChr: { [chrName]: { mode: "segments", chrName, segments: [{ segmentId: "ctg_ds_1", type: "ctg",
      assemblyCtgId: 2, datasetName: dataset, ctgName: "ctgRaw_Len@NC_141021.1", overallLen: 100, start: 1, end: 100 }] } },
  } });
  const html = renderAssemblyPage(state);
  assert.ok(html.includes(`${projectName}_${chrName} Final Path`));
  assert.ok(html.includes(`${dataset}_ctgRaw_Len@NC_141021.1`));
  assert.ok(html.includes('data-final-path-segment-id="ctg_ds_1"'));
});

test("display-field expansion does not rename the two existing TSV schemas", () => {
  const entry = { chrName: "NC_141021.1", mode: "segments", segments: [] };
  assert.equal(buildFinalPathTsvText(entry).split("\n")[0],
    "#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end");
  assert.equal(exportTest.buildProjectFinalPathTsvText([]).split("\n")[0],
    "Chr\t#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end");
  assert.equal(exportTest.getLabels({ locale: "en" }).detailLength, "Length (bp)");
  assert.equal(exportTest.getLabels({ locale: "zh" }).detailLength, "长度 (bp)");
});


for (const locale of ["en", "zh"]) {
  test(`detail tables localize visible captions without changing filter/sort keys or row identities (${locale})`, () => {
    const entry = { chrName: "NC_141021.1", mode: "segments", segments: [{ type: "ctg", segmentId: "raw_seg_1",
      assemblyCtgId: 2, datasetName: "MiXeD_ds", ctgName: "ctgRaw", originId: "origin_ctg_RAW",
      overallLen: 100, start: 1, end: 100 }] };
    const state = { locale, session: { workspacePath: "raw_PATH", projectId: 7, projectName: "MiXeD_Project" },
      initializer: { datasets: [{ datasetId: 1, name: "Primary_RAW", fastaAvailable: true }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 1 }] }, assembly: { finalPathTrackView: {} },
      projectExport: { loading: false, loaded: true, workspacePath: "raw_PATH", mutationStamp: previewMutationStamp({ workspaceRoot: "raw_PATH", projectId: 7 }), projectId: 7, chromosomes: [{ chrName: entry.chrName }],
        primaryCtgsByChr: { [entry.chrName]: [{ assemblyCtgId: 1, datasetName: "Primary_RAW", name: "main", totalLength: 100 }] },
        finalPathByChr: { [entry.chrName]: entry } } };
    const html = renderProjectExportPage(state), labels = exportTest.getLabels(state);
    for (const value of [labels.detailType, labels.detailChromosome, labels.detailDataset, labels.detailOrigin,
      labels.detailStart, labels.detailEnd, labels.detailLength, labels.detailUsedBy]) assert.ok(html.includes(value), value);
    assert.ok(html.includes(`>${labels.supportTypeOption}<`));
    assert.match(html, /data-project-export-detail-filter="chr"/);
    assert.match(html, /data-project-export-detail-sort="length_bp"/);
    assert.doesNotMatch(html, /<th>(?:origin_id|start|end|length_bp|used_by_chr)<\/th>/);
    assert.ok(html.includes("MiXeD_ds")); assert.ok(html.includes("origin_ctg_RAW"));
    const tsv = exportTest.buildProjectFinalPathTsvText([{ chrName: entry.chrName, entry }]);
    assert.ok(tsv.includes("MiXeD_ds_ctgRaw")); assert.ok(tsv.includes("origin_ctg_RAW"));

    const logModel = { primaryDatasetName: "Primary_RAW", primaryCount: { used: 0, total: 1, appended: 0, hidden: 0 },
      primaryLength: { usedBp: 0, totalBp: 100, appendedBp: 0, hiddenBp: 0 },
      supportRows: [{ datasetName: "MiXeD_ds", originId: "origin_ctg_RAW", finalPathStart: 1, finalPathEnd: 100, lengthBp: 100 }], otherChrPrimaryRows: [] };
    const log = renderFinalPathCard({ projectName: "MiXeD_Project", chrName: entry.chrName, finalPathEntry: entry,
      viewMode: "log", finalPathLogModel: logModel }, { i18n: getMessages(locale, "assembly") });
    const copy = getMessages(locale, "assembly").page;
    assert.ok(log.includes(`<th>${copy.finalPathDetailUsedBy}</th>`));
    assert.ok(log.includes(`<th>${copy.finalPathDetailLength}</th>`));
    assert.doesNotMatch(log, /<th>(?:origin_id|start|end|length_bp|used_by_chr)<\/th>/);
    assert.ok(log.includes("origin_ctg_RAW"));
  });
}
