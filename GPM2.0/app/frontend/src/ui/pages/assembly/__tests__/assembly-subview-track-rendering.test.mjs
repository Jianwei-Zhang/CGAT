import {
  test,
  assert,
  __testBuildAssemblyContextMenuItems,
  __testRerenderSubviewPanel,
  __testToggleSubviewContigFlip,
  renderAssemblyPage,
  createState,
  createStore,
} from "./tabs-semantics-harness.mjs";

test("subview panel renders chart sub-card with parameter labels after entering", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-ctg" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /<h4>Subview<\/h4>/);
  assert.match(
    html,
    /Ctrl\/Cmd 选中任意两个ctg进入subview-ctg；也支持点击任意两个轨道名进入subview-track。/,
  );
  assert.match(html, /support-ctg vs ctg-alpha/);
  assert.match(html, /data-subview-remove-type="candidate"/);
  assert.match(html, /data-subview-remove-role="support"/);
  assert.match(html, /data-subview-remove-contig-id="30"/);
  assert.match(html, /最小刻度单位\(kb\)/);
  assert.match(html, /最多可展示数/);
  assert.match(html, /比对长度\(bp\)/);
  assert.match(html, /MAPQ/);
  assert.match(html, /id="subview-track-min-tick-unit-kb"/);
  assert.match(html, /id="subview-track-max-tick-count"/);
  assert.match(html, /id="subview-track-alignment-length"/);
  assert.match(html, /id="subview-track-mapq"/);
  assert.match(html, /class="assembly-track-layout subview-track-layout"/);
  assert.doesNotMatch(html, /规则：/);
  assert.doesNotMatch(html, /上轨：/);
  assert.doesNotMatch(html, /下轨：/);
  assert.doesNotMatch(html, /命中：/);
  assert.match(html, /support-ctg/);
  assert.match(html, /ctg-alpha/);
});

test("schema 3 renders local GRT evidence in contig-pair and track-pair Subviews", () => {
  const supportSegment = {
    segmentId: "support-segment",
    type: "ctg",
    assemblyCtgId: 30,
    assemblySourceStart: 1,
    assemblySourceEnd: 300,
    datasetName: "flye",
    ctgName: "support-ctg",
    overallLen: 300,
    orient: "+",
    start: 1,
    end: 300,
    source: { dataset: "flye", contig: "support-ctg", start: 1, end: 300, orientation: "+" },
  };
  const primarySegment = {
    segmentId: "primary-segment",
    type: "ctg",
    assemblyCtgId: 2,
    assemblySourceStart: 1,
    assemblySourceEnd: 1200,
    datasetName: "hifiasm",
    ctgName: "ctg-alpha",
    overallLen: 1200,
    orient: "+",
    start: 1,
    end: 1200,
    source: { dataset: "hifiasm", contig: "ctg-alpha", start: 1, end: 1200, orientation: "+" },
  };
  const baseline = {
    mode: "segments",
    chrName: "Chr01",
    grtDisplayAvailable: true,
    segments: [supportSegment, primarySegment],
    displayEvidence: [{
      evidenceId: "grt-display-local-integration",
      tool: "mummer",
      role: "left_anchor",
      association: "supporting_precursor",
      alignedLength: 100,
      identity: 0.999,
      mapq: null,
      source: {
        assemblyCtgId: 30,
        assemblySourceStart: 1,
        assemblySourceEnd: 300,
        start: 101,
        end: 200,
        orientation: "+",
      },
      target: {
        assemblyCtgId: 2,
        assemblySourceStart: 1,
        assemblySourceEnd: 1200,
        start: 401,
        end: 500,
        orientation: "+",
      },
    }],
  };
  const commonAssembly = {
    isChrPhased: false,
    supportDatasetId: 22,
    supportChrCtgs: [
      { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
    ],
    finalPathByChr: { Chr01: structuredClone(baseline) },
    grtProjectView: {
      recipe: { finalPathSchemaVersion: "3" },
      baselineFinalPathByChr: { Chr01: baseline },
      sourceCards: [],
      verification: {},
    },
    grtResultDisplayByChr: { Chr01: { main: false, subview: true } },
  };
  const initializer = {
    datasets: [
      { datasetId: 11, name: "hifiasm", label: "hifiasm" },
      { datasetId: 22, name: "flye", label: "flye" },
    ],
    existingProjects: [
      { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
    ],
  };
  const contigPairHtml = renderAssemblyPage(createState({
    assembly: {
      ...commonAssembly,
      subview: {
        mode: "2-contig",
        selectedAContigId: 2,
        selectedARole: "primary",
        selectedBContigId: 30,
        selectedBRole: "support",
        summary: {
          mode: "2-contig",
          top: { contigId: 30, role: "support", contigName: "support-ctg" },
          bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
        },
      },
    },
    initializer,
  }));
  const trackPairHtml = renderAssemblyPage(createState({
    assembly: {
      ...commonAssembly,
      subview: {
        selectedTrackARole: "primary",
        selectedTrackBRole: "support",
        summary: {
          mode: "track-pair",
          topTrack: { role: "support" },
          bottomTrack: { role: "primary" },
        },
        trackPairHiddenCtgs: [],
      },
    },
    initializer,
  }));

  assert.match(contigPairHtml, /data-grt-display-evidence="grt-display-local-integration"/);
  assert.match(trackPairHtml, /data-grt-display-evidence="grt-display-local-integration"/);
  assert.match(trackPairHtml, /grt-display-evidence-band is-mummer is-supporting-precursor/);
});

test("subview track-pair mode renders only mirror support ctg containers when support track source is mirror", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-mother", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "wtdbg2",
            chrName: "Chr01",
            assemblyCtgId: 330,
            name: "support-mirror-only",
            totalLength: 350,
            anchorStart: 360,
            lengthBp: 350,
            startBp: 0,
            endBp: 349,
            laneIndex: 0,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          selectedTrackBDatasetId: 33,
          selectedTrackBIsMirror: true,
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", datasetId: 33, isMirror: true },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
          { datasetId: 33, name: "wtdbg2", label: "wtdbg2" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] },
        ],
      },
    }),
  );

  assert.match(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="330"/);
  assert.doesNotMatch(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="30"/);
  assert.match(html, /class="subview-candidate-badge"[^>]*><strong class="subview-candidate-slot">T1<\/strong><span class="subview-candidate-content"><span class="subview-candidate-name">/);
  assert.match(html, /class="subview-candidate-badge"[^>]*><strong class="subview-candidate-slot">T2<\/strong><span class="subview-candidate-content"><span class="subview-candidate-name">/);
  assert.match(html, /data-subview-remove-type="track"[^>]*><svg class="subview-candidate-remove-icon"[^>]*>/);
});

test("subview track-pair mother support does not include mirror ctgs from other datasets", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "canu2-mother", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 1901,
            name: "flye-mirror-ctg1901",
            totalLength: 1481407,
            anchorStart: 0,
            lengthBp: 1481407,
            startBp: 0,
            endBp: 1481406,
            laneIndex: 0,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          selectedTrackBDatasetId: 22,
          selectedTrackBIsMirror: false,
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "canu2", label: "canu2" },
          { datasetId: 33, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] },
        ],
      },
    }),
  );

  assert.match(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="30"/);
  assert.doesNotMatch(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="1901"/);
});

test("subview track-pair support track skips deleted contigs inherited from main view", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-keep", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
          { assemblyCtgId: 31, name: "support-deleted", assignedChrName: "Chr01", memberCount: 1, totalLength: 280, anchorStart: 720 },
        ],
        deletedCtgs: [
          {
            deletedCtgRecordId: 9101,
            assemblyCtgId: 31,
            name: "support-deleted",
            memberCount: 1,
            totalLength: 280,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="30"/);
  assert.doesNotMatch(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="31"/);
});

test("subview track-pair mode renders both ds track labels and local delete context attrs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /主\(hifiasm\)/);
  assert.match(html, /辅\(flye\)/);
  assert.match(html, /data-subview-track-pair-role="support"/);
  assert.match(html, /data-subview-track-pair-contig-id="30"/);
  assert.match(html, /data-subview-track-pair-dataset-id="22"/);
  assert.match(html, /data-subview-track-pair-is-mirror="0"/);
  assert.match(html, /data-subview-remove-type="track"/);
  assert.doesNotMatch(html, /尚未选择候选 ctg/);
  assert.doesNotMatch(html, /轨道模式：/);
});

test("subview labels expose runtime lookup metadata in both 2-contig and track-pair modes", () => {
  const twoContigHtml = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-top", refOrient: "+", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "primary-bottom", refOrient: "-", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 100 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
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

  assert.match(twoContigHtml, /data-subview-label-slot="top"[^>]*data-subview-label-role="support"[^>]*data-subview-label-contig-id="30"[^>]*>support-top \(\+\)<\/text>/);
  assert.match(twoContigHtml, /data-subview-label-slot="bottom"[^>]*data-subview-label-role="primary"[^>]*data-subview-label-contig-id="2"[^>]*>primary-bottom \(-\)<\/text>/);

  const trackPairHtml = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-track", refOrient: "-", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "primary-track", refOrient: "+", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 100 },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
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

  assert.match(trackPairHtml, /data-subview-label-slot="top"[^>]*data-subview-label-role="support"[^>]*data-subview-label-contig-id="30"[^>]*>support-track \(-\)<\/text>/);
  assert.match(trackPairHtml, /data-subview-label-slot="bottom"[^>]*data-subview-label-role="primary"[^>]*data-subview-label-contig-id="2"[^>]*>primary-track \(\+\)<\/text>/);
});

test("subview track-pair strips chr suffix in labels and keeps full hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "Ctg1617@Chr22", refOrient: "-", assignedChrName: "Chr22", memberCount: 1, totalLength: 500_000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "ptg000009l@Chr22", refOrient: "+", assignedChrName: "Chr22", memberCount: 1, totalLength: 500_000, anchorStart: 100 },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
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

  assert.match(html, /data-subview-label-slot="top"[^>]*data-subview-label-role="support"[^>]*data-subview-label-contig-id="30"[^>]*>Ctg1617 \(-\)<\/text>/);
  assert.match(html, /data-subview-label-slot="bottom"[^>]*data-subview-label-role="primary"[^>]*data-subview-label-contig-id="2"[^>]*>ptg000009l \(\+\)<\/text>/);
  assert.match(html, /<title>Ctg1617@Chr22 \| start=/);
  assert.match(html, /<title>ptg000009l@Chr22 \| start=/);
  assert.doesNotMatch(html, /data-subview-label-slot="top"[^>]*>Ctg1617@Chr22 \(-\)<\/text>/);
  assert.doesNotMatch(html, /data-subview-label-slot="bottom"[^>]*>ptg000009l@Chr22 \(\+\)<\/text>/);
});

test("subview local contig flips only affect subview labels and leave main-view labels unchanged", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-track",
            refOrient: "+",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000,
            anchorStart: 100,
          },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 2,
          selectedBRole: "primary",
          flippedCtgs: [{ slot: "bottom", contigId: 2 }],
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "primary", contigName: "primary-track" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-track" },
          },
        },
      },
    }),
  );

  assert.match(html, /data-track-role="primary"[^>]*>[\s\S]*?primary-track \(\+\)<\/text>/);
  assert.match(html, /data-subview-label-slot="top"[^>]*>primary-track \(\+\)<\/text>/);
  assert.match(html, /data-subview-label-slot="bottom"[^>]*>primary-track \(-\)<\/text>/);
});

test("subview local contig flip refreshes only the subview panel", async () => {
  const store = createStore(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          flippedCtgs: [],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
    }),
  );
  const calls = [];

  await __testToggleSubviewContigFlip(
    {},
    store,
    { slot: "top", assemblyCtgId: 30 },
    {
      async persistProjectAssemblyViewStateFromStore() {},
      rerenderSubviewPanel(_host, currentStore) {
        calls.push(currentStore.getState().assembly.subview.flippedCtgs);
      },
    },
  );

  assert.deepEqual(store.getState().assembly.subview.flippedCtgs, [{ slot: "top", contigId: 30 }]);
  assert.deepEqual(calls, [[{ slot: "top", contigId: 30 }]]);
});

test("subview panel rerender uses track renderer deps so local flips paint immediately", () => {
  const store = createStore(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-track",
            refOrient: "+",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000,
            anchorStart: 100,
          },
        ],
        subview: {
          mode: "2-contig",
          flippedCtgs: [{ slot: "bottom", contigId: 2 }],
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "primary", contigName: "primary-track" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-track" },
          },
        },
      },
    }),
  );
  let renderedPanelHtml = "";
  let currentPanel = null;
  const fakeDoc = {
    contains(node) {
      return Boolean(node);
    },
    querySelector(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  const noopPanel = {
    ownerDocument: fakeDoc,
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  currentPanel = {
    ownerDocument: fakeDoc,
    set outerHTML(value) {
      renderedPanelHtml = String(value || "");
      currentPanel = noopPanel;
    },
  };
  const routeHost = {
    ownerDocument: fakeDoc,
    matches(selector) {
      return selector === "#route-host";
    },
    closest() {
      return null;
    },
    querySelector(selector) {
      return selector === "[data-subview-panel='1']" ? currentPanel : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };

  __testRerenderSubviewPanel(routeHost, store);

  assert.match(renderedPanelHtml, /data-subview-label-slot="bottom"[^>]*>primary-track \(-\)<\/text>/);
});

test("subview track-pair mode renders tooltip-enabled overlap bands and draggable track metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  assert.match(html, /class="subview-band-tooltip is-hidden"/);
  assert.match(html, /data-subview-band-tooltip-delay-ms="500"/);
  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 2,200-3,400 bp[^"]*primary-bottom: 2,400-3,600 bp/);
  assert.match(html, /class="track-band-canvas-layer"[^>]*data-track-band-canvas-scene-kind="subview-track-pair"/);
  assert.match(html, /<canvas class="track-band-canvas"[^>]*data-track-band-canvas="1"/);
  assert.match(html, /<polygon class="track-collinearity-band is-companion"[^>]*pointer-events="visibleFill"[^>]*data-track-band-proxy="1"/);
  assert.match(html, /<clipPath id="subview-track-band-clip"/);
  assert.match(html, /<g clip-path="url\(#subview-track-band-clip\)">[\s\S]*<polygon class="track-collinearity-band is-companion"[\s\S]*data-track-band-proxy="1"/);
  assert.match(html, /class="track-ctg subview-track-ctg[^"]*"[^>]*pointer-events="all"/);
  assert.match(html, /data-subview-track-slot="top"[^>]*data-subview-contig-id="30"/);
  assert.match(html, /data-subview-track-slot="bottom"[^>]*data-subview-contig-id="2"/);
  assert.match(html, /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-domain-span-bp="[^"]+"/);
  assert.match(html, /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-inner-width="[^"]+"/);
});

test("subview track-pair bands anchor to each contig lane instead of fixed top row at low tick-unit scales", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-lane0",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3_000_000,
            anchorStart: 100,
            hits: [],
          },
          {
            assemblyCtgId: 31,
            name: "support-hit-lane1",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3_000_000,
            anchorStart: 120,
            hits: [
              { refStart: 13_600_000, refEnd: 13_700_000, ctgStart: 100_000, ctgEnd: 200_000, blockLength: 100_000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3_200_000,
            anchorStart: 100,
            hits: [
              { refStart: 13_600_000, refEnd: 13_700_000, ctgStart: 100_000, ctgEnd: 200_000, blockLength: 100_000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 250,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  const topRectMatch = html.match(
    /data-subview-track-slot="top"[^>]*data-subview-contig-id="31"[^>]*data-subview-rect-y="([^"]+)"/,
  );
  assert.ok(topRectMatch, "expected top contig 31 with rect y");
  const topRectY = Number(topRectMatch[1]);

  const polygonMatch = html.match(
    /<polygon class="track-collinearity-band[^"]*"[^>]*points="([^"]+)"[^>]*data-subview-band-tooltip="[^"]*support-hit-lane1[^"]*"/,
  );
  assert.ok(polygonMatch, "expected a band polygon for support-hit-lane1");
  const firstPoint = String(polygonMatch[1] || "").split(" ")[0] || "";
  const firstY = Number(firstPoint.split(",")[1]);
  assert.ok(
    Math.abs(firstY - (topRectY + 14)) < 0.1,
    `expected top band y to align with contig bottom (${topRectY + 14}), got ${firstY}`,
  );
});

test("subview track-pair bands use only the shared ref-overlap slice instead of full hit widths", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 3000, ctgStart: 1, ctgEnd: 2000, blockLength: 2000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [
              { refStart: 2000, refEnd: 4000, ctgStart: 1, ctgEnd: 2000, blockLength: 2000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  const topRectMatch = html.match(
    /data-subview-track-slot="top"[^>]*data-subview-contig-id="30"[^>]*data-subview-rect-x="([^"]+)"[^>]*data-subview-rect-width="([^"]+)"/,
  );
  assert.ok(topRectMatch, "expected top rect metrics");
  const topRectX = Number(topRectMatch[1]);
  const topRectWidth = Number(topRectMatch[2]);

  const bottomRectMatch = html.match(
    /data-subview-track-slot="bottom"[^>]*data-subview-contig-id="2"[^>]*data-subview-rect-x="([^"]+)"[^>]*data-subview-rect-width="([^"]+)"/,
  );
  assert.ok(bottomRectMatch, "expected bottom rect metrics");
  const bottomRectX = Number(bottomRectMatch[1]);
  const bottomRectWidth = Number(bottomRectMatch[2]);

  const polygonMatch = html.match(
    /<polygon class="track-collinearity-band[^"]*"[^>]*points="([^"]+)"[^>]*data-subview-band-tooltip="[^"]*support-top[^"]*primary-bottom[^"]*"/,
  );
  assert.ok(polygonMatch, "expected a track-pair band polygon");
  const points = String(polygonMatch[1] || "")
    .split(" ")
    .map((point) => point.split(",").map(Number));

  assert.ok(
    Math.abs(points[0][0] - (topRectX + topRectWidth / 2)) < 0.2,
    `expected top overlap to start at half of top rect, got ${points[0][0]}`,
  );
  assert.ok(
    Math.abs(points[1][0] - (topRectX + topRectWidth)) < 0.2,
    `expected top overlap to end at top rect end, got ${points[1][0]}`,
  );
  assert.ok(
    Math.abs(points[2][0] - (bottomRectX + bottomRectWidth / 2)) < 0.2,
    `expected bottom overlap to end at half of bottom rect, got ${points[2][0]}`,
  );
  assert.ok(
    Math.abs(points[3][0] - bottomRectX) < 0.2,
    `expected bottom overlap to start at bottom rect start, got ${points[3][0]}`,
  );
});

test("subview track-pair overlap slice does not inflate a clamped 1px hit to full width", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 1, ctgEnd: 1, blockLength: 1001, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000000,
            anchorStart: 100,
            hits: [
              { refStart: 1500, refEnd: 2000, ctgStart: 1, ctgEnd: 1, blockLength: 501, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  const topRectMatch = html.match(
    /data-subview-track-slot="top"[^>]*data-subview-contig-id="30"[^>]*data-subview-rect-x="([^"]+)"[^>]*data-subview-rect-width="([^"]+)"/,
  );
  assert.ok(topRectMatch, "expected top rect metrics");

  const polygonMatch = html.match(
    /<polygon class="track-collinearity-band[^"]*"[^>]*points="([^"]+)"[^>]*data-subview-band-tooltip="[^"]*support-top[^"]*primary-bottom[^"]*"/,
  );
  assert.ok(polygonMatch, "expected a track-pair band polygon");
  const points = String(polygonMatch[1] || "")
    .split(" ")
    .map((point) => point.split(",").map(Number));
  const topProjectedWidth = points[1][0] - points[0][0];
  assert.ok(
    topProjectedWidth < 0.75,
    `expected top overlap width to stay subpixel-to-half-pixel, got ${topProjectedWidth}`,
  );
});

test("subview track-pair mode avoids cross-pair fan-out when adjacent hits slightly overlap at boundaries", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 1, ctgEnd: 1000, blockLength: 1001, mapq: 60 },
              { refStart: 2001, refEnd: 3000, ctgStart: 1001, ctgEnd: 2000, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2050, ctgStart: 1, ctgEnd: 1050, blockLength: 1051, mapq: 60 },
              { refStart: 2000, refEnd: 3000, ctgStart: 1051, ctgEnd: 2050, blockLength: 1001, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  const subviewSvgMatch = html.match(
    /<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/,
  );
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatches = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*"/g) || [];
  assert.equal(
    polygonMatches.length,
    2,
    `expected only the two best ordered bands, got ${polygonMatches.length}`,
  );
});

test("subview track-pair mode ignores malformed hits without explicit contig coordinates", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20_000_000,
            anchorStart: 320,
            hits: [
              { refStart: 12_200_000, refEnd: 13_700_000, blockLength: 1_500_000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20_000_000,
            anchorStart: 100,
            hits: [
              { refStart: 12_200_000, refEnd: 13_700_000, ctgStart: 2_200_000, ctgEnd: 3_700_000, blockLength: 1_500_000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  assert.doesNotMatch(html, /data-subview-band-tooltip="/);
});

test("subview track-pair mode marks box-selected ctgs as multi-selected", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairSelectedCtgs: [
            { trackRole: "support", contigId: 30 },
            { trackRole: "primary", contigId: 2 },
          ],
        },
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

  assert.match(
    html,
    /data-subview-track-role="support"[\s\S]*class="track-ctg subview-track-ctg is-companion is-multi-selected"/,
  );
  assert.match(
    html,
    /data-subview-track-role="primary"[\s\S]*class="track-ctg subview-track-ctg is-multi-selected"/,
  );
});

test("context menu on blank area exposes batch subview delete for box-selected track-pair ctgs", () => {
  const store = createStore(
    createState({
      assembly: {
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairSelectedCtgs: [
            { trackRole: "support", contigId: 30 },
            { trackRole: "primary", contigId: 2 },
          ],
        },
      },
    }),
  );
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    deletedCtgContext: null,
    memberNode: null,
    subviewTrackPairContext: null,
    store,
    host: {},
  });

  assert.ok(
    items.some((item) => item.label === "在 Subview 中删除已框选 contig（2，仅当前视图）"),
  );
});

test("subview track-pair mode keeps a fixed 20px visible gap between adjacent top-track contigs", () => {
  const html = renderAssemblyPage(
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
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 200,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  const matches = [
    ...html.matchAll(
      /data-subview-track-slot="top"[\s\S]*?data-subview-rect-x="([^"]+)"[\s\S]*?data-subview-rect-width="([^"]+)"/g,
    ),
  ];
  assert.ok(matches.length >= 2, "expected at least two top-track ctg bars");
  const firstX = Number(matches[0][1]);
  const firstWidth = Number(matches[0][2]);
  const secondX = Number(matches[1][1]);
  const visibleGapPx = secondX - (firstX + firstWidth);
  assert.ok(visibleGapPx >= 19.9, `expected visible gap >= 20px, got ${visibleGapPx}`);
});

test("subview track-pair preserves the main track contig order", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 300,
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 200,
          },
          {
            assemblyCtgId: 32,
            name: "support-c",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
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

  const topIds = [
    ...html.matchAll(/data-subview-track-slot="top"[^>]*data-subview-contig-id="([^"]+)"/g),
  ].map((match) => Number(match[1]));
  assert.deepEqual(topIds.slice(0, 3), [30, 31, 32]);
});

test("subview track-pair drag offsets move the targeted ctg bar", () => {
  const buildHtml = (subviewTrackDragOffsets = []) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 30,
              name: "support-top",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 20000,
              anchorStart: 320,
              hits: [
                { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 2,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 20000,
              anchorStart: 100,
              hits: [
                { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
              ],
            },
          ],
          subview: {
            selectedTrackARole: "primary",
            selectedTrackBRole: "support",
            summary: {
              mode: "track-pair",
              topTrack: { role: "support" },
              bottomTrack: { role: "primary" },
            },
          },
          subviewTrackDragOffsets,
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

  const extractTrackPairRectX = (html, slot, contigId) => {
    const match = html.match(
      new RegExp(`<g[^>]*data-subview-track-slot="${slot}"[^>]*data-subview-contig-id="${contigId}"[^>]*data-subview-rect-x="([^"]+)"`),
    );
    assert.ok(match, `expected ${slot} bar for contig ${contigId}`);
    return Number(match[1]);
  };

  const baseHtml = buildHtml([]);
  const shiftedHtml = buildHtml([{ slot: "top", contigId: 30, offsetPx: 60 }]);

  const baseTopX = extractTrackPairRectX(baseHtml, "top", 30);
  const shiftedTopX = extractTrackPairRectX(shiftedHtml, "top", 30);
  assert.ok(Math.abs((shiftedTopX - baseTopX) - 60) < 0.1, `expected top x shift by 60px, got ${shiftedTopX - baseTopX}`);
});

test("subview renders bands for support-support pairs when one contig comes from mirror track", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 1914,
            name: "Ctg1914",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4_000_000,
            anchorStart: 100,
            hits: [
              { refStart: 5_000_000, refEnd: 5_600_000, ctgStart: 100_000, ctgEnd: 700_000, blockLength: 600_000, mapq: 60 },
            ],
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 1901,
            name: "Ctg1901",
            totalLength: 3_500_000,
            anchorStart: 200,
            lengthBp: 3_500_000,
            startBp: 0,
            endBp: 3_499_999,
            laneIndex: 0,
            hits: [
              { refStart: 5_050_000, refEnd: 5_650_000, ctgStart: 120_000, ctgEnd: 720_000, blockLength: 600_000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 1901,
          selectedARole: "support",
          selectedBContigId: 1914,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 1901, role: "support", contigName: "Ctg1901" },
            bottom: { contigId: 1914, role: "support", contigName: "Ctg1914" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "canu2", label: "canu2" },
          { datasetId: 33, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = Array.from(
    subviewSvgMatch[0].matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.ok(polygons.length > 0, "expected support-support subview bands from mirror/source hits");
});
