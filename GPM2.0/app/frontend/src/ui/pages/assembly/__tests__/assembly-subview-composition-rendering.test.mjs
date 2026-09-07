import {
  test,
  assert,
  renderAssemblyPage,
  createState,
} from "./tabs-semantics-harness.mjs";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";
import {
  applySubviewComposition,
  normalizeSubviewComposition,
} from "../subview-composition-state.js";
import { buildSubviewAnchorEndpointKey } from "../subview-anchor-state.js";

function compositionState(composition, candidates, pairwiseEvidence = null, assemblyPatch = {}) {
  return createState({
    assembly: {
      subviewTrackView: { alignmentLength: 1, mapq: 0 },
      ...assemblyPatch,
      subview: {
        ...applySubviewComposition({}, composition),
        pairwiseEvidence,
      },
      subviewCompositionCandidates: candidates,
      subviewCompositionCandidatesLoaded: true,
      subviewCompositionViewport: { bpPerPx: 10, leftBp: 0, topPx: 0 },
    },
  });
}

test("composition canvas keeps world positions and exposes evidence cuts from real hit intervals", () => {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [
      { assemblyCtgId: 1, datasetId: 1, name: "ctg1", lengthBp: 1000 },
      { assemblyCtgId: 2, datasetId: 2, name: "ctg2", lengthBp: 1000 },
    ],
  });
  const composition = normalizeSubviewComposition({
    members: [
      { ...candidates[0], lane: "top", xBp: -500 },
      { ...candidates[1], lane: "bottom", xBp: 2000 },
    ],
  });
  const html = renderAssemblyPage(compositionState(composition, candidates, {
    status: "loaded",
    hits: [{
      hitKey: "mixed-1", alignLength: 150, mapq: 60,
      queryAssemblyCtgId: 1,
      subjectAssemblyCtgId: 2,
      queryStart: 100,
      queryEnd: 200,
      subjectStart: 300,
      subjectEnd: 450,
      strand: "+",
    }],
    coverage: [{ status: "ready" }],
  }));

  assert.match(html, /data-subview-composition-scene="1"/);
  assert.match(html, /data-subview-composition-entity-key="assembly:1"[\s\S]*data-subview-rect-x="-50\.00"/);
  assert.match(html, /data-subview-composition-entity-key="assembly:2"[\s\S]*data-subview-rect-x="200\.00"/);
  assert.match(html, /data-subview-hit-key="mixed-1"/);
  assert.match(html, /data-subview-anchor-hit-key="mixed-1"[\s\S]*data-subview-anchor-top-cut-bp="100"[\s\S]*data-subview-anchor-bottom-cut-bp="300"/);
  assert.match(html, /data-subview-anchor-hit-key="mixed-1"[\s\S]*data-subview-anchor-top-cut-bp="200"[\s\S]*data-subview-anchor-bottom-cut-bp="450"/);
});

test("composition canvas renders each effective direction once in labels and hover titles", () => {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [
      { assemblyCtgId: 1, datasetId: 1, name: "ctg1@Chr01 (+)", lengthBp: 1000, orient: "-" },
      { assemblyCtgId: 2, datasetId: 2, name: "ctg2@Chr01 (-)", lengthBp: 1000, orient: "-" },
    ],
  });
  const composition = normalizeSubviewComposition({
    members: [
      { ...candidates[0], lane: "top", xBp: 0 },
      { ...candidates[1], lane: "bottom", xBp: 0, flipped: true },
    ],
  });
  const html = renderAssemblyPage(compositionState(composition, candidates));

  assert.match(html, /data-subview-composition-entity-key="assembly:1"[\s\S]*?<title>ctg1@Chr01 \(-\) ·/);
  assert.match(html, /data-subview-composition-entity-key="assembly:1"[\s\S]*?>ctg1 \(-\)<\/text>/);
  assert.match(html, /data-subview-composition-entity-key="assembly:2"[\s\S]*?<title>ctg2@Chr01 \(\+\) ·/);
  assert.match(html, /data-subview-composition-entity-key="assembly:2"[\s\S]*?>ctg2 \(\+\)<\/text>/);
  assert.doesNotMatch(html, />ctg1@Chr01 \(-\)<\/text>|>ctg2@Chr01 \(\+\)<\/text>/);
  assert.doesNotMatch(html, /ctg1@Chr01 \(\+\) \(-\)|ctg2@Chr01 \(-\) \(\+\)/);
  assert.equal(composition.members[0].label, "ctg1@Chr01 (+)");
  assert.equal(composition.members[1].label, "ctg2@Chr01 (-)");
});

test("composition canvas projects each reference member against the paired contig only", () => {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [{
      assemblyCtgId: 1,
      datasetId: 1,
      name: "ctg1",
      lengthBp: 1000,
      hits: [{
        hitKey: "ref-hit-1", blockLength: 100, mapq: 60,
        refStart: 1000,
        refEnd: 1100,
        ctgStart: 200,
        ctgEnd: 300,
        strand: "+",
      }],
    }],
    refCtgs: [{
      assemblyCtgId: 1,
      name: "Chr01:900-1200",
      referenceChrName: "Chr01",
      segmentStartBp: 900,
      segmentEndBp: 1200,
      lengthBp: 301,
    }],
  });
  const composition = normalizeSubviewComposition({
    members: [
      { ...candidates[0], lane: "top", xBp: 0 },
      { ...candidates[1], lane: "bottom", xBp: 0 },
    ],
  });
  const html = renderAssemblyPage(compositionState(composition, candidates));

  assert.match(html, /data-subview-composition-entity-key="assembly:1"/);
  assert.match(html, /data-subview-composition-entity-key="ref:Chr01:900-1200"/);
  assert.match(html, /data-subview-hit-key="reference:assembly:1\|ref:Chr01:900-1200\|ref-hit-1"/);
});

test("saved members become unavailable only after candidate loading has completed", () => {
  const composition = normalizeSubviewComposition({
    members: [{
      assemblyCtgId: 9,
      source: { role: "support", datasetId: 2 },
      label: "gone",
      lengthBp: 100,
      lane: "top",
      xBp: 0,
    }],
  });
  const loadedHtml = renderAssemblyPage(compositionState(composition, []));
  const loadingState = compositionState(composition, []);
  loadingState.assembly.subviewCompositionCandidatesLoaded = false;
  const loadingHtml = renderAssemblyPage(loadingState);

  assert.match(loadedHtml, /class="track-ctg-group[^"]* is-unavailable"/);
  assert.doesNotMatch(loadingHtml, /class="track-ctg-group[^"]* is-unavailable"/);
});

test("composition canvas keeps baseline GRT anchors when result display is off and Final Path diverges", () => {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [
      { assemblyCtgId: 1, datasetId: 1, name: "ctg1", lengthBp: 1000 },
      { assemblyCtgId: 2, datasetId: 2, name: "ctg2", lengthBp: 1000 },
    ],
  });
  const composition = normalizeSubviewComposition({
    members: [
      { ...candidates[0], lane: "top", xBp: 0 },
      { ...candidates[1], lane: "bottom", xBp: 0 },
    ],
    manualAnchors: [{
      manualAnchorId: "grt-copy:origin",
      coordinateSpace: "assembly",
      origin: { kind: "grt", originId: "origin", baselineKey: "base", chrName: "Chr01", connectionKind: "link" },
      endpointA: {
        endpointKey: buildSubviewAnchorEndpointKey({
          role: candidates[0].source.role,
          contigId: candidates[0].assemblyCtgId,
          datasetId: candidates[0].source.datasetId,
          source: candidates[0].source.sourceType,
        }),
        contigId: 1, cutBp: 100, lengthBp: 1000,
      },
      endpointB: {
        endpointKey: buildSubviewAnchorEndpointKey({
          role: candidates[1].source.role,
          contigId: candidates[1].assemblyCtgId,
          datasetId: candidates[1].source.datasetId,
          source: candidates[1].source.sourceType,
        }),
        contigId: 2, cutBp: 200, lengthBp: 1000,
      },
    }],
  });
  const baseline = {
    mode: "segments",
    chrName: "Chr01",
    grtDisplayAvailable: true,
    segments: [
      {
        segmentId: "left", type: "ctg", assemblyCtgId: 1,
        assemblySourceStart: 1, assemblySourceEnd: 1000, start: 1, end: 100,
        source: { dataset: "primary", contig: "ctg1", start: 1, end: 100, orientation: "+" },
      },
      {
        segmentId: "right", type: "ctg", assemblyCtgId: 2,
        assemblySourceStart: 1, assemblySourceEnd: 1000, start: 200, end: 300,
        source: { dataset: "support", contig: "ctg2", start: 200, end: 300, orientation: "+" },
      },
    ],
  };
  const html = renderAssemblyPage(compositionState(composition, candidates, null, {
    selectedChrName: "Chr01",
    finalPathByChr: { Chr01: { mode: "segments", chrName: "Chr01", segments: [] } },
    grtProjectView: { baselineFinalPathByChr: { Chr01: baseline } },
    grtResultDisplayByChr: { Chr01: { main: false, subview: false } },
  }));

  assert.match(html, /data-subview-composition-scene="1"/);
  assert.match(html, /data-subview-anchor-kind="grt"/);
  assert.match(html, /data-subview-anchor-top-contig-id="1"/);
  assert.match(html, /data-subview-anchor-bottom-contig-id="2"/);
  assert.match(html, /data-subview-fragment-contig-id="1"/);
  assert.match(html, /data-subview-fragment-contig-id="2"/);
});
