import test from "node:test";
import assert from "node:assert/strict";

import {
  addFinalPathContigRelativeToSegment,
  addFinalPathGapRelativeToSegment,
  appendTrackContigToFinalPath,
  appendFinalPathRow,
  createEmptyFinalPathRow,
  flipFinalPathSegment,
  moveFinalPathRow,
  removeFinalPathRow,
  updateFinalPathRow,
} from "../final-path-runtime.js";

function createStore(assemblyOverrides = {}) {
  let state = {
    locale: "zh",
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
      projectName: "projA",
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      selectedChrName: "Chr01",
      supportDatasetId: 22,
      finalPathViewMode: "graph",
      trackView: {},
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      trackScrollState: {},
      subviewTrackScrollState: {},
      finalPathByChr: {},
      chrCtgs: [
        {
          assemblyCtgId: 9,
          name: "Ctg9",
          originId: "utig4-001122l",
          totalLength: 1200,
          datasetId: 11,
        },
      ],
      supportChrCtgs: [
        {
          assemblyCtgId: 30,
          name: "Ctg30",
          originId: "contig_98",
          totalLength: 2200,
          datasetId: 22,
        },
      ],
      ...assemblyOverrides,
    },
  };
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };
}

function createDeps(overrides = {}) {
  return {
    confirm() {
      return true;
    },
    async persistProjectAssemblyViewState(payload) {
      return payload;
    },
    rerender() {},
    ...overrides,
  };
}

test("appendTrackContigToFinalPath creates the first ctg segment when current chr has no path", async () => {
  const store = createStore();
  const persisted = [];
  let rerenderCount = 0;

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
    },
    createDeps({
      async persistProjectAssemblyViewState(payload) {
        persisted.push(payload);
        return payload;
      },
      rerender() {
        rerenderCount += 1;
      },
    }),
  );

  const entry = store.getState().assembly.finalPathByChr.Chr01;
  assert.equal(entry.mode, "segments");
  assert.equal(entry.segments.length, 1);
  assert.deepEqual(entry.segments[0], {
    segmentId: "seg-1",
    type: "ctg",
    assemblyCtgId: 9,
    datasetName: "hifiasm",
    ctgName: "Ctg9",
    originId: "utig4-001122l",
    overallLen: 1200,
    start: 1,
    end: 1200,
  });
  assert.equal(entry.totalLength, 1200);
  assert.equal(persisted.length, 1);
  assert.equal(rerenderCount, 1);
});

test("appendTrackContigToFinalPath appends after existing segments instead of overwriting", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 30,
            datasetName: "flye",
            ctgName: "Ctg30",
            overallLen: 2200,
            start: 1,
            end: 2200,
          },
        ],
      },
    },
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
    },
    createDeps(),
  );

  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments.length, 2);
  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[0].assemblyCtgId, 30);
  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[1].assemblyCtgId, 9);
});

test("appendFinalPathRow writes to the active final-path haplotype key", async () => {
  const store = createStore({
    isChrPhased: true,
    activePhasedTrackKey: "B",
    activeFinalPathKey: "B",
    phasedChrTracks: [
      { haplotypeKey: "A", label: "Chr01A" },
      { haplotypeKey: "B", label: "Chr01B" },
    ],
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [{ segmentId: "parent", type: "gap", gapSizeBp: 100 }],
      },
    },
  });

  await appendFinalPathRow({}, store, createDeps());

  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments.length, 1);
  assert.equal(store.getState().assembly.finalPathByChr.Chr01B.chrName, "Chr01B");
  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01B.segments, [
    { segmentId: "seg-1", type: "gap", gapSizeBp: 100 },
  ]);
});

test("appendTrackContigToFinalPath preserves reversed orientation from the current track ctg", async () => {
  const store = createStore({
    chrCtgs: [
      {
        assemblyCtgId: 9,
        name: "Ctg9",
        originId: "utig4-001122l",
        totalLength: 1200,
        datasetId: 11,
        refOrient: "-",
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 9,
      datasetName: "hifiasm",
      ctgName: "Ctg9",
      originId: "utig4-001122l",
      overallLen: 1200,
      start: 1200,
      end: 1,
    },
  ]);
});

test("appendTrackContigToFinalPath lets subview-local orientation override source ctg orient", async () => {
  const store = createStore({
    chrCtgs: [
      {
        assemblyCtgId: 9,
        name: "Ctg9",
        originId: "utig4-001122l",
        totalLength: 1200,
        datasetId: 11,
        orient: "+",
        refOrient: "+",
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
      refOrient: "-",
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 9,
      datasetName: "hifiasm",
      ctgName: "Ctg9",
      originId: "utig4-001122l",
      overallLen: 1200,
      start: 1200,
      end: 1,
    },
  ]);
});

test("appendTrackContigToFinalPath preserves an explicit fragment start/end range", async () => {
  const store = createStore();

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
      start: 101,
      end: 500,
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 9,
      datasetName: "hifiasm",
      ctgName: "Ctg9",
      originId: "utig4-001122l",
      overallLen: 1200,
      start: 101,
      end: 500,
    },
  ]);
});

test("appendTrackContigToFinalPath preserves origin id for mirrored support contigs", async () => {
  const store = createStore({
    supportMirroredCtgs: [
      {
        assemblyCtgId: 1929,
        datasetId: 22,
        datasetName: "canu2",
        name: "Ctg1929",
        originId: "ptg0001929l",
        totalLength: 11955319,
        startBp: 1,
        endBp: 11955319,
        lengthBp: 11955319,
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 1929,
      trackRole: "support",
      isMirror: true,
      datasetId: 22,
      start: 1,
      end: 11703605,
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 1929,
      datasetName: "canu2",
      ctgName: "Ctg1929",
      originId: "ptg0001929l",
      overallLen: 11955319,
      start: 1,
      end: 11703605,
    },
  ]);
});

test("appendTrackContigToFinalPath appends ref segments as bounded final-path members", async () => {
  const store = createStore({
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        referenceChrId: 1,
        referenceChrName: "Chr01",
        name: "ref_Chr01:5101-10100",
        segmentStartBp: 5101,
        segmentEndBp: 10100,
        totalLength: 5000,
        refOrient: "+",
        hits: [],
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9001,
      trackRole: "ref",
      sourceKind: "ref_segment",
      referenceChrName: "Chr01",
      segmentStart: 5101,
      segmentEnd: 10100,
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      sourceKind: "ref_segment",
      assemblyCtgId: 9001,
      referenceChrId: 1,
      referenceChrName: "Chr01",
      datasetName: "",
      ctgName: "ref_Chr01:5101-10100",
      originId: "Chr01",
      overallLen: 5000,
      memberStartBp: 5101,
      memberEndBp: 10100,
      start: 1,
      end: 5000,
    },
  ]);
});

test("updateFinalPathRow keeps ref segment ranges inside the original gap-bounded member", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            sourceKind: "ref_segment",
            assemblyCtgId: 9001,
            referenceChrId: 1,
            referenceChrName: "Chr01",
            datasetName: "",
            ctgName: "ref_Chr01:5101-10100",
            originId: "Chr01",
            overallLen: 5000,
            memberStartBp: 5101,
            memberEndBp: 10100,
            start: 1,
            end: 5000,
          },
        ],
      },
    },
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: "seg-1",
      field: "start",
      value: "101",
    },
    createDeps(),
  );

  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[0].ctgName, "ref_Chr01:5201-10100");
  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[0].start, 101);

  const result = await updateFinalPathRow(
    {},
    store,
    {
      segmentId: "seg-1",
      field: "end",
      value: "5001",
    },
    createDeps(),
  );

  assert.equal(result, null);
  assert.equal(store.getState().assembly.actionError, "Start/End 超出 Ctg 区间。");
  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[0].end, 5000);
});

test("appendTrackContigToFinalPath backfills mirror origin id from the support contig pool", async () => {
  const store = createStore({
    supportChrCtgs: [
      {
        assemblyCtgId: 3531,
        name: "Ctg3531",
        originId: "ptg0003531l",
        totalLength: 5332933,
        datasetId: 22,
      },
    ],
    supportMirroredCtgs: [
      {
        assemblyCtgId: 3531,
        datasetId: 22,
        datasetName: "canu2",
        name: "Ctg3531",
        originId: "",
        totalLength: 5332933,
        startBp: 1,
        endBp: 5332933,
        lengthBp: 5332933,
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 3531,
      trackRole: "support",
      isMirror: true,
      datasetId: 22,
      start: 1881287,
      end: 5332933,
    },
    createDeps(),
  );

  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[0].originId, "ptg0003531l");
});

test("appendTrackContigToFinalPath flips explicit fragment ranges when the source track is reversed", async () => {
  const store = createStore({
    chrCtgs: [
      {
        assemblyCtgId: 9,
        name: "Ctg9",
        originId: "utig4-001122l",
        totalLength: 1200,
        datasetId: 11,
        refOrient: "-",
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
      start: 101,
      end: 500,
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 9,
      datasetName: "hifiasm",
      ctgName: "Ctg9",
      originId: "utig4-001122l",
      overallLen: 1200,
      start: 500,
      end: 101,
    },
  ]);
});

test("appendTrackContigToFinalPath honors a subview-local refOrient override without mutating the source track", async () => {
  const store = createStore({
    chrCtgs: [
      {
        assemblyCtgId: 9,
        name: "Ctg9",
        originId: "utig4-001122l",
        totalLength: 1200,
        datasetId: 11,
        orient: "+",
        refOrient: "+",
      },
    ],
  });

  await appendTrackContigToFinalPath(
    {},
    store,
    {
      assemblyCtgId: 9,
      trackRole: "primary",
      isMirror: false,
      datasetId: 11,
      refOrient: "-",
      start: 101,
      end: 500,
    },
    createDeps(),
  );

  assert.equal(store.getState().assembly.chrCtgs[0].refOrient, "+");
  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 9,
      datasetName: "hifiasm",
      ctgName: "Ctg9",
      originId: "utig4-001122l",
      overallLen: 1200,
      start: 500,
      end: 101,
    },
  ]);
});

test("addFinalPathContigRelativeToSegment keeps the source origin id on inserted ctg rows", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            originId: "utig4-001122l",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
      },
    },
  });

  await addFinalPathContigRelativeToSegment(
    {},
    store,
    {
      segmentId: "seg-1",
      placement: "before",
    },
    createDeps({
      prompt() {
        return "30";
      },
    }),
  );

  assert.equal(store.getState().assembly.finalPathByChr.Chr01.segments[0].originId, "contig_98");
});

test("appendFinalPathRow creates a default gap row", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
        updatedAt: "1",
      },
    },
  });
  await appendFinalPathRow({}, store, createDeps());
  const rows = store.getState().assembly.finalPathByChr.Chr01.segments;
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[1], {
    segmentId: "seg-2",
    type: "gap",
    gapSizeBp: 100,
  });
});

test("appendFinalPathRow creates the first gap row when current chr has no final path yet", async () => {
  const store = createStore({
    finalPathByChr: {},
    finalPathViewMode: "table",
  });
  const persisted = [];

  await appendFinalPathRow(
    {},
    store,
    createDeps({
      async persistProjectAssemblyViewState(payload) {
        persisted.push(payload);
        return payload;
      },
    }),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "gap",
      gapSizeBp: 100,
    },
  ]);
  assert.equal(persisted[0].finalPathViewMode, "table");
});

test("createEmptyFinalPathRow materializes the first real ctg row from the editable empty row", async () => {
  const store = createStore({
    finalPathByChr: {},
    finalPathViewMode: "table",
  });
  const persisted = [];

  await createEmptyFinalPathRow(
    {},
    store,
    {
      field: "ctg",
      value: "flye_Ctg30",
    },
    createDeps({
      async persistProjectAssemblyViewState(payload) {
        persisted.push(payload);
        return payload;
      },
    }),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 30,
      datasetName: "flye",
      ctgName: "Ctg30",
      originId: "contig_98",
      overallLen: 2200,
      start: 1,
      end: 2200,
    },
  ]);
  assert.equal(persisted.length, 1);
  assert.equal(persisted[0].finalPathViewMode, "table");
});

test("createEmptyFinalPathRow accepts a single numeric ctg alias", async () => {
  const store = createStore({
    finalPathByChr: {},
    finalPathViewMode: "table",
    chrCtgs: [
      {
        assemblyCtgId: 2,
        name: "Ctg2",
        totalLength: 1800,
        datasetId: 11,
      },
    ],
    supportChrCtgs: [],
  });

  await createEmptyFinalPathRow(
    {},
    store,
    {
      field: "ctg",
      value: "2",
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 2,
      datasetName: "hifiasm",
      ctgName: "Ctg2",
      overallLen: 1800,
      start: 1,
      end: 1800,
    },
  ]);
});

test("updateFinalPathRow validates Ctg and supports Gap row", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
        updatedAt: "1",
      },
    },
  });
  await appendFinalPathRow({}, store, createDeps());
  const draftId = "seg-2";

  const invalidResult = await updateFinalPathRow(
    {},
    store,
    {
      segmentId: draftId,
      field: "ctg",
      value: "not-exists",
    },
    createDeps(),
  );
  assert.equal(invalidResult, null);
  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[1], {
    segmentId: "seg-2",
    type: "gap",
    gapSizeBp: 100,
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: draftId,
      field: "ctg",
      value: "flye_Ctg30",
    },
    createDeps(),
  );
  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[1], {
    segmentId: "seg-2",
    type: "ctg",
    assemblyCtgId: 30,
    datasetName: "flye",
    ctgName: "Ctg30",
    originId: "contig_98",
    overallLen: 2200,
    start: 1,
    end: 2200,
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: draftId,
      field: "start",
      value: 2200,
    },
    createDeps(),
  );
  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: draftId,
      field: "end",
      value: 1,
    },
    createDeps(),
  );
  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[1], {
    segmentId: "seg-2",
    type: "ctg",
    assemblyCtgId: 30,
    datasetName: "flye",
    ctgName: "Ctg30",
    originId: "contig_98",
    overallLen: 2200,
    start: 2200,
    end: 1,
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: draftId,
      field: "ctg",
      value: "Gap",
    },
    createDeps(),
  );
  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[1], {
    segmentId: "seg-2",
    type: "gap",
    gapSizeBp: 100,
  });
});

test("updateFinalPathRow swaps start and end when orient changes", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 100,
            end: 300,
          },
        ],
      },
    },
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: "seg-1",
      field: "orient",
      value: "-",
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[0], {
    segmentId: "seg-1",
    type: "ctg",
    assemblyCtgId: 9,
    datasetName: "hifiasm",
    ctgName: "Ctg9",
    overallLen: 1200,
    start: 300,
    end: 100,
  });
});

test("updateFinalPathRow keeps the row unchanged when orient matches the current direction", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 300,
            end: 100,
          },
        ],
      },
    },
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: "seg-1",
      field: "orient",
      value: "-",
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[0], {
    segmentId: "seg-1",
    type: "ctg",
    assemblyCtgId: 9,
    datasetName: "hifiasm",
    ctgName: "Ctg9",
    overallLen: 1200,
    start: 300,
    end: 100,
  });
});

test("updateFinalPathRow toggles initial explicit negative orient back to forward", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            orient: "-",
            start: 1,
            end: 1200,
          },
        ],
      },
    },
  });

  await updateFinalPathRow(
    {},
    store,
    {
      segmentId: "seg-1",
      field: "orient",
      value: "+",
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments[0], {
    segmentId: "seg-1",
    type: "ctg",
    assemblyCtgId: 9,
    datasetName: "hifiasm",
    ctgName: "Ctg9",
    overallLen: 1200,
    start: 1,
    end: 1200,
  });
});

test("addFinalPathContigRelativeToSegment inserts a prompted ctg with forward full length", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
      },
    },
  });

  await addFinalPathContigRelativeToSegment(
    {},
    store,
    {
      segmentId: "seg-1",
      placement: "before",
    },
    createDeps({
      prompt() {
        return "30";
      },
    }),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-2",
      type: "ctg",
      assemblyCtgId: 30,
      datasetName: "flye",
      ctgName: "Ctg30",
      originId: "contig_98",
      overallLen: 2200,
      start: 1,
      end: 2200,
    },
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 9,
      datasetName: "hifiasm",
      ctgName: "Ctg9",
      overallLen: 1200,
      start: 1,
      end: 1200,
    },
  ]);
});

test("addFinalPathGapRelativeToSegment inserts a new gap even when the target side already has a gap", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
          {
            segmentId: "seg-2",
            type: "gap",
            gapSizeBp: 100,
          },
        ],
      },
    },
  });
  await addFinalPathGapRelativeToSegment(
    {},
    store,
    {
      segmentId: "seg-1",
      placement: "after",
    },
    createDeps(),
  );

  assert.deepEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments.map((segment) => segment.type),
    ["ctg", "gap", "gap"],
  );
  assert.notEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments[1].segmentId,
    store.getState().assembly.finalPathByChr.Chr01.segments[2].segmentId,
  );
});

test("addFinalPathGapRelativeToSegment keeps repeated gap insertions as independent segments", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
      },
    },
  });

  await addFinalPathGapRelativeToSegment(
    {},
    store,
    {
      segmentId: "seg-1",
      placement: "after",
    },
    createDeps(),
  );
  await addFinalPathGapRelativeToSegment(
    {},
    store,
    {
      segmentId: "seg-1",
      placement: "after",
    },
    createDeps(),
  );

  assert.deepEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments.map((segment) => segment.type),
    ["ctg", "gap", "gap"],
  );
  assert.notEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments[1].segmentId,
    store.getState().assembly.finalPathByChr.Chr01.segments[2].segmentId,
  );
});

test("addFinalPathGapRelativeToSegment preserves the current graph scroll position during rerender", async () => {
  const persisted = [];
  const store = createStore({
    finalPathTrackView: {
      minTickUnitKb: 10000,
      maxTickCount: 10,
    },
    finalPathTrackScrollState: {
      viewportKey: "7:Chr01:graph:10000:10",
      scrollLeft: 120,
    },
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
      },
    },
  });
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]" || selector === ".assembly-final-path-svg-wrap") {
        return { scrollLeft: 640 };
      }
      return null;
    },
  };

  await addFinalPathGapRelativeToSegment(
    host,
    store,
    {
      segmentId: "seg-1",
      placement: "after",
    },
    createDeps({
      async persistProjectAssemblyViewState(payload) {
        persisted.push(payload);
        return payload;
      },
    }),
  );

  assert.deepEqual(store.getState().assembly.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 640,
  });
  assert.deepEqual(persisted[0].finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 640,
  });
});

test("flipFinalPathSegment swaps ctg start and end", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 30,
            datasetName: "flye",
            ctgName: "Ctg30",
            overallLen: 2200,
            start: 50,
            end: 300,
          },
        ],
      },
    },
  });

  await flipFinalPathSegment(
    {},
    store,
    {
      segmentId: "seg-1",
    },
    createDeps(),
  );

  assert.deepEqual(store.getState().assembly.finalPathByChr.Chr01.segments, [
    {
      segmentId: "seg-1",
      type: "ctg",
      assemblyCtgId: 30,
      datasetName: "flye",
      ctgName: "Ctg30",
      overallLen: 2200,
      start: 300,
      end: 50,
    },
  ]);
});

test("moveFinalPathRow supports before/after placement and removeFinalPathRow keeps remaining order", async () => {
  const store = createStore({
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
          {
            segmentId: "seg-2",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-3",
            type: "ctg",
            assemblyCtgId: 30,
            datasetName: "flye",
            ctgName: "Ctg30",
            overallLen: 2200,
            start: 1,
            end: 2200,
          },
        ],
      },
    },
  });
  await moveFinalPathRow(
    {},
    store,
    {
      sourceSegmentId: "seg-1",
      targetSegmentId: "seg-2",
      placement: "after",
    },
    createDeps(),
  );
  assert.deepEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments.map((row) => row.segmentId),
    ["seg-2", "seg-1", "seg-3"],
  );

  await moveFinalPathRow(
    {},
    store,
    {
      sourceSegmentId: "seg-3",
      targetSegmentId: "seg-2",
      placement: "before",
    },
    createDeps(),
  );
  assert.deepEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments.map((row) => row.segmentId),
    ["seg-3", "seg-2", "seg-1"],
  );

  await removeFinalPathRow(
    {},
    store,
    {
      segmentId: "seg-1",
    },
    createDeps(),
  );
  assert.deepEqual(
    store.getState().assembly.finalPathByChr.Chr01.segments.map((row) => row.segmentId),
    ["seg-3", "seg-2"],
  );
});
