import { sleep } from "../contracts.js";

export function createMockAssemblyOperations(mockStore) {
async function listChrViewCtgsMock({ chrName, datasetId = null }) {
  await sleep(150);
  const samples = {
    Chr01: [
      {
        assemblyCtgId: 1,
        name: "Ctg1",
        assignedChrName: "Chr01",
        chrOrder: 1,
        anchorStart: 58212,
        refOrient: "+",
        placementMode: "auto",
        memberCount: 1,
        totalLength: 437166,
        datasetId: 1,
        datasetName: "hifiasm",
        originId: "utig4-001122l",
        hits: [
          {
            ctgStart: 1200,
            ctgEnd: 5200,
            blockLength: 4000,
          },
          {
            ctgStart: 9200,
            ctgEnd: 9800,
            blockLength: 600,
          },
        ],
      },
      {
        assemblyCtgId: 2,
        name: "Ctg2",
        assignedChrName: "Chr01",
        chrOrder: 2,
        anchorStart: 338097,
        refOrient: "+",
        placementMode: "auto",
        memberCount: 1,
        totalLength: 14814047,
        datasetId: 2,
        datasetName: "flye",
        originId: "contig_98",
        hits: [],
      },
    ],
    Chr02: [
      {
        assemblyCtgId: 3,
        name: "Ctg3",
        assignedChrName: "Chr02",
        chrOrder: 1,
        anchorStart: 45000,
        refOrient: "+",
        placementMode: "auto",
        memberCount: 2,
        totalLength: 6300000,
        datasetId: 1,
        datasetName: "hifiasm",
        originId: "",
        hits: [],
      },
    ],
  };
  const normalizedDatasetId = Number(datasetId);
  const items = (samples[chrName] || []).filter((item) => {
    if (!Number.isFinite(normalizedDatasetId) || normalizedDatasetId <= 0) {
      return true;
    }
    return Number(item.datasetId) === Math.trunc(normalizedDatasetId);
  });
  return {
    items,
  };
}

async function listReferenceTrackMembersMock({ chrName }) {
  await sleep(80);
  const normalizedChrName = String(chrName || "").trim() || "Chr01";
  return {
    items: [
      {
        sourceKind: "ref_segment",
        referenceChrId: 1,
        referenceChrName: normalizedChrName,
        segmentOrder: 1,
        segmentStartBp: 1,
        segmentEndBp: 5000000,
        name: `ref_${normalizedChrName}:1-5000000`,
        anchorStart: 1,
        totalLength: 5000000,
        refOrient: "+",
        hits: [],
      },
    ],
  };
}

const PHASED_HAPLOTYPE_KEYS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const DEFAULT_PHASED_TRACK_GAP_BEFORE_PX = 20;

async function listPhasedChrTracksMock({ projectId, parentChrName }) {
  await sleep(60);
  const normalizedProjectId = Number(projectId);
  const normalizedParentChrName = normalizeRequiredText("parentChrName", parentChrName);
  return {
    projectId: normalizedProjectId,
    parentChrName: normalizedParentChrName,
    tracks: mockStore.phasedChrTracks
      .filter(
        (track) =>
          Number(track.projectId) === normalizedProjectId &&
          track.parentChrName === normalizedParentChrName,
      )
      .sort((left, right) => left.displayOrder - right.displayOrder)
      .map(clonePhasedTrack),
  };
}

async function createPhasedChrTrackMock({ projectId, parentChrName }) {
  await sleep(80);
  const normalizedProjectId = Number(projectId);
  const normalizedParentChrName = normalizeRequiredText("parentChrName", parentChrName);
  const project = mockStore.existingProjects.find(
    (item) => Number(item.projectId) === normalizedProjectId,
  );
  if (!project) {
    throw new Error(`project_id ${normalizedProjectId} does not exist`);
  }
  if (!project.phasedAssemblyEnabled) {
    throw new Error(`project_id ${normalizedProjectId} has phased assembly disabled`);
  }
  const existingKeys = new Set(
    mockStore.phasedChrTracks
      .filter(
        (track) =>
          Number(track.projectId) === normalizedProjectId &&
          track.parentChrName === normalizedParentChrName,
      )
      .map((track) => track.haplotypeKey),
  );
  const haplotypeKey = PHASED_HAPLOTYPE_KEYS.find((key) => !existingKeys.has(key));
  if (!haplotypeKey) {
    throw new Error(`parent_chr_name '${normalizedParentChrName}' already has 26 phased tracks`);
  }
  const displayOrder =
    Math.max(
      0,
      ...mockStore.phasedChrTracks
        .filter(
          (track) =>
            Number(track.projectId) === normalizedProjectId &&
            track.parentChrName === normalizedParentChrName,
        )
        .map((track) => Number(track.displayOrder) || 0),
    ) + 1;
  const track = {
    phasedTrackId: mockStore.nextPhasedTrackId,
    projectId: normalizedProjectId,
    parentChrName: normalizedParentChrName,
    haplotypeKey,
    label: `${normalizedParentChrName}${haplotypeKey}`,
    displayOrder,
    items: [],
  };
  mockStore.nextPhasedTrackId += 1;
  mockStore.phasedChrTracks = [...mockStore.phasedChrTracks, track];
  return { track: clonePhasedTrack(track) };
}

async function deletePhasedChrTrackMock({ projectId, phasedTrackId }) {
  await sleep(70);
  const track = findMockPhasedTrack(projectId, phasedTrackId);
  mockStore.phasedChrTracks = mockStore.phasedChrTracks.filter(
    (item) => item.phasedTrackId !== track.phasedTrackId,
  );
  compactMockPhasedTracks(track.projectId, track.parentChrName);
  return {
    projectId: track.projectId,
    phasedTrackId: track.phasedTrackId,
    parentChrName: track.parentChrName,
    haplotypeKey: track.haplotypeKey,
    label: track.label,
    deleted: true,
  };
}

function compactMockPhasedTracks(projectId, parentChrName) {
  const tracks = mockStore.phasedChrTracks
    .filter((track) =>
      Number(track.projectId) === Number(projectId)
      && track.parentChrName === parentChrName,
    )
    .sort((left, right) => left.displayOrder - right.displayOrder || left.phasedTrackId - right.phasedTrackId);
  tracks.forEach((track, index) => {
    const haplotypeKey = PHASED_HAPLOTYPE_KEYS[index] || track.haplotypeKey;
    track.haplotypeKey = haplotypeKey;
    track.label = `${parentChrName}${haplotypeKey}`;
    track.displayOrder = index + 1;
  });
}

async function addCtgToPhasedChrTrackMock({ projectId, phasedTrackId, assemblyCtgId }) {
  await sleep(70);
  const track = findMockPhasedTrack(projectId, phasedTrackId);
  const displayOrder = Math.max(0, ...track.items.map((item) => Number(item.displayOrder) || 0)) + 1;
  const item = {
    itemId: mockStore.nextPhasedTrackItemId,
    phasedTrackId: track.phasedTrackId,
    assemblyCtgId: Number(assemblyCtgId),
    displayOrder,
    gapBeforePx: DEFAULT_PHASED_TRACK_GAP_BEFORE_PX,
    orient: "+",
  };
  mockStore.nextPhasedTrackItemId += 1;
  track.items = [...track.items, item];
  return { item: { ...item } };
}

async function removePhasedChrTrackItemMock({ projectId, phasedTrackItemId }) {
  await sleep(60);
  const { track, item } = findMockPhasedTrackItem(projectId, phasedTrackItemId);
  track.items = track.items.filter((candidate) => candidate.itemId !== item.itemId);
  return {
    projectId: track.projectId,
    phasedTrackId: track.phasedTrackId,
    phasedTrackItemId: item.itemId,
    removed: true,
  };
}

async function reorderPhasedChrTrackItemsMock({ projectId, phasedTrackId, itemIds }) {
  await sleep(70);
  const track = findMockPhasedTrack(projectId, phasedTrackId);
  const normalizedItemIds = Array.isArray(itemIds) ? itemIds.map((item) => Number(item)) : [];
  const currentIds = track.items.map((item) => item.itemId);
  if (normalizedItemIds.length !== currentIds.length) {
    throw new Error("itemIds must exactly match the current phased track items");
  }
  const sortedRequested = [...normalizedItemIds].sort((left, right) => left - right);
  const sortedCurrent = [...currentIds].sort((left, right) => left - right);
  const sameSet = sortedRequested.every((itemId, index) => itemId === sortedCurrent[index]);
  if (!sameSet) {
    throw new Error("itemIds must exactly match the current phased track items");
  }
  const itemById = new Map(track.items.map((item) => [item.itemId, item]));
  track.items = normalizedItemIds.map((itemId, index) => ({
    ...itemById.get(itemId),
    displayOrder: index + 1,
  }));
  return {
    projectId: track.projectId,
    phasedTrackId: track.phasedTrackId,
    itemCount: track.items.length,
  };
}

function normalizeRequiredText(name, value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    throw new Error(`${name} must not be blank`);
  }
  return normalized;
}

function findMockPhasedTrack(projectId, phasedTrackId) {
  const normalizedProjectId = Number(projectId);
  const normalizedTrackId = Number(phasedTrackId);
  const track = mockStore.phasedChrTracks.find(
    (item) =>
      Number(item.projectId) === normalizedProjectId &&
      Number(item.phasedTrackId) === normalizedTrackId,
  );
  if (!track) {
    throw new Error(`phased_track_id ${normalizedTrackId} does not exist`);
  }
  return track;
}

function findMockPhasedTrackItem(projectId, phasedTrackItemId) {
  const normalizedItemId = Number(phasedTrackItemId);
  for (const track of mockStore.phasedChrTracks) {
    if (Number(track.projectId) !== Number(projectId)) {
      continue;
    }
    const item = track.items.find((candidate) => Number(candidate.itemId) === normalizedItemId);
    if (item) {
      return { track, item };
    }
  }
  throw new Error(`phased_track_item_id ${normalizedItemId} does not exist`);
}

function normalizeMockOrient(value) {
  return String(value || "").trim() === "-" ? "-" : "+";
}

function clonePhasedTrack(track) {
  return {
    ...track,
    items: track.items.map((item) => ({ ...item })),
  };
}

async function listDeletedCtgsMock({ chrName, datasetId = null }) {
  await sleep(80);
  if (String(chrName || "").trim() && String(chrName || "").trim() !== "Chr01") {
    return { items: [] };
  }
  const normalizedDatasetId = Number(datasetId);
  return {
    items: [
      {
        deletedCtgRecordId: 9901,
        projectId: 7,
        assemblyCtgId: 77,
        name: "ctg-deleted-77",
        assignedChrName: "Chr01",
        chrOrder: 9,
        anchorStart: 880000,
        refOrient: "+",
        placementMode: "manual",
        memberCount: 2,
        totalLength: 65432,
        deletedAt: "1775000000",
        datasetId: 11,
      },
    ].filter((item) => {
      if (!Number.isFinite(normalizedDatasetId) || normalizedDatasetId <= 0) {
        return true;
      }
      return Number(item.datasetId) === Math.trunc(normalizedDatasetId);
    }),
  };
}

async function restoreDeletedCtgMock({ projectId, deletedCtgRecordId }) {
  await sleep(100);
  return {
    projectId,
    deletedCtgRecordId,
    assemblyCtgId: 77,
    restoredMemberCount: 2,
    refreshedChrCount: 1,
  };
}

async function getCtgDetailMock({ assemblyCtgId }) {
  await sleep(120);
  return {
    assemblyCtgId,
    name: `Ctg${assemblyCtgId}`,
    assignedChrName: "Chr01",
    chrOrder: 1,
    anchorStart: 58212,
    refOrient: "+",
    placementMode: "auto",
    members: [
      {
        assemblyCtgMemberId: 5000 + assemblyCtgId,
        memberOrder: 1,
        assemblySeqId: 1000 + assemblyCtgId,
        datasetName: "hifiasm",
        seqName: `ptg${String(assemblyCtgId).padStart(6, "0")}l`,
        seqLength: 437166,
        orient: "+",
        sourceStart: 1,
        sourceEnd: 437166,
        leftEndType: "normal",
        rightEndType: "normal",
        hidden: false,
      },
    ],
  };
}

async function listCtgEditCandidatesMock() {
  await sleep(120);
  return {
    moveTargetCtgs: [
      { assemblyCtgId: 2, name: "Ctg2", assignedChrName: "Chr01", chrOrder: 2 },
      { assemblyCtgId: 3, name: "Ctg3", assignedChrName: "Chr02", chrOrder: 1 },
    ],
    addSeqCandidates: [
      {
        assemblySeqId: 7001,
        datasetName: "hifiasm",
        seqName: "ptg_mock_7001",
        seqLength: 120000,
        hidden: false,
      },
      {
        assemblySeqId: 7002,
        datasetName: "flye",
        seqName: "utg_mock_7002",
        seqLength: 83000,
        hidden: true,
      },
    ],
  };
}

async function runCtgEditorActionMock({ projectId, action, args = {} }) {
  await sleep(100);
  if (action === "flip-ctg" && Number(args?.phasedTrackItemId || 0) > 0) {
    const { item } = findMockPhasedTrackItem(projectId, args.phasedTrackItemId);
    item.orient = normalizeMockOrient(item.orient) === "-" ? "+" : "-";
  }
  return {
    action,
    changed: true,
  };
}

async function getJunctionInspectionMock({
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
}) {
  await sleep(220);
  return {
    projectId,
    assignedChrName: "Chr01",
    placementRelation: "overlap",
    overlapBp: 3245,
    gapBp: null,
    sameDataset: true,
    evidenceSource: "self_paf",
    evidenceHitCount: 1,
    left: {
      assemblyCtgId: leftAssemblyCtgId,
      name: `Ctg${leftAssemblyCtgId}`,
    },
    right: {
      assemblyCtgId: rightAssemblyCtgId,
      name: `Ctg${rightAssemblyCtgId}`,
    },
    hits: [
      {
        queryAssemblyCtgId: leftAssemblyCtgId,
        querySourceSeqId: 4503,
        querySourceSeqName: "ctg499",
        subjectAssemblyCtgId: rightAssemblyCtgId,
        subjectSourceSeqId: 1959,
        subjectSourceSeqName: "ctg577",
        strand: "+",
        queryStart: 12,
        queryEnd: 3212,
        subjectStart: 19,
        subjectEnd: 3219,
        mapq: 60,
        identityPct: 99.61,
        alignLength: 3200,
        mismatchCount: 5,
        gapOpenCount: 0,
        evalue: 0,
        bitScore: 5812,
        evidenceOrigin: "self_paf",
      },
    ],
  };
}

async function getTrackPairwiseEvidenceMock({
  projectId,
  topAssemblyCtgIds = [],
  bottomAssemblyCtgIds = [],
}) {
  await sleep(220);
  const topAssemblyCtgId = Number(topAssemblyCtgIds[0] || 0);
  const bottomAssemblyCtgId = Number(bottomAssemblyCtgIds[0] || 0);
  return {
    projectId,
    assignedChrName: "Chr01",
    sameDataset: topAssemblyCtgId > 0 && bottomAssemblyCtgId > 0,
    evidenceSource: "self_paf",
    evidenceHitCount: topAssemblyCtgId > 0 && bottomAssemblyCtgId > 0 ? 1 : 0,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    hits: topAssemblyCtgId > 0 && bottomAssemblyCtgId > 0
      ? [
          {
            queryAssemblyCtgId: topAssemblyCtgId,
            querySourceSeqId: 4503,
            querySourceSeqName: `ctg${topAssemblyCtgId}`,
            subjectAssemblyCtgId: bottomAssemblyCtgId,
            subjectSourceSeqId: 1959,
            subjectSourceSeqName: `ctg${bottomAssemblyCtgId}`,
            strand: "+",
            queryStart: 12,
            queryEnd: 3212,
            subjectStart: 19,
            subjectEnd: 3219,
            mapq: 60,
            identityPct: 99.61,
            alignLength: 3200,
            mismatchCount: 5,
            gapOpenCount: 0,
            evalue: 0,
            bitScore: 5812,
            evidenceOrigin: "self_paf",
          },
        ]
      : [],
  };
}

async function appendEditAuditLogMock({ projectId, category, action, detail }) {
  await sleep(60);
  return {
    id: Math.trunc(Date.now() / 1000),
    projectId,
    category: category || "session",
    action: action || "unknown",
    detail: detail || null,
    createdAt: String(Math.floor(Date.now() / 1000)),
  };
}

  return {
    listChrViewCtgs: listChrViewCtgsMock,
    listReferenceTrackMembers: listReferenceTrackMembersMock,
    listPhasedChrTracks: listPhasedChrTracksMock,
    createPhasedChrTrack: createPhasedChrTrackMock,
    deletePhasedChrTrack: deletePhasedChrTrackMock,
    addCtgToPhasedChrTrack: addCtgToPhasedChrTrackMock,
    removePhasedChrTrackItem: removePhasedChrTrackItemMock,
    reorderPhasedChrTrackItems: reorderPhasedChrTrackItemsMock,
    listDeletedCtgs: listDeletedCtgsMock,
    restoreDeletedCtg: restoreDeletedCtgMock,
    getCtgDetail: getCtgDetailMock,
    listCtgEditCandidates: listCtgEditCandidatesMock,
    runCtgEditorAction: runCtgEditorActionMock,
    getJunctionInspection: getJunctionInspectionMock,
    getTrackPairwiseEvidence: getTrackPairwiseEvidenceMock,
    appendEditAuditLog: appendEditAuditLogMock,
  };
}
