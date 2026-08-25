import test from "node:test";
import assert from "node:assert/strict";

import { createPhasedTrackController } from "../phased-track-controller.js";

function createTrack(id, key) {
  return {
    phasedTrackId: id,
    displayOrder: id,
    haplotypeKey: key,
    label: `Chr01${key}`,
    items: [],
  };
}

function createStore(phasedChrTracks = []) {
  let state = {
    locale: "zh",
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      selectedChrName: "Chr01",
      chrCtgs: [],
      phasedChrTracks,
      isChrPhased: phasedChrTracks.length > 0,
      activePhasedTrackKey: phasedChrTracks[0]?.haplotypeKey || "",
      activePhasedTrackKeyByChr: {},
    },
  };
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = { ...state, ...nextState };
    },
  };
}

function createController({ tracksAfter, createError = null, notices }) {
  return createPhasedTrackController({
    addCtgToPhasedChrTrack: async () => ({}),
    createPhasedChrTrack: async () => {
      if (createError) {
        throw createError;
      }
    },
    deletePhasedChrTrack: async () => ({}),
    listPhasedChrTracks: async () => ({ tracks: tracksAfter }),
    mapAssemblyError: () => ({ userMessage: "创建失败" }),
    persistMainTrackViewState: async () => {},
    persistTrackDragOffsets: async () => {},
    removePhasedChrTrackItem: async () => ({}),
    requestAssemblyNotice: (_host, _store, options) => {
      notices.push(options);
      return Promise.resolve(true);
    },
    rerenderAssemblyMainTab: () => {},
    setAssemblyActionFeedbackInMainTab: () => {},
  });
}

test("first successful phased track creation explains how to restore GRT results", async () => {
  const notices = [];
  const controller = createController({
    tracksAfter: [createTrack(1, "A")],
    notices,
  });

  await controller.createPhasedChrTrack({}, createStore());

  assert.deepEqual(notices, [{
    title: "GRT 结果暂不可用",
    message: "分型轨道暂不支持显示 GRT 预计算结果。关闭所有分型轨道后，即可恢复 GRT 结果。",
    confirmLabel: "我知道了",
  }]);
});

test("adding another phased track does not repeat the GRT notice", async () => {
  const notices = [];
  const existingTrack = createTrack(1, "A");
  const controller = createController({
    tracksAfter: [existingTrack, createTrack(2, "B")],
    notices,
  });

  await controller.createPhasedChrTrack({}, createStore([existingTrack]));

  assert.deepEqual(notices, []);
});

test("failed phased track creation does not show the GRT notice", async () => {
  const notices = [];
  const controller = createController({
    tracksAfter: [],
    createError: new Error("backend failed"),
    notices,
  });

  await controller.createPhasedChrTrack({}, createStore());

  assert.deepEqual(notices, []);
});

test("closing all phased tracks allows the next first-track notice to appear again", async () => {
  const notices = [];
  const existingTrack = createTrack(1, "A");
  const store = createStore([existingTrack]);
  store.setState({
    assembly: {
      ...store.getState().assembly,
      phasedChrTracks: [],
      isChrPhased: false,
      activePhasedTrackKey: "",
    },
  });
  const controller = createController({
    tracksAfter: [createTrack(2, "A")],
    notices,
  });

  await controller.createPhasedChrTrack({}, store);

  assert.equal(notices.length, 1);
});
