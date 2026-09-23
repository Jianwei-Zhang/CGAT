import { test, assert, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";

const attr = (html, name) => html.match(new RegExp(`${name}="([^"]*)"`))?.[1];
const markers = (html) => [...html.matchAll(/<rect\s+class="track-n-region-marker"[^>]*>/g)].map(([tag]) => tag);

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode}: native N markers remain visible and follow local flipping`, () => {
    const state = createIdentityRenderState(mode);
    const region = { ctgStart: 3001, ctgEnd: 3100, lengthBp: 100 };
    state.assembly.chrCtgs[0].nRegions = [region];
    if (mode === "composition") {
      state.assembly.subviewCompositionCandidates.find((c) => c.assemblyCtgId === 2).ctg.nRegions = [region];
    }
    const before = markers(renderAssemblyPage(state));
    assert.equal(before.length, 2, "main view and local view each render the N marker");
    assert.equal(attr(before[1], "data-n-region-contig-id"), "2");
    assert.equal(attr(before[1], "data-n-region-length"), "100");
    assert.ok(Number(attr(before[1], "width")) >= 6, "short gaps remain visible when zoomed out");
    if (mode === "composition") {
      state.assembly.subview.summary.members.find((m) => m.assemblyCtgId === 2).flipped = true;
    } else {
      state.assembly.subview.flippedCtgs = [{ slot: "bottom", contigId: 2 }];
    }
    const after = markers(renderAssemblyPage(state));
    assert.equal(after.length, 2);
    assert.equal(after[0], before[0], "local flipping must not move the main-view marker");
    assert.ok(Number(attr(after[1], "x")) > Number(attr(before[1], "x")));
    assert.deepEqual(state.assembly.chrCtgs[0].nRegions, [region]);
  });
}
