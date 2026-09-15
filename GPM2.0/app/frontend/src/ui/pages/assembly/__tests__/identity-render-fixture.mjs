import { createState } from "./tabs-semantics-harness.mjs";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";
import { applySubviewComposition } from "../subview-composition-state.js";

export const identityValues = [100, 85, 95, 90, 0, null, 93.27, 80];

export function createIdentityRenderState(mode = "2-contig", { threshold = 0, overlap = false } = {}) {
  const hits = identityValues.map((identityPct, index) => ({
    hitKey: `evidence-${index + 1}`, identityPct, mapq: 60,
    queryAssemblyCtgId: 30, subjectAssemblyCtgId: 2,
    queryStart: overlap ? 1000 : 500 + index * 1800,
    queryEnd: overlap ? 3000 : 1800 + index * 1800,
    subjectStart: overlap ? 1000 : 500 + index * 1800,
    subjectEnd: overlap ? 3000 : 1800 + index * 1800,
    alignLength: 1300, strand: "+",
  }));
  const ctg = (id, datasetId, name) => ({
    assemblyCtgId: id, datasetId, name, assignedChrName: "Chr01",
    memberCount: 1, totalLength: 16000, lengthBp: 16000, anchorStart: 1,
    hits: hits.map((hit) => ({
      identityPct: hit.identityPct, blockLength: hit.alignLength, mapq: 60,
      refStart: hit.queryStart, refEnd: hit.queryEnd,
      ctgStart: hit.queryStart, ctgEnd: hit.queryEnd,
    })),
  });
  const primary = ctg(2, 11, "primary");
  const support = ctg(30, 22, "companion");
  const prefs = { minTickUnitKb: 1, maxTickCount: 20, alignmentLength: 1, minIdentityPct: threshold };
  const state = createState({
    initializer: {
      datasets: [{ datasetId: 11, name: "primary" }, { datasetId: 22, name: "companion" }],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 2, placedBp: 16000, lengthBp: 16000 }],
      chrCtgs: [primary], supportDatasetId: 22, supportChrCtgs: [support],
      trackView: { ...prefs }, subviewTrackView: { ...prefs },
      subview: {
        mode,
        summary: mode === "track-pair" ? {
          mode, topTrack: { role: "support", source: "mother", datasetId: 22 }, bottomTrack: { role: "primary" },
        } : {
          mode: "2-contig", top: { role: "support", contigId: 30 }, bottom: { role: "primary", contigId: 2 },
        },
        pairwiseEvidence: {
          key: mode === "track-pair" ? "track-pair:support:mother:22:30|primary:2" : "2-contig:support:30:primary:2",
          status: "loaded", hits,
        },
      },
    },
  });
  if (mode === "composition") {
    const candidates = buildSubviewCompositionCandidates({ primaryDatasetId: 11, allChrCtgs: [support, primary] });
    state.assembly.subview = {
      ...applySubviewComposition({}, { members: candidates.map((candidate) => ({
        ...candidate, lane: candidate.assemblyCtgId === 30 ? "top" : "bottom", xBp: 0,
      })) }),
      pairwiseEvidence: { status: "loaded", hits },
    };
    state.assembly.subviewCompositionCandidates = candidates;
    state.assembly.subviewCompositionCandidatesLoaded = true;
    state.assembly.subviewCompositionViewport = { bpPerPx: 20, leftBp: 0, topPx: 0 };
  }
  return state;
}
