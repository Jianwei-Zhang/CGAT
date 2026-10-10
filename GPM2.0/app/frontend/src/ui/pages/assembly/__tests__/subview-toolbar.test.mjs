import { test, assert, createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { readFileSync } from "node:fs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";

const localMarkup = (state) => {
  const html = renderAssemblyPage(state);
  return html.slice(html.indexOf('<article class="subview-selection-panel"'),
    html.indexOf('<article class="card final-path-card"'));
};
const ruleBody = (css, selector) => {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `missing CSS rule: ${selector}`);
  return css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
};
const css = readFileSync(new URL("../../../../styles/subview.css", import.meta.url), "utf8");

for (const mode of ["2-contig", "track-pair", "composition"]) {
  for (const locale of ["zh", "en"]) {
    test(`${mode} ${locale} places exactly one set of controls in the shared toolbar`, () => {
      const state = createIdentityRenderState(mode);
      state.locale = locale;
      if (mode === "2-contig") Object.assign(state.assembly.subview, {
        selectedAContigId: 30, selectedARole: "support", selectedBContigId: 2, selectedBRole: "primary",
      });
      if (mode === "track-pair") state.assembly.subview.selectedTrackSelections = [
        { role: "support", source: "mother", datasetId: 22 }, { role: "primary" },
      ];
      const html = localMarkup(state);
      const sceneStart = html.indexOf('<article class="assembly-track-panel subview-alignment-card"');
      assert.ok(sceneStart > 0);
      const toolbar = html.slice(0, sceneStart);
      const scene = html.slice(sceneStart);
      for (const field of ["subview-track-alignment-length", "subview-track-identity-pct"]) {
        assert.equal(html.match(new RegExp(`id="${field}"`, "g"))?.length, 1);
        assert.ok(toolbar.includes(`id="${field}"`));
        assert.ok(!scene.includes(`id="${field}"`));
      }
      assert.match(toolbar, /data-subview-tools-toggle="1"/);
      assert.match(toolbar, /class="subview-candidate-row"/);
      assert.match(toolbar, /data-subview-action="history-rollback"/);
      assert.match(toolbar, /data-subview-action="history-reset"/);
      assert.doesNotMatch(scene, /assembly-track-panel-head|subview-track-inline-controls| vs /);
      assert.match(scene, /subview-track-layout/);
      assert.doesNotMatch(html, /subview-empty-guide/);
      assert.match(toolbar, /<details class="subview-panel-help">/);
      assert.match(toolbar, /<summary[^>]*title="[^"]+"[^>]*>\?<\/summary>/);
      assert.ok(toolbar.includes(`aria-label="${locale === "zh" ? "局部视图操作说明" : "Local View instructions"}"`));
      assert.match(toolbar, /<p class="subview-panel-guide">[^<]+<\/p>\s*<\/details>/);
      if (mode === "composition") assert.match(toolbar, /data-subview-action="clear-composition"/);
      else assert.equal(toolbar.match(/class="subview-candidate-remove"/g)?.length, 2);
    });
  }
}

for (const locale of ["zh", "en"]) {
  test(`empty ${locale} view keeps visible guidance without inactive parameter controls`, () => {
    const html = localMarkup(createState({ locale }));
    assert.match(html, /<p class="muted subview-empty-guide">[^<]+<\/p>/);
    assert.match(html, /<details class="subview-panel-help">/);
    assert.doesNotMatch(html, /subview-track-inline-controls|subview-alignment-card|data-subview-action="history-/);
  });
}

for (const evidence of [
  { status: "loading" },
  { status: "error", error: "Pairwise evidence failed" },
  { status: "loaded", hits: [] },
  { status: "loaded", coverage: [{ status: "missing" }] },
]) {
  test(`composition preserves ${evidence.status} evidence feedback outside the control row`, () => {
    const state = createIdentityRenderState("composition");
    state.assembly.subview.pairwiseEvidence = evidence;
    const html = localMarkup(state);
    const status = html.match(/<div class="subview-evidence-status" role="status">[\s\S]*?<\/div>/)?.[0];
    assert.ok(status);
    assert.doesNotMatch(status, /subview-track-inline-controls|subview-track-alignment-length/);
    assert.ok(html.indexOf('id="subview-track-alignment-length"') < html.indexOf(status));
  });
}

test("toolbar shrinks names before moving the intact parameter group to another line", () => {
  assert.match(ruleBody(css, ".subview-panel-head"), /flex-wrap:\s*wrap/);
  assert.match(ruleBody(css, ".subview-panel-title-row"), /flex:\s*1 1 360px[\s\S]*flex-wrap:\s*nowrap/);
  assert.match(ruleBody(css, ".subview-candidate-row"), /min-width:\s*0[\s\S]*flex-wrap:\s*nowrap/);
  assert.match(ruleBody(css, ".subview-candidate-badge"), /flex:\s*0 1 auto[\s\S]*min-width:\s*0/);
  assert.match(ruleBody(css, ".subview-candidate-name"), /text-overflow:\s*ellipsis/);
  assert.match(ruleBody(css, ".subview-candidate-remove"), /flex:\s*0 0 26px/);
  assert.match(ruleBody(css, ".subview-track-inline-controls"), /flex:\s*0 0 auto[\s\S]*flex-wrap:\s*nowrap/);
  assert.match(ruleBody(css, ".subview-track-inline-controls .assembly-track-inline-field"), /flex:\s*0 0 auto/);
  assert.match(css, /@media \(max-width: 700px\)[\s\S]*flex-basis: 100%[\s\S]*flex-wrap: wrap/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*\.subview-candidate-row[\s\S]*flex-basis: 100%/);
  assert.doesNotMatch(css, /width: calc\(50% - 6px\)/);
});

test("help disclosure floats over the view rather than consuming toolbar height", () => {
  assert.match(ruleBody(css, ".subview-panel-title-row"), /position:\s*relative/);
  assert.match(ruleBody(css, ".subview-panel-guide"), /position:\s*absolute/);
  assert.match(ruleBody(css, ".subview-panel-guide"), /width:\s*min\(360px, calc\(100vw - 64px\)\)/);
  assert.match(ruleBody(css, ".subview-panel-help > summary:focus-visible"), /outline:\s*2px solid/);
});
