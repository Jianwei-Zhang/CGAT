import test from "node:test";
import assert from "node:assert/strict";

import { renderCurrentRoute } from "../router.js";
import { clearAssemblySessionCache } from "../assembly-session-cache.js";

function createRouteButton(route) {
  return {
    dataset: { route },
    classList: {
      active: false,
      toggle(_className, enabled) {
        this.active = Boolean(enabled);
      },
    },
  };
}

function createRouteHost() {
  let html = "";
  let renderCount = 0;
  return {
    childNodes: [],
    dataset: {},
    get innerHTML() {
      return html;
    },
    set innerHTML(value) {
      html = value;
      renderCount += 1;
      this.childNodes = [{ html: value, renderCount }];
    },
    get renderCount() {
      return renderCount;
    },
    replaceChildren(...nodes) {
      this.childNodes = nodes;
      html = nodes.map((node) => node.html || "").join("");
    },
    addEventListener() {},
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
}

function createRoot(routeHost) {
  const buttons = [
    createRouteButton("importer"),
    createRouteButton("workspace"),
    createRouteButton("assembly"),
    createRouteButton("projectExport"),
  ];
  return {
    querySelector(selector) {
      if (selector === "#route-host") {
        return routeHost;
      }
      return null;
    },
    querySelectorAll(selector) {
      return selector === ".route-button" ? buttons : [];
    },
  };
}

function createRoutableState(activeRoute) {
  return {
    locale: "en",
    activeRoute,
    session: {
      workspacePath: "D:/ws",
      projectName: "project-a",
      projectId: 7,
    },
    initializer: {
      loading: false,
      optionsLoaded: true,
      optionsError: "",
      references: [],
      datasets: [],
      existingProjects: [],
      selectedReferenceId: "",
      selectedPrimaryDatasetId: "",
      selectedSupportDatasetIds: [],
      projectNameInput: "",
      chrAssignmentMinCoveragePercentInput: "60",
      createModalOpen: false,
      autoPipelineModalOpen: false,
      autoPipelineRunning: false,
      autoPipelineCanClose: true,
      autoPipelineSteps: [],
      creating: false,
      updating: false,
      summary: "",
    },
    assembly: {
      loading: false,
      bootstrapping: false,
      activeTab: "about",
      chromosomes: [{ chrName: "Chr01", ctgCount: 1, placedBp: 1000 }],
      selectedChrName: "Chr01",
      chrCtgs: [],
      refTrackMembers: [],
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
      selectedCtgId: null,
      ctgDetail: null,
      editCandidates: {
        moveTargetCtgs: [],
        addSeqCandidates: [],
      },
      trackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      finalPathTrackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
      },
      supportChrCtgs: [],
      supportMirroredCtgs: [],
      finalPathByChr: {},
      finalPathViewMode: "graph",
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      trackScrollState: {
        viewportKey: "",
        scrollLeft: 0,
      },
      subviewTrackScrollState: {
        viewportKey: "",
        scrollLeft: 0,
      },
      finalPathTrackScrollState: {
        viewportKey: "",
        scrollLeft: 0,
      },
      subview: {
        mode: "2-contig",
        selectedAContigId: null,
        selectedARole: "",
        selectedBContigId: null,
        selectedBRole: "",
        message: "",
        error: "",
        summary: null,
      },
      error: "",
    },
  };
}

test("router fallback renders english copy for missing route", () => {
  const routeHost = { innerHTML: "" };
  const root = {
    querySelector(selector) {
      if (selector === "#route-host") {
        return routeHost;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const store = {
    getState() {
      return {
        locale: "en",
        activeRoute: "unknown-route",
        session: {
          workspacePath: "",
          projectName: "",
          projectId: null,
        },
      };
    },
  };

  renderCurrentRoute(root, store);

  assert.match(routeHost.innerHTML, /Page not found: unknown-route/);
});

test("router restores cached assembly DOM when returning to the same project", () => {
  clearAssemblySessionCache();
  const previousWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
  };
  let state = createRoutableState("assembly");
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const routeHost = createRouteHost();
  const root = createRoot(routeHost);

  try {
    renderCurrentRoute(root, store);
    const firstAssemblyNode = routeHost.childNodes[0];

    state = createRoutableState("workspace");
    renderCurrentRoute(root, store);
    assert.notEqual(routeHost.childNodes[0], firstAssemblyNode);

    state = createRoutableState("assembly");
    renderCurrentRoute(root, store);

    assert.equal(routeHost.childNodes[0], firstAssemblyNode);
    assert.equal(routeHost.renderCount, 2);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("router renders fresh assembly DOM for a newly rebuilt route host", () => {
  clearAssemblySessionCache();
  const previousWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
  };
  let state = createRoutableState("assembly");
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const originalHost = createRouteHost();
  const originalRoot = createRoot(originalHost);

  try {
    renderCurrentRoute(originalRoot, store);
    const cachedAssemblyNode = originalHost.childNodes[0];

    state = createRoutableState("workspace");
    renderCurrentRoute(originalRoot, store);

    state = createRoutableState("assembly");
    const rebuiltHost = createRouteHost();
    const rebuiltRoot = createRoot(rebuiltHost);
    renderCurrentRoute(rebuiltRoot, store);

    assert.notEqual(rebuiltHost.childNodes[0], cachedAssemblyNode);
    assert.equal(rebuiltHost.renderCount, 1);
    assert.equal(rebuiltHost.dataset.route, "assembly");
  } finally {
    globalThis.window = previousWindow;
  }
});

test("router skips cached assembly DOM when project export requests chr jump scroll", () => {
  clearAssemblySessionCache();
  const previousWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
  };
  let state = createRoutableState("assembly");
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const routeHost = createRouteHost();
  const root = createRoot(routeHost);

  try {
    renderCurrentRoute(root, store);
    const cachedAssemblyNode = routeHost.childNodes[0];

    state = createRoutableState("projectExport");
    renderCurrentRoute(root, store);

    state = {
      ...createRoutableState("assembly"),
      assembly: {
        ...createRoutableState("assembly").assembly,
        projectExportScrollToBottom: true,
      },
    };
    renderCurrentRoute(root, store);

    assert.notEqual(routeHost.childNodes[0], cachedAssemblyNode);
    assert.equal(routeHost.renderCount, 3);
  } finally {
    globalThis.window = previousWindow;
  }
});
