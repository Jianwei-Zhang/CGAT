import test from "node:test";
import assert from "node:assert/strict";
import { getMessages, t } from "../index.js";
import { libraryLabels } from "../../pages/project-library-view.js";
import { projectLabels } from "../../pages/projects-view.js";
import { buildAssemblyNavigationModel } from "../../shell/assembly-navigation.js";

test("Project names the logical collection; Assembly names its imported entries in both languages", () => {
  for (const locale of ["zh", "en"]) {
    const state = { locale, session: {}, importer: {}, initializer: {}, assembly: {} };
    const navigation = buildAssemblyNavigationModel(state).copy;
    const collection = locale === "en" ? "Project" : "项目";
    const assembly = locale === "en" ? "Assembly" : "组装";
    assert.equal(navigation.partition, collection);
    assert.equal(navigation.project, assembly);
    assert.equal(getMessages(locale, "shell").workspaceRoute, locale === "en" ? "Home" : "首页");
    assert.equal(getMessages(locale, "shell").project, assembly);
    assert.equal(libraryLabels(state).create, locale === "en" ? "New project" : "新建项目");
    assert.equal(projectLabels(state).rename, locale === "en" ? "Rename Assembly" : "重命名组装");
    assert.match(getMessages(locale, "importer").page.openWorkspacePath, /project\.sqlite/);
    assert.match(getMessages(locale, "importer").runtime.importMockCreateWorkspace, /project\.sqlite/);
  }
});
test("terminology is static copy only, never a replacement in user names or paths", () => {
  const name = "Project_partition_项目_分区_MiXeD";
  const path = "D:/Project/partition/project.sqlite";
  assert.equal(t("en", "workspace.cards.selectedProject", { projectName: name }), `Selected Assembly: ${name}`);
  assert.equal(t("zh", "workspace.cards.selectedProject", { projectName: name }), `已选择组装：${name}`);
  assert.equal(t("en", "importer.runtime.sessionRestoringSummary", { workspacePath: path }), `Attempting to restore assembly: ${path}`);
});
