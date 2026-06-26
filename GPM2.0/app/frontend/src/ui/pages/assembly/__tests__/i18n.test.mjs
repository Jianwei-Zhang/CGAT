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
  assert.equal(i18n.runtime.addSeqTargetMissing, undefined);
  assert.equal(i18n.memberEditor, undefined);
});

test("i18n module centralizes zh error and status labels", () => {
  assert.match(assemblyLabelsZh.errors.invalidParams, /参数/);
  assert.match(assemblyLabelsZh.status.loadingChromosomes, /加载 chromosome/);
  assert.equal(assemblyLabelsZh.degap.jobsTitle, "任务");
  assert.match(assemblyLabelsZh.degap.settingsSummary, /至少填写一个/);
});

test("mapAssemblyError returns english assembly messages when locale is en", () => {
  const mapped = mapAssemblyError({
    stateOrLocale: { locale: "en" },
    error: { code: "CURRENT_CHR_NO_MATCHING_CTG", message: "not found" },
  });

  assert.equal(mapped.userMessage, "No matching contig was found in the current chromosome. Check the search filters and try again.");
});
