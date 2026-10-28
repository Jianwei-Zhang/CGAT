import test from "node:test";
import assert from "node:assert/strict";
import { renderAssemblyPage, createState } from "./tabs-semantics-harness.mjs";

function renderTracks(locale, { primaryName = "hifiasm", supportName = "flye", selected = true } = {}) {
  return renderAssemblyPage({ ...createState({
    initializer: {
      datasets: [{ datasetId: 11, name: primaryName }, { datasetId: 22, name: supportName }],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: { supportDatasetId: selected ? 22 : null },
  }), locale });
}

function labelRows(html) {
  return [...html.matchAll(/<div class="assembly-track-label-row[^"]*"([^>]+)>\s*<span>([^<]*)<\/span>/g)]
    .map(([, attrs, text]) => ({ attrs, text }));
}

for (const locale of ["zh", "en"]) {
  const primary = locale === "zh" ? "主" : "P";
  const auxiliary = locale === "zh" ? "辅" : "A";
  test(`main track names use compact role prefixes with full accessible labels (${locale})`, () => {
    const rows = labelRows(renderTracks(locale));
    for (const [role, prefix, name, title] of [
      ["primary", primary, "hifiasm", locale === "zh" ? "主数据集轨道（hifiasm）" : "Primary Dataset Track (hifiasm)"],
      ["support", auxiliary, "flye", locale === "zh" ? "辅助数据集轨道（flye）" : "Auxiliary Dataset Track (flye)"],
    ]) {
      const row = rows.find(row => row.attrs.includes(`data-track-label-role="${role}"`));
      assert.ok(row, `missing ${role} track`);
      assert.equal(row.text, `[${prefix}] ${name}`);
      assert.ok(row.attrs.includes(`title="${title}"`));
      assert.ok(row.attrs.includes(`aria-label="${title}"`));
      assert.ok(row.attrs.includes('data-track-label-selectable="1"'));
      assert.ok(row.attrs.includes('data-track-label-source="mother"'));
    }
  });

  test(`unnamed primary track keeps its role prefix without fabricating a dataset name (${locale})`, () => {
    const rows = labelRows(renderAssemblyPage({ ...createState(), locale }));
    const row = rows.find(row => row.attrs.includes('data-track-label-role="primary"'));
    assert.equal(row.text, `[${primary}]`);
    assert.ok(row.attrs.includes(locale === "zh" ? 'title="主数据集轨道"' : 'title="Primary Dataset Track"'));
    assert.ok(!rows.some(row => row.attrs.includes('data-track-label-role="support"')));
  });

  test(`unselected auxiliary track stays concise, explicit and non-selectable (${locale})`, () => {
    const rows = labelRows(renderTracks(locale, { selected: false }));
    const text = locale === "zh" ? "未选择" : "Not Selected";
    const row = rows.find(row => row.text === `[${auxiliary}] ${text}`);
    assert.ok(row);
    assert.ok(row.attrs.includes(locale === "zh" ? 'title="辅助数据集轨道（未选择）"' : 'title="Auxiliary Dataset Track (Not Selected)"'));
    assert.ok(!row.attrs.includes("data-track-label-selectable"));
  });

  test(`compact track names preserve case, long names and HTML escaping (${locale})`, () => {
    const name = 'HiFiasm_Chromosome_V1_very_long_name<&"';
    const rows = labelRows(renderTracks(locale, { primaryName: name, supportName: name }));
    for (const [role, prefix] of [["primary", primary], ["support", auxiliary]]) {
      const row = rows.find(row => row.attrs.includes(`data-track-label-role="${role}"`));
      assert.equal(row.text, `[${prefix}] HiFiasm_Chromosome_V1_very_long_name&lt;&amp;"`);
      assert.ok(row.attrs.includes('HiFiasm_Chromosome_V1_very_long_name&lt;&amp;&quot;'));
    }
  });
}
