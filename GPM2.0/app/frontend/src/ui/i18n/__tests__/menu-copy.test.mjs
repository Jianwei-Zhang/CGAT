import test from "node:test";
import assert from "node:assert/strict";
import { getMessages, t } from "../index.js";
import { projectLabels } from "../../pages/projects-view.js";
import { splitCopy } from "../../pages/assembly/contig-split-boundary.js";
import { localFragmentCopy } from "../../pages/assembly/subview-fragment-copy.js";
import { chrAlignmentCopy } from "../../pages/assembly/contig-chr-alignments.js";

function assertMenuTitleCase(label, key) {
  const smallWords = new Set(["a", "an", "the", "and", "or", "as", "at", "by", "for", "from", "in", "of", "on", "than", "to", "with"]);
  const words = label.replace(/\{[^{}]*\}/g, "").match(/[A-Za-z]+/g) || [];
  for (const word of words) {
    assert.ok(smallWords.has(word) || /^[A-Z]/.test(word), `${key}: ${label}`);
  }
}

test("static English context-menu copy uses Title Case without recasing data at runtime", () => {
  const labels = getMessages("en", "assembly").contextMenu;
  for (const [key, label] of Object.entries(labels)) {
    if (key === "currentVersionUnavailable" || key.endsWith("Confirm") || key === "deleteShorterThanNoMatches") continue;
    assertMenuTitleCase(label, `contextMenu.${key}`);
  }
  for (const key of ["open", "openLocation", "rename", "delete"]) assertMenuTitleCase(projectLabels({ locale: "en" })[key], `project.${key}`);
  for (const key of ["importAddPackage", "copyProject"]) assertMenuTitleCase(getMessages("en", "importer").buttons[key], `importer.${key}`);
  for (const key of ["title", "manual", "left", "right", "undoTitle", "undoLeft", "undoRight"]) assertMenuTitleCase(splitCopy.en[key], `split.${key}`);
  for (const key of ["delete", "deleteFragment", "localDelete", "mainDelete"]) assertMenuTitleCase(localFragmentCopy.en[key], `local.${key}`);
  assertMenuTitleCase(chrAlignmentCopy.en.openAction, "crossChromosome");
  assert.equal(t("en", "assembly.contextMenu.enterContigMenu", { ctgName: "ctg_miXeD.1" }), "Enter ctg_miXeD.1 Menu");
  assert.equal(t("en", "assembly.contextMenu.addToPhasedTrack", { key: "my_hap_a" }), "Add to Track my_hap_a");
  assert.equal(labels.degap, "DEGAP");
  assert.equal(labels.degapGapfillerLeft, "GapFiller Left");
  assert.equal(labels.degapTelseekerRight, "TelSeeker Right");
});

test("split, unsplit and local-delete submenus complement rather than repeat their parent actions", () => {
  assert.deepEqual([splitCopy.en.title, splitCopy.en.manual, splitCopy.en.left, splitCopy.en.right],
    ["Split Contig", "Manually…", "at the Left Boundary", "at the Right Boundary"]);
  assert.deepEqual([splitCopy.zh.title, splitCopy.zh.manual, splitCopy.zh.left, splitCopy.zh.right],
    ["分割 Contig", "手动…", "在左侧边界", "在右侧边界"]);
  assert.deepEqual([splitCopy.en.undoTitle, splitCopy.en.undoLeft, splitCopy.en.undoRight],
    ["Undo Contig Split", "on the Left", "on the Right"]);
  assert.deepEqual([splitCopy.zh.undoTitle, splitCopy.zh.undoLeft, splitCopy.zh.undoRight],
    ["撤销分割 Contig", "左侧", "右侧"]);
  assert.deepEqual([localFragmentCopy.en.delete, localFragmentCopy.en.localDelete, localFragmentCopy.en.mainDelete],
    ["Delete Contig", "from Current Local View Only", "and Synchronize to Main View…"]);
  assert.deepEqual([localFragmentCopy.zh.delete, localFragmentCopy.zh.localDelete, localFragmentCopy.zh.mainDelete],
    ["删除 Contig", "仅在当前局部视图", "并同步主视图…"]);
});

test("other static dropdown menus follow the same English capitalization", () => {
  const assembly = getMessages("en", "assembly"), preview = getMessages("en", "projectPreview");
  for (const key of ["telomereMarkers", "centromereMarkers", "createPhasedTrack"]) assertMenuTitleCase(assembly.trackControls[key], `markers.${key}`);
  for (const key of ["showResult", "displayItems", "resultPath", "alignmentEvidence"]) assertMenuTitleCase(assembly.grtResult[key], `precomputed.${key}`);
  for (const key of ["legend", "download"]) assertMenuTitleCase(preview[key], `preview.${key}`);
});
