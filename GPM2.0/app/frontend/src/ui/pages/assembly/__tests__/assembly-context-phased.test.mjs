import {
  test,
  assert,
  addCtgToPhasedChrTrack,
  createPhasedChrTrack,
  initializeProject,
  updateProject,
  __testBuildAssemblyContextMenuItems,
  __testBindAssemblyContextMenu,
  __testCreatePhasedChrTrack,
  __testInheritPrimaryTrackDragOffsetForPhasedItem,
  __testRemovePhasedTrackItem,
  __testCompactFinalPathByDeletedPhasedTrack,
  __testSetSelectedPrimaryTrackCtgsHidden,
  __testResolveTrackContigClickAction,
  __testToggleSupportTrackCtgMirror,
  renderAssemblyPage,
  createState,
  createStore,
} from "./tabs-semantics-harness.mjs";

test("track click intent uses selectCtg by default and reserves Ctrl/Cmd for subview selection", () => {
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "primary", contigId: 8 }),
    { type: "select-ctg", contigId: 8 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "support", contigId: 30 }),
    { type: "select-ctg", contigId: 30 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "primary", contigId: 8, ctrlKey: true }),
    { type: "select-subview-candidate", trackRole: "primary", contigId: 8 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "phased", contigId: 2, ctrlKey: true }),
    { type: "select-subview-candidate", trackRole: "phased", contigId: 2 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "support", contigId: 30, metaKey: true }),
    { type: "select-subview-candidate", trackRole: "support", contigId: 30 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "other", contigId: 30 }),
    { type: "noop" },
  );
});

test("assembly rendering marks box-selected track ctgs with multi-selected class", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        trackSelectedCtgIds: [8, 30],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /track-ctg-group is-multi-selected is-companion/);
  assert.match(html, /track-ctg-group is-active is-multi-selected/);
  assert.match(html, /class="track-ctg is-multi-selected is-companion"/);
});

test("context menu opens for track contig glyphs and legacy ctg nodes", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const trackTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return {
          getAttribute(name) {
            if (name === "data-track-contig-id") return "30";
            if (name === "data-track-role") return "support";
            return null;
          },
        };
      }
      if (selector === "[data-assembly-ctg-id]") {
        return null;
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: trackTarget,
    clientX: 12,
    clientY: 34,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.match(menuState.innerHTML, /翻转 contig/);
  assert.match(menuState.innerHTML, /重命名 contig/);
  assert.match(menuState.innerHTML, /镜像 contig/);
  assert.doesNotMatch(menuState.innerHTML, /撤销镜像 contig/);
  assert.doesNotMatch(menuState.innerHTML, /隐藏 contig/);
  assert.doesNotMatch(menuState.innerHTML, /解除隐藏 contig/);
  assert.doesNotMatch(menuState.innerHTML, /删除 contig/);
  assert.doesNotMatch(menuState.innerHTML, /查看\/编辑成员/);
  assert.doesNotMatch(menuState.innerHTML, /更多 contig 操作/);
  assert.doesNotMatch(menuState.innerHTML, /移动锚点/);
  assert.doesNotMatch(menuState.innerHTML, /当前版本未接入/);
});

test("primary track context menu toggles hide/unhide contig label by hidden state", () => {
  const host = {};
  const visibleStore = createStore(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [],
      },
    }),
  );
  const hiddenStore = createStore(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );

  const visibleItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: "primary" },
    deletedCtgContext: null,
    memberNode: null,
    store: visibleStore,
    host,
  });
  const hiddenItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: "primary" },
    deletedCtgContext: null,
    memberNode: null,
    store: hiddenStore,
    host,
  });

  assert.ok(visibleItems.some((item) => item.label === "隐藏 contig"));
  assert.ok(visibleItems.every((item) => item.label !== "解除隐藏 contig"));
  assert.ok(hiddenItems.some((item) => item.label === "解除隐藏 contig"));
  assert.ok(hiddenItems.every((item) => item.label !== "隐藏 contig"));
});

test("support track context menu exposes mirror toggle and mirror bar keeps only unmirror action", () => {
  const host = {};
  const store = createStore(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 22,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 30,
            name: "support-a",
            totalLength: 10_000_000,
            anchorStart: 100,
            lengthBp: 10_000_000,
            startBp: 0,
            endBp: 9_999_999,
            laneIndex: 0,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const supportItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  }).map((item) => item.label);
  const mirrorItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: true },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  }).map((item) => item.label);

  assert.ok(supportItems.includes("翻转 contig"));
  assert.ok(supportItems.includes("重命名 contig..."));
  assert.ok(supportItems.includes("追加到路径"));
  assert.ok(supportItems.includes("撤销镜像 contig"));
  assert.deepEqual(mirrorItems, ["追加到路径", "撤销镜像 contig"]);
});

test("phased mode primary contig context menu offers per-haplotype add and append actions", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: "primary", datasetId: null, isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      async addTrackContigToPhasedTrack(_host, _store, payload) {
        calls.push({ type: "add", payload });
      },
      async appendTrackContigToFinalPath(_host, _store, ctgContext, options) {
        calls.push({ type: "append", ctgContext, options });
      },
    },
  });
  const labels = items.map((item) => item.label);

  assert.deepEqual(
    labels.filter((label) => label.startsWith("添加到 ") || label.startsWith("追加到路径 ")),
    ["添加到 A", "添加到 B", "追加到路径 A", "追加到路径 B"],
  );
  assert.equal(labels.includes("追加到路径"), false);

  await items.find((item) => item.label === "添加到 B").run();
  await items.find((item) => item.label === "追加到路径 B").run();

  assert.deepEqual(calls, [
    {
      type: "add",
      payload: {
        phasedTrackId: 102,
        haplotypeKey: "B",
        label: "Chr01B",
        assemblyCtgId: 2,
      },
    },
    {
      type: "append",
      ctgContext: { assemblyCtgId: 2, trackRole: "primary", datasetId: null, isMirror: false },
      options: {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    },
  ]);
});

test("phased mode support contig context menu offers grouped per-haplotype append actions", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      async addTrackContigToPhasedTrack(_host, _store, payload) {
        calls.push({ type: "add", payload });
      },
      async appendTrackContigToFinalPath(_host, _store, ctgContext, options) {
        calls.push({ type: "append", ctgContext, options });
      },
    },
  });
  const labels = items.map((item) => item.label);

  assert.deepEqual(
    labels.filter((label) => label.startsWith("追加到路径 ")),
    ["追加到路径 A", "追加到路径 B"],
  );
  assert.equal(labels.some((label) => label.startsWith("添加到 ")), false);
  assert.equal(labels.includes("追加到路径"), false);

  await items.find((item) => item.label === "追加到路径 B").run();

  assert.deepEqual(calls, [
    {
      type: "append",
      ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: false },
      options: {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    },
  ]);
});

test("creating a phased track refreshes only the main assembly card", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};
    const created = await initializeProject({
      workspaceRoot: "/tmp/workspace",
      projectName: `project-phased-local-refresh-${Date.now()}`,
    });
    await updateProject({
      workspaceRoot: "/tmp/workspace",
      projectId: created.projectId,
      projectName: created.projectName,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: created.supportDatasetIds,
      chrAssignmentMinCoveragePercent: 60,
      phasedAssemblyEnabled: true,
      stateOrLocale: { locale: "en" },
    });
    const store = createStore(createState({
      session: {
        workspacePath: "/tmp/workspace",
        projectId: created.projectId,
      },
      assembly: {
        selectedChrName: "Chr01",
        phasedChrTracks: [],
      },
    }));
    let fullPageRenderCount = 0;
    let replacedCount = 0;
    const makeNode = () => ({
      addEventListener() {},
      querySelector() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
      replaceWith() {
        replacedCount += 1;
      },
    });
    const currentSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const nextSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const fakeDocument = {
      createElement(tagName) {
        assert.equal(tagName, "template");
        return {
          set innerHTML(_value) {},
          content: {
            querySelector(selector) {
              return nextSections.get(selector) || null;
            },
          },
        };
      },
      querySelector() {
        return null;
      },
      contains(node) {
        return node === routeHost;
      },
    };
    const routeHost = {
      id: "route-host",
      isConnected: true,
      ownerDocument: fakeDocument,
      matches(selector) {
        return selector === "#route-host";
      },
      closest(selector) {
        return selector === "#route-host" ? this : null;
      },
      querySelector(selector) {
        return currentSections.get(selector) || null;
      },
      querySelectorAll() {
        return [];
      },
      addEventListener() {},
      set innerHTML(_value) {
        fullPageRenderCount += 1;
      },
    };

    await __testCreatePhasedChrTrack(routeHost, store);

    assert.equal(fullPageRenderCount, 0);
    assert.ok(replacedCount >= 2, "expected main-card sections to be replaced");
    assert.equal(store.getState().assembly.phasedChrTracks[0]?.haplotypeKey, "A");
  } finally {
    globalThis.window = previousWindow || {};
  }
});

test("phased track item context menu appends, flips, and removes only that phased instance", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(createState({
    assembly: {
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
      ],
    },
  }));
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: {
      assemblyCtgId: 2,
      trackRole: "phased",
      datasetId: null,
      isMirror: false,
      phasedTrackId: 101,
      phasedTrackItemId: 9001,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      async appendTrackContigToFinalPath(_host, _store, ctgContext, options) {
        calls.push({ type: "append", ctgContext, options });
      },
      async applyEditorAction(_host, _store, payload) {
        calls.push({ type: "flip", payload });
      },
      async removePhasedTrackItem(_host, _store, payload) {
        calls.push({ type: "remove", payload });
      },
    },
  });

  assert.deepEqual(items.map((item) => item.label), ["追加到路径 A", "追加到路径 B", "翻转 contig", "从该分型组删除"]);
  await items[1].run();
  await items[2].run();
  await items[3].run();
  assert.deepEqual(calls, [
    {
      type: "append",
      ctgContext: {
        assemblyCtgId: 2,
        trackRole: "phased",
        datasetId: null,
        isMirror: false,
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        phasedHaplotypeKey: "A",
      },
      options: {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    },
    {
      type: "flip",
      payload: {
        action: "flip-ctg",
        args: { assemblyCtgId: 2, phasedTrackItemId: 9001 },
        keepCurrentCtg: true,
        localRefresh: true,
        phasedOnlyRefresh: true,
      },
    },
    {
      type: "remove",
      payload: { phasedTrackItemId: 9001 },
    },
  ]);
});

test("phased track item orientation is isolated from the main track ctg orientation", () => {
  const buildHtml = ({ primaryOrient, hitStart, hitEnd }) => renderAssemblyPage(createState({
    initializer: {
      datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
    assembly: {
      activeHitsTrackKey: "A",
      supportDatasetId: null,
      supportChrCtgs: [],
      phasedChrTracks: [
        {
          phasedTrackId: 101,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 92, displayOrder: 1, orient: "+" }],
        },
      ],
      chrCtgs: [
        {
          assemblyCtgId: 92,
          name: "contig_92",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 600_000,
          anchorStart: 500,
          orient: primaryOrient,
          refOrient: primaryOrient,
          hits: [
            {
              refStart: 100_000,
              refEnd: 190_000,
              ctgStart: hitStart,
              ctgEnd: hitEnd,
              blockLength: 90_001,
              mapq: 60,
              strand: "+",
            },
          ],
        },
      ],
    },
  }));
  const extractPhasedBandPoints = (html) => {
    const match = html.match(
      /<polygon class="track-collinearity-band is-phased-track"[^>]*data-band-track-role="phased"[^>]*data-band-contig-id="92"[^>]*points="([^"]+)"/,
    );
    assert.ok(match, "expected phased track hit band");
    return match[1];
  };

  const plusHtml = buildHtml({ primaryOrient: "+", hitStart: 100_000, hitEnd: 190_000 });
  const html = buildHtml({ primaryOrient: "-", hitStart: 410_001, hitEnd: 500_001 });

  assert.match(
    html,
    /<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="92"[^>]*data-track-role="primary"[^>]*data-track-ref-orient="-"/,
  );
  assert.match(
    html,
    /<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="92"[^>]*data-track-role="phased"[^>]*data-track-ref-orient="\+"[^>]*data-track-phased-track-item-id="9001"/,
  );
  assert.match(html, />contig_92 \(-\)<\/text>/);
  assert.match(html, />contig_92 \(\+\)<\/text>/);
  assert.equal(extractPhasedBandPoints(html), extractPhasedBandPoints(plusHtml));
});

test("adding a dragged primary ctg to a phased track inherits the current visual offset", () => {
  const store = createStore(createState({
    assembly: {
      trackDragOffsets: [
        { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
      ],
    },
  }));

  const changed = __testInheritPrimaryTrackDragOffsetForPhasedItem(store, {
    assemblyCtgId: 8,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
  });

  assert.equal(changed, true);
  assert.deepEqual(store.getState().assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
    {
      trackRole: "phased",
      assemblyCtgId: 8,
      phasedTrackId: 101,
      phasedTrackItemId: 9001,
      offsetBp: 1200,
    },
  ]);
});

test("adding an undragged primary ctg to a phased track leaves phased offsets unchanged", () => {
  const store = createStore(createState({
    assembly: {
      trackDragOffsets: [
        { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
      ],
    },
  }));

  const changed = __testInheritPrimaryTrackDragOffsetForPhasedItem(store, {
    assemblyCtgId: 2,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
  });

  assert.equal(changed, false);
  assert.deepEqual(store.getState().assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
  ]);
});

test("removing a phased track item refreshes only the main assembly card", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};
    const created = await initializeProject({
      workspaceRoot: "/tmp/workspace",
      projectName: `project-phased-remove-local-refresh-${Date.now()}`,
    });
    await updateProject({
      workspaceRoot: "/tmp/workspace",
      projectId: created.projectId,
      projectName: created.projectName,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: created.supportDatasetIds,
      chrAssignmentMinCoveragePercent: 60,
      phasedAssemblyEnabled: true,
      stateOrLocale: { locale: "en" },
    });
    const createdTrack = await createPhasedChrTrack({
      workspaceRoot: "/tmp/workspace",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    const added = await addCtgToPhasedChrTrack({
      workspaceRoot: "/tmp/workspace",
      projectId: created.projectId,
      phasedTrackId: createdTrack.track.phasedTrackId,
      assemblyCtgId: 2,
    });
    const store = createStore(createState({
      session: {
        workspacePath: "/tmp/workspace",
        projectId: created.projectId,
      },
      assembly: {
        selectedChrName: "Chr01",
        phasedChrTracks: [
          {
            ...createdTrack.track,
            items: [added.item],
          },
        ],
        isChrPhased: true,
        activePhasedTrackKey: "A",
      },
    }));
    let fullPageRenderCount = 0;
    let replacedCount = 0;
    const makeNode = () => ({
      addEventListener() {},
      querySelector() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
      replaceWith() {
        replacedCount += 1;
      },
    });
    const currentSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const nextSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const fakeDocument = {
      createElement(tagName) {
        assert.equal(tagName, "template");
        return {
          set innerHTML(_value) {},
          content: {
            querySelector(selector) {
              return nextSections.get(selector) || null;
            },
          },
        };
      },
      querySelector() {
        return null;
      },
      contains(node) {
        return node === routeHost;
      },
    };
    const routeHost = {
      id: "route-host",
      isConnected: true,
      ownerDocument: fakeDocument,
      matches(selector) {
        return selector === "#route-host";
      },
      closest(selector) {
        return selector === "#route-host" ? this : null;
      },
      querySelector(selector) {
        return currentSections.get(selector) || null;
      },
      querySelectorAll() {
        return [];
      },
      addEventListener() {},
      set innerHTML(_value) {
        fullPageRenderCount += 1;
      },
    };

    await __testRemovePhasedTrackItem(routeHost, store, { phasedTrackItemId: added.item.itemId });

    assert.equal(fullPageRenderCount, 0);
    assert.ok(replacedCount >= 2, "expected main-card sections to be replaced");
    assert.equal(store.getState().assembly.phasedChrTracks[0]?.items.length, 0);
  } finally {
    globalThis.window = previousWindow || {};
  }
});

test("primary and phased track labels expose single-active hits toggles", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedChrName: "Chr01",
        activeHitsTrackKey: "primary",
        activeHitsTrackKeyByChr: { Chr01: "primary" },
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const actions = {
    setActiveHitsTrack(_host, _store, payload) {
      calls.push(payload);
    },
  };
  const primaryItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "primary", isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });
  const phasedItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "phased",
      isMirror: false,
      phasedTrackId: 101,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });

  assert.equal(primaryItems[0].label, "隐藏比对线");
  assert.equal(phasedItems[0].label, "显示比对线");

  await primaryItems[0].run();
  await phasedItems[0].run();

  assert.deepEqual(calls, [{ trackKey: "" }, { trackKey: "A" }]);
});

test("ds-backed track label context menu exposes add new ctg with clicked target", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        selectedChrName: "Chr01",
      },
    }),
  );
  const calls = [];
  const primaryItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "primary", isMirror: false, datasetId: 11 },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      importAddCtgIntoTrack(_host, _store, payload) {
        calls.push(payload);
      },
    },
  });
  const supportItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "support", isMirror: false, datasetId: 22 },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      importAddCtgIntoTrack(_host, _store, payload) {
        calls.push(payload);
      },
    },
  });

  const primaryAdd = primaryItems.find((item) => item.label === "添加新 ctg...");
  const supportAdd = supportItems.find((item) => item.label === "添加新 ctg...");
  assert.ok(primaryAdd, "expected primary add new ctg menu item");
  assert.ok(supportAdd, "expected support add new ctg menu item");
  await primaryAdd.run();
  await supportAdd.run();
  assert.deepEqual(calls, [
    { targetChr: "Chr01", targetTrack: "hifiasm", datasetId: 11, trackRole: "primary" },
    { targetChr: "Chr01", targetTrack: "flye", datasetId: 22, trackRole: "support" },
  ]);
});

test("phased and mirror track labels do not expose direct add new ctg", () => {
  const store = createStore(
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        selectedChrName: "Chr01",
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        ],
      },
    }),
  );
  const host = { closest: () => null };
  const phasedItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "phased",
      isMirror: false,
      phasedTrackId: 101,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  });
  const mirrorItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "support", isMirror: true, datasetId: 22 },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  });
  assert.equal(phasedItems.some((item) => item.label === "添加新 ctg..."), false);
  assert.equal(mirrorItems.some((item) => item.label === "添加新 ctg..."), false);
});

test("phased track label context menu exposes delete track action", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedChrName: "Chr01",
        activeHitsTrackKey: "primary",
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "phased",
      isMirror: false,
      phasedTrackId: 101,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      deletePhasedTrack(_host, _store, payload) {
        calls.push(payload);
      },
      confirm() {
        return true;
      },
    },
  });

  const deleteItem = items.find((item) => /删除.*分型轨道/.test(item.label));
  assert.ok(deleteItem, "expected phased track delete menu item");
  await deleteItem.run();
  assert.deepEqual(calls, [{ phasedTrackId: 101, haplotypeKey: "A" }]);
});

test("deleting a phased track compacts final path keys with track labels", () => {
  const nextFinalPathByChr = __testCompactFinalPathByDeletedPhasedTrack(
    {
      Chr01A: { chrName: "Chr01A", segments: [{ segmentId: "a" }] },
      Chr01B: { chrName: "Chr01B", segments: [{ segmentId: "b" }] },
      Chr01C: { chrName: "Chr01C", segments: [{ segmentId: "c" }] },
      Chr02: { chrName: "Chr02", segments: [{ segmentId: "ordinary" }] },
    },
    {
      parentChrName: "Chr01",
      deletedPhasedTrackId: 102,
      tracksBefore: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", displayOrder: 2 },
        { phasedTrackId: 103, haplotypeKey: "C", label: "Chr01C", displayOrder: 3 },
      ],
    },
  );

  assert.deepEqual(Object.keys(nextFinalPathByChr).sort(), ["Chr01A", "Chr01B", "Chr02"]);
  assert.deepEqual(nextFinalPathByChr.Chr01B, {
    chrName: "Chr01B",
    segments: [{ segmentId: "c" }],
  });
  assert.deepEqual(nextFinalPathByChr.Chr02, {
    chrName: "Chr02",
    segments: [{ segmentId: "ordinary" }],
  });
});

test("toggling support mirror persists project-scoped mirrored ctgs", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
    },
    assembly: {
      selectedChrName: "Chr01",
      supportDatasetId: 22,
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              assemblyCtgId: 8,
              datasetName: "",
              ctgName: "ctg-primary",
              overallLen: 500,
              start: 1,
              end: 500,
            },
          ],
          updatedAt: "1",
        },
      },
      chrCtgs: [
        { assemblyCtgId: 8, name: "ctg-primary", totalLength: 500, anchorStart: 0, startBp: 0, endBp: 499 },
      ],
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "ctg-mirror", totalLength: 300, anchorStart: 320, startBp: 0, endBp: 299, laneIndex: 0 },
      ],
      supportMirroredCtgs: [],
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });
  const store = {
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
  const persisted = [];

  await __testToggleSupportTrackCtgMirror(
    host,
    store,
    {
      datasetId: 22,
      assemblyCtgId: 30,
      shouldMirror: true,
    },
    {
      async persistProjectAssemblyViewState(payload) {
        persisted.push(payload);
      },
    },
  );

  assert.equal(store.getState().assembly.supportMirroredCtgs.length, 1);
  assert.deepEqual(persisted, [
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: 22,
      trackView: store.getState().assembly.trackView,
      supportDsCtgLenRulesByChr: {},
      supportMirroredCtgs: store.getState().assembly.supportMirroredCtgs,
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: store.getState().assembly.finalPathByChr,
      degapProjectState: {},
    },
  ]);
});

test("batch hide and unhide force selected primary contigs to target hidden state", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      session: {
        workspacePath: "/tmp/ws",
        projectId: 7,
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 8,
                datasetName: "",
                ctgName: "ctg-beta",
                overallLen: 600,
                start: 1,
                end: 600,
              },
            ],
            updatedAt: "1",
          },
        },
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );
  const persisted = [];

  await __testSetSelectedPrimaryTrackCtgsHidden(host, store, [2, 8], true, {
    async persistProjectAssemblyViewState(payload) {
      persisted.push(payload);
    },
  });
  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, [2, 8]);
  const hiddenFinalPathByChr = persisted[0].finalPathByChr;

  await __testSetSelectedPrimaryTrackCtgsHidden(host, store, [2, 8], false, {
    async persistProjectAssemblyViewState(payload) {
      persisted.push(payload);
    },
  });
  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, []);
  assert.deepEqual(persisted, [
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: null,
      trackView: store.getState().assembly.trackView,
      supportDsCtgLenRulesByChr: {},
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [2, 8],
      hiddenPrimaryCtgIdsByChr: { Chr01: [2, 8] },
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: hiddenFinalPathByChr,
      degapProjectState: {},
    },
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: null,
      trackView: store.getState().assembly.trackView,
      supportDsCtgLenRulesByChr: {},
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: store.getState().assembly.finalPathByChr,
      degapProjectState: {},
    },
  ]);
});
