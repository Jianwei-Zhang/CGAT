import { test, assert, createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { applySubviewComposition } from "../subview-composition-state.js";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";

function controlState() {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [1, 2, 3].map((id) => ({
      assemblyCtgId: id, datasetId: id === 1 ? 1 : 2,
      name: `ctg${id}`, lengthBp: 30_000,
    })),
  });
  const composition = { members: candidates.map((member, index) => ({
    ...member, lane: index === 0 ? "top" : "bottom", xBp: index === 0 ? -5_000 : index * 30_000,
  })) };
  return createState({
    assembly: {
      subview: {
        ...applySubviewComposition({}, composition),
        pairwiseEvidence: {
          status: "loaded", loadedMinAlignmentLength: 1, loadedMinMapq: 0,
          hits: [
            { hitKey: "short", alignLength: 100, mapq: 60 },
            { hitKey: "low-mapq", alignLength: 1000, mapq: 10 },
            { hitKey: "pass", alignLength: 1000, mapq: 60 },
            { hitKey: "missing-mapq", alignLength: 1000 },
          ].map((hit) => ({ ...hit, queryAssemblyCtgId: 1, subjectAssemblyCtgId: 2,
            queryStart: 1, queryEnd: 100, subjectStart: 200, subjectEnd: 300, strand: "+" })),
        },
      },
      subviewCompositionCandidates: candidates,
      subviewCompositionCandidatesLoaded: true,
      subviewCompositionViewport: { bpPerPx: 20, leftBp: -5000, topPx: 0 },
      subviewTrackView: { minTickUnitKb: 1, maxTickCount: 10, alignmentLength: 1, mapq: 0 },
    },
  });
}

function hitKeys(state) {
  return [...renderAssemblyPage(state).matchAll(/<polygon[^>]*data-subview-hit-key="([^"]+)"/g)]
    .map((match) => match[1]);
}

test("composition applies both thresholds to cached pairwise hits without mutating evidence or positions", () => {
  const state = controlState();
  const originalSubview = structuredClone(state.assembly.subview);
  assert.deepEqual(hitKeys(state), ["short", "low-mapq", "pass", "missing-mapq"]);
  state.assembly.subviewTrackView.alignmentLength = 1000;
  assert.deepEqual(hitKeys(state), ["low-mapq", "pass", "missing-mapq"]);
  state.assembly.subviewTrackView.mapq = 60;
  assert.deepEqual(hitKeys(state), ["pass"]);
  state.assembly.subviewTrackView.mapq = 61;
  assert.deepEqual(hitKeys(state), []);
  state.assembly.subviewTrackView.mapq = 0;
  state.assembly.subviewTrackView.alignmentLength = 1;
  assert.deepEqual(hitKeys(state), ["short", "low-mapq", "pass", "missing-mapq"]);
  assert.deepEqual(state.assembly.subview, originalSubview);
});

test("composition filtering keeps raw fallback hit identities and handles reversed lane order", () => {
  const state = controlState();
  const hits = state.assembly.subview.pairwiseEvidence.hits;
  hits.forEach((hit) => { delete hit.hitKey; });
  Object.assign(hits[2], { queryAssemblyCtgId: 2, subjectAssemblyCtgId: 1 });
  state.assembly.subviewTrackView.alignmentLength = 500;
  state.assembly.subviewTrackView.mapq = 30;
  assert.deepEqual(hitKeys(state), ["composition-pairwise-3"]);
  assert.match(renderAssemblyPage(state), /data-subview-anchor-hit-key="composition-pairwise-3"/);
});

test("composition reference projections use block length and MAPQ before creating bands and hit zones", () => {
  const state = controlState();
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [{ assemblyCtgId: 1, datasetId: 1, name: "ctg1", lengthBp: 30_000,
      hits: [
        { hitKey: "short", blockLength: 100, mapq: 60 },
        { hitKey: "low", blockLength: 1000, mapq: 0 },
        { hitKey: "pass", block_length: 1000, mapQ: 60 },
      ].map((hit) => ({ ...hit, refStart: 100, refEnd: 1100, ctgStart: 1, ctgEnd: 1001 })),
    }],
    refCtgs: [{ assemblyCtgId: 9, name: "Chr01:1-30000", referenceChrName: "Chr01",
      segmentStartBp: 1, segmentEndBp: 30000, lengthBp: 30000 }],
  });
  state.assembly.subview = applySubviewComposition({}, {
    members: candidates.map((member, index) => ({ ...member, lane: index === 0 ? "top" : "bottom", xBp: 0 })),
  });
  state.assembly.subviewCompositionCandidates = candidates;
  assert.equal(hitKeys(state).length, 3);
  Object.assign(state.assembly.subviewTrackView, { alignmentLength: 1000, mapq: 60 });
  assert.deepEqual(hitKeys(state), ["reference:assembly:1|ref:Chr01:1-30000|pass"]);
  assert.doesNotMatch(renderAssemblyPage(state), /data-subview-anchor-hit-key="[^"]*\|(?:short|low)"/);
});

test("composition emits main-view-aligned non-negative ruler metadata using the current minimum tick unit", () => {
  const state = controlState();
  let html = renderAssemblyPage(state);
  assert.match(html, /data-subview-virtual-ruler="1"/);
  assert.match(html, /data-subview-ruler-origin-x="0.0000"/);
  assert.match(html, /data-subview-ruler-window-start="0.0000"/);
  assert.match(html, /data-subview-ruler-tick-bp="1000.0000"/);
  state.assembly.subviewTrackView.minTickUnitKb = 2;
  html = renderAssemblyPage(state);
  assert.match(html, /data-subview-ruler-tick-bp="2000.0000"/);
});

test("composition GRT switch and both layer selections control the shared result scene", () => {
  const state = controlState();
  const baseline = {
    mode: "segments", chrName: "Chr01", grtDisplayAvailable: true,
    segments: [1, 2].map((id) => ({
      segmentId: `segment-${id}`, type: "ctg", assemblyCtgId: id,
      assemblySourceStart: 1, assemblySourceEnd: 30000, start: 100, end: 1000,
      source: { dataset: `ds${id}`, contig: `ctg${id}`, start: 100, end: 1000, orientation: "+" },
    })),
    displayEvidence: [{ evidenceId: "grt-evidence", tool: "minimap2",
      source: { assemblyCtgId: 1, assemblySourceStart: 1, assemblySourceEnd: 30000, start: 100, end: 1000, orientation: "+" },
      target: { assemblyCtgId: 2, assemblySourceStart: 1, assemblySourceEnd: 30000, start: 100, end: 1000, orientation: "+" },
    }],
  };
  state.assembly.grtProjectView = { recipe: { finalPathSchemaVersion: "2" }, baselineFinalPathByChr: { Chr01: baseline } };
  state.assembly.finalPathByChr = { Chr01: baseline };
  for (const enabled of [false, true]) {
    for (const resultPath of [false, true]) {
      for (const alignmentEvidence of [false, true]) {
        state.assembly.grtResultDisplayByChr = { Chr01: { main: false, subview: enabled,
          subviewLayers: { resultPath, alignmentEvidence } } };
        const html = renderAssemblyPage(state);
        assert.equal(/data-grt-result-interval="1"/.test(html), enabled && resultPath);
        assert.equal(/data-grt-result-junction="link"/.test(html), enabled && resultPath);
        assert.equal(/data-grt-display-evidence="grt-evidence"/.test(html), enabled && alignmentEvidence);
        assert.match(html, /data-subview-anchor-kind="grt"/, "baseline anchor references remain independent");
        assert.match(html, /data-grt-result-entry-key="assembly:1"/, "drag preview can identify GRT endpoints");
      }
    }
  }
});
