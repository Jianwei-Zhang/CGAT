import test from "node:test";
import assert from "node:assert/strict";
import { getMessages } from "../../i18n/index.js";
import { projectLabels, renderProjectsBody, renderProjectImportDialog } from "../projects-view.js";
import { projectCatalogKey, renderProjectCatalog } from "../project-catalog-view.js";

function strings(value) {
  return typeof value === "string" ? [value] : Object.values(value).flatMap(strings);
}

test("auxiliary terminology changes presentation while preserving support i18n keys", () => {
  const assembly = getMessages("en", "assembly");
  const workspace = getMessages("en", "workspace");
  assert.equal(assembly.trackControls.supportDataset, "Auxiliary dataset");
  assert.equal(assembly.trackControls.supportTrackLabel, "Auxiliary Dataset Track");
  assert.equal(workspace.cards.supportDataset, "Auxiliary dataset");
  assert.match(assembly.page.finalPathLogSupportTitle, /^Auxiliary /);
  assert.match(workspace.pipeline.appendSupportLabel, /auxiliary datasets/);
  for (const text of [...strings(assembly), ...strings(workspace)]) {
    assert.doesNotMatch(text, /\bSupport\b|\bsupport (?:datasets?|tracks?|ds ctg)\b/);
  }
  // "support" remains a verb when it does not denote the data role.
  assert.match(assembly.page.phasedTrackGrtNoticeMessage, /support LGZ/);
  assert.equal(getMessages("zh", "assembly").trackControls.supportDataset, "辅助数据集");
});

for (const locale of ["en", "zh"]) {
  for (const populated of [false, true]) {
    test(`project entry labels stay compact (${locale}, populated=${populated})`, () => {
      const state = { locale, session: {}, importer: {}, initializer: {} };
      const labels = projectLabels(state);
      assert.equal(labels.import, locale === "en" ? "Import" : "导入");
      assert.equal(labels.open, locale === "en" ? "Open" : "打开");
      const html = renderProjectsBody(state, {
        records: populated ? [{ path: "/rice", projectName: "Rice" }] : [],
        summaryHtml: "", messages: getMessages(state, "importer"), formatTime: () => "",
      });
      assert.match(html, new RegExp(`id="project-import-button"[^>]*>[\\s\\S]*?>${labels.import}<`));
      assert.match(html, new RegExp(`id="project-open-button"[^>]*>[\\s\\S]*?>${labels.open}<`));
      assert.doesNotMatch(html, />Import Project<|>Open project<|>导入项目<|>打开项目</);
    });
  }
}

test("catalog renders Auxiliary for the unchanged support data role", () => {
  const state = { locale: "en", session: { workspacePath: "/rice", projectId: 1 }, initializer: {} };
  state.initializer.projectCatalog = {
    key: projectCatalogKey(state),
    data: { datasets: [{ role: "support", objectId: 2, displayName: "flye", statistics: {} }] },
  };
  const html = renderProjectCatalog(state);
  assert.match(html, /data-dataset-role="support">Auxiliary<\/span>/);
  assert.doesNotMatch(html, />Support</);
});

test("compact entry buttons do not shorten the import dialog title", () => {
  for (const locale of ["en", "zh"]) {
    const state = { locale, importer: { importDialogOpen: true } };
    const html = renderProjectImportDialog(state, getMessages(state, "importer"));
    assert.match(html, new RegExp(`id="project-import-title">${locale === "en" ? "Import Project" : "导入项目"}<`));
  }
});
