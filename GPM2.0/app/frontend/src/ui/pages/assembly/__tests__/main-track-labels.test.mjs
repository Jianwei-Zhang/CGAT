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
  return [...html.matchAll(/<div class="assembly-track-label-row[^"]*"([^>]+)>\s*<span class="assembly-track-label-name">([^<]*)<\/span>(?:<span class="assembly-track-role-marker" aria-hidden="true">([^<]*)<\/span>)?/g)]
    .map(([, attrs, name, marker]) => ({ attrs, text: [name, marker].filter(Boolean).join(" ") }));
}

for (const locale of ["zh", "en"]) {
  const primary = "P";
  const auxiliary = "A";
  test(`main track names use compact role suffixes with full accessible labels (${locale})`, () => {
    const rows = labelRows(renderTracks(locale));
    for (const [role, prefix, name, title] of [
      ["primary", primary, "hifiasm", locale === "zh" ? "主数据集轨道（hifiasm）" : "Primary Dataset Track (hifiasm)"],
      ["support", auxiliary, "flye", locale === "zh" ? "辅助数据集轨道（flye）" : "Auxiliary Dataset Track (flye)"],
    ]) {
      const row = rows.find(row => row.attrs.includes(`data-track-label-role="${role}"`));
      assert.ok(row, `missing ${role} track`);
      assert.equal(row.text, `${name} [${prefix}]`);
      assert.ok(row.attrs.includes(`data-app-tooltip="${title}"`));
      assert.ok(row.attrs.includes(`aria-label="${title}"`));
      assert.ok(row.attrs.includes('data-track-label-selectable="1"'));
      assert.ok(row.attrs.includes('data-track-label-source="mother"'));
    }
  });

  test(`unnamed primary track keeps its role suffix without fabricating a dataset name (${locale})`, () => {
    const rows = labelRows(renderAssemblyPage({ ...createState(), locale }));
    const row = rows.find(row => row.attrs.includes('data-track-label-role="primary"'));
    assert.equal(row.text, `[${primary}]`);
    assert.ok(row.attrs.includes(locale === "zh" ? 'data-app-tooltip="主数据集轨道"' : 'data-app-tooltip="Primary Dataset Track"'));
    assert.ok(!rows.some(row => row.attrs.includes('data-track-label-role="support"')));
  });

  test(`unselected auxiliary track stays concise, explicit and non-selectable (${locale})`, () => {
    const rows = labelRows(renderTracks(locale, { selected: false }));
    const text = locale === "zh" ? "未选择" : "Not Selected";
    const row = rows.find(row => row.text === `${text} [${auxiliary}]`);
    assert.ok(row);
    assert.ok(row.attrs.includes(locale === "zh" ? 'data-app-tooltip="辅助数据集轨道（未选择）"' : 'data-app-tooltip="Auxiliary Dataset Track (Not Selected)"'));
    assert.ok(!row.attrs.includes("data-track-label-selectable"));
  });

  test(`compact track names preserve case, long names and HTML escaping (${locale})`, () => {
    const name = 'HiFiasm_Chromosome_V1_very_long_name<&"';
    const rows = labelRows(renderTracks(locale, { primaryName: name, supportName: name }));
    for (const [role, prefix] of [["primary", primary], ["support", auxiliary]]) {
      const row = rows.find(row => row.attrs.includes(`data-track-label-role="${role}"`));
      assert.equal(row.text, `HiFiasm_Chromosome_V1_very_long_name&lt;&amp;&quot; [${prefix}]`);
      assert.ok(row.attrs.includes('HiFiasm_Chromosome_V1_very_long_name&lt;&amp;&quot;'));
    }
  });
}

for (const locale of ["zh", "en"]) {
  for (const swapped of [false, true]) {
    test(`local comparison track names match Main while keeping full descriptions (${locale}, swapped=${swapped})`, () => {
      const topTrack = { role: swapped ? "primary" : "support", datasetId: swapped ? 11 : 22 };
      const bottomTrack = { role: swapped ? "support" : "primary", datasetId: swapped ? 22 : 11 };
      const html = renderAssemblyPage({ ...createState({
        initializer: {
          datasets: [{ datasetId: 11, name: "hifiasm" }, { datasetId: 22, name: "flye" }],
          existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
        },
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [{ assemblyCtgId: 30, name: "support-ctg", totalLength: 300, anchorStart: 320 }],
          subview: {
            selectedTrackARole: "primary",
            selectedTrackBRole: "support",
            summary: { mode: "track-pair", topTrack, bottomTrack },
          },
        },
      }), locale });
      const mainRows = labelRows(html).filter(row => row.attrs.includes("data-track-label-role="));
      const localStart = html.indexOf('<article class="assembly-track-panel subview-alignment-card"');
      assert.ok(localStart >= 0);
      const localRows = labelRows(html.slice(localStart));
      assert.equal(localRows.length, 2);
      for (const [index, track] of [topTrack, bottomTrack].entries()) {
        const mainRow = mainRows.find(row => row.attrs.includes(`data-track-label-role="${track.role}"`));
        const localRow = localRows[index];
        assert.ok(mainRow);
        assert.equal(localRow.text, mainRow.text);
        const fullLabel = mainRow.attrs.match(/aria-label="([^"]*)"/)[1];
        assert.ok(localRow.attrs.includes(`aria-label="${fullLabel}"`));
        assert.ok(localRow.attrs.includes(`data-app-tooltip="${fullLabel}"`));
        assert.ok(localRow.attrs.includes('data-app-tooltip-overflow=".assembly-track-label-name"'));
        assert.ok(html.includes(`<span class="subview-candidate-name">${mainRow.text}</span>`));
      }
    });
  }
}
