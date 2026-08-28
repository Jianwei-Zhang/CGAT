import test from "node:test";
import assert from "node:assert/strict";

import {
  assemblyLabelsZh,
  getAssemblyI18n,
  getAssemblyLocale,
} from "../i18n.js";
import { mapAssemblyError } from "../error-contract.js";

test("getAssemblyLocale prefers root locale then assembly locale and falls back to zh", () => {
  assert.equal(getAssemblyLocale({ locale: "en", assembly: { locale: "zh" } }), "en");
  assert.equal(getAssemblyLocale({ assembly: { locale: "en" } }), "en");
  assert.equal(getAssemblyLocale({ locale: "fr", assembly: { locale: "ja" } }), "zh");
});

test("getAssemblyI18n returns english page copy when locale is en", () => {
  const i18n = getAssemblyI18n({ locale: "en" });

  assert.equal(i18n.tabs.assembly, "Assembly");
  assert.equal(i18n.newSequencesTitle, "New Sequences");
  assert.equal(i18n.statsLabels.currentCtg, "Current Contig");
  assert.equal(i18n.page.finalPathDegapControls, "DEGAP graph controls");
  assert.equal(i18n.degap.jobsTitle, "Jobs");
  assert.equal(i18n.degap.validation.jobOutRequired, "Job --out is required.");
  assert.equal(i18n.contextMenu.addToPhasedTrack, "Add to track {key}");
  assert.equal(i18n.subview.historyRestoreRollbackUnavailableLabel, "No rollback to undo");
  assert.equal(i18n.runtime.addSeqTargetMissing, undefined);
  assert.equal(i18n.memberEditor, undefined);
});

test("i18n module centralizes zh error and status labels", () => {
  assert.match(assemblyLabelsZh.errors.invalidParams, /参数/);
  assert.match(assemblyLabelsZh.status.loadingChromosomes, /加载染色体/);
  assert.equal(assemblyLabelsZh.degap.jobsTitle, "任务");
  assert.match(assemblyLabelsZh.degap.settingsSummary, /至少填写一个/);
  assert.equal(assemblyLabelsZh.page.phasedTrackGrtNoticeTitle, "GRT 结果暂不可用");
  assert.equal(assemblyLabelsZh.page.phasedTrackGrtNoticeConfirm, "我知道了");
  assert.equal(assemblyLabelsZh.trackControls.alignmentLengthBp, "比对长度(bp)");
  assert.equal(assemblyLabelsZh.trackControls.mapq, "MAPQ");
  assert.equal(assemblyLabelsZh.contextMenu.addToPhasedTrack, "添加至轨道 {key}");
  assert.equal(assemblyLabelsZh.subview.historyRestoreRollbackUnavailableLabel, "暂无可撤销的回退操作");
});

test("phased-track GRT notice has complete English copy", () => {
  const i18n = getAssemblyI18n({ locale: "en" });

  assert.equal(i18n.page.phasedTrackGrtNoticeTitle, "GRT results are temporarily unavailable");
  assert.match(i18n.page.phasedTrackGrtNoticeMessage, /Close all phased tracks/);
  assert.equal(i18n.page.phasedTrackGrtNoticeConfirm, "Got it");
});

test("mapAssemblyError returns english assembly messages when locale is en", () => {
  const mapped = mapAssemblyError({
    stateOrLocale: { locale: "en" },
    error: { code: "CURRENT_CHR_NO_MATCHING_CTG", message: "not found" },
  });

  assert.equal(mapped.userMessage, "No matching contig was found in the current chromosome. Check the search filters and try again.");
});
