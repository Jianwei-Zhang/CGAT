import {
  test,
  assert,
  bindAssemblyPageImpl,
  __testResolveCurrentRouteHost,
  __testSetSelectedPrimaryTrackCtgsHidden,
  __testRenderAssemblyFinalPathCard,
  __testRenderAssemblyMainTrackSections,
  __testTogglePrimaryTrackCtgHidden,
  renderAssemblyPage,
  createState,
  createStore,
} from "./tabs-semantics-harness.mjs";

test("assembly rerender host resolution falls back from detached route host to current route host", () => {
  const currentRouteHost = { id: "route-host", isConnected: true };
  const fakeDocument = {
    querySelector(selector) {
      return selector === "#route-host" ? currentRouteHost : null;
    },
    contains(node) {
      return node === currentRouteHost;
    },
  };
  const staleRouteHost = {
    id: "route-host",
    isConnected: false,
    ownerDocument: fakeDocument,
    matches(selector) {
      return selector === "#route-host";
    },
    closest(selector) {
      return selector === "#route-host" ? this : null;
    },
  };

  assert.equal(__testResolveCurrentRouteHost(staleRouteHost), currentRouteHost);
});


test("check new sequences tab renders API-backed items as rows", () => {
  const html = renderAssemblyPage(createState({ activeTab: "check-new-sequences" }));

  assert.match(html, /新增序列清单/);
  assert.match(html, /<th>操作<\/th>/);
  assert.match(html, /ptg_mock_7001/);
  assert.match(html, /utg_mock_7002/);
  assert.match(html, /hifiasm/);
  assert.match(html, /已显示/);
  assert.match(html, /已隐藏/);
  assert.doesNotMatch(html, /data-new-seq-action="add-seq-to-ctg"/);
  assert.match(html, /data-new-seq-action="locate-seq"/);
  assert.doesNotMatch(html, /纳入当前 contig/);
  assert.match(html, /定位到当前序列/);
  assert.doesNotMatch(html, /后续接入/);
});

test("contig list tab renders sorted Chinese columns and jump affordance", () => {
  const html = renderAssemblyPage(createState({ activeTab: "contig-list" }));

  assert.match(html, /contig 列表/);
  assert.match(html, /染色体/);
  assert.match(html, /总长度/);
  assert.match(html, /定位起点/);
  assert.match(html, /跳转/);
  assert.ok(html.indexOf("ctg-alpha") < html.indexOf("ctg-beta"));
  assert.ok(html.indexOf("ctg-beta") < html.indexOf("ctg-zeta"));
  assert.match(html, /跳转到该 contig/);
  assert.match(html, /data-assembly-ctg-id="2"/);
});

test("assembly track keeps duplicate origin ids as independent contigs", () => {
  const html = renderAssemblyPage(createState({
    chrCtgs: [
      {
        assemblyCtgId: 101,
        name: "pgt000001l@Chr01",
        originId: "pgt000001l",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 6100,
        anchorStart: 100,
      },
      {
        assemblyCtgId: 202,
        name: "pgt000001l@Chr02",
        originId: "pgt000001l",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 6000,
        anchorStart: 7000,
      },
    ],
    selectedCtgId: 202,
    ctgDetail: {
      assemblyCtgId: 202,
      name: "pgt000001l@Chr02",
      totalLength: 6000,
      members: [],
    },
  }));

  assert.match(html, /data-track-contig-id="101"/);
  assert.match(html, /data-track-contig-id="202"/);
  assert.match(html, /pgt000001l@Chr01/);
  assert.match(html, /pgt000001l@Chr02/);
});

test("stats tab shows Chinese core assembly metrics", () => {
  const html = renderAssemblyPage(createState({ activeTab: "stats" }));

  assert.match(html, /参考基因组 ID/);
  assert.match(html, /染色体数/);
  assert.match(html, /已放置 contig 数/);
  assert.match(html, /未放置 contig 数/);
  assert.match(html, /未放置总长度/);
  assert.match(html, /当前 contig/);
  assert.match(html, /4/);
});

test("assembly tab renders english labels when locale is en", () => {
  const html = renderAssemblyPage(createState({
    locale: "en",
    activeTab: "assembly",
  }));

  assert.doesNotMatch(html, /data-tab="assembly"/);
  assert.doesNotMatch(html, /data-tab="contig-list"/);
  assert.doesNotMatch(html, /data-tab="stats"/);
  assert.doesNotMatch(html, /data-tab="check-new-sequences"/);
  assert.doesNotMatch(html, /data-tab="about"/);
  assert.match(html, /Chromosome Chr01/);
  assert.doesNotMatch(html, />Download</);
  assert.match(html, />Primary Alignment View/);
  assert.match(html, /aria-label="Primary Alignment View Controls"/);
  assert.match(html, />Support Dataset</);
  assert.match(html, />Min Tick Unit \(kb\)</);
  assert.match(html, />Max Visible Count</);
  assert.match(html, /_Chr01 Primary ds track members/);
});

test("assembly page shell does not render an extra outer card frame", () => {
  const html = renderAssemblyPage(createState({ activeTab: "assembly" }));

  assert.match(html, /<section class="assembly-tabs">/);
  assert.doesNotMatch(html, /<section class="assembly-tabs card">/);
});

test("assembly page does not render member editor modal copy when locale is en", () => {
  const html = renderAssemblyPage(createState({
    locale: "en",
    assembly: {
      memberEditorModal: {
        open: true,
        ctgId: 8,
        ctgName: "ctg-beta",
        baselineCtgName: "ctg-beta",
        rows: [],
        baselineRows: [],
        deletedMemberIds: [],
        appendCtgDrafts: [],
        dirty: false,
        saving: false,
        status: "",
        error: "",
      },
    },
  }));

  assert.doesNotMatch(html, /aria-label="Contig Member Editor"/);
  assert.doesNotMatch(html, />Contig Name:</);
  assert.doesNotMatch(html, />Order</);
  assert.doesNotMatch(html, />Remove</);
  assert.doesNotMatch(html, /No member drafts yet\./);
  assert.doesNotMatch(html, />Add Member</);
  assert.doesNotMatch(html, /placeholder="Seq ID \/ Ctg ID \/ Ctg Name"/);
  assert.doesNotMatch(html, /placeholder="Start \(optional\)"/);
  assert.doesNotMatch(html, /placeholder="End \(optional\)"/);
  assert.doesNotMatch(html, />Append</);
  assert.doesNotMatch(html, /There are no changes to save\./);
  assert.doesNotMatch(html, />Cancel</);
  assert.doesNotMatch(html, />\s*Save\s*</);
});

test("assembly english view renders localized track labels and mirror empty states", () => {
  const html = renderAssemblyPage(createState({
    locale: "en",
    assembly: {
      supportDatasetId: 22,
      chrCtgs: [],
      supportChrCtgs: [],
      supportMirroredCtgs: [
        {
          datasetId: 22,
          datasetName: "flye",
          assemblyCtgId: 901,
          startBp: 10,
          endBp: 20,
          lengthBp: 11,
          laneIndex: 0,
        },
      ],
      subview: {
        summary: {
          mode: "track-pair",
          topTrack: { role: "support", source: "mirror", datasetId: 22, isMirror: true },
          bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
        },
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  }));

  assert.match(html, />Primary Dataset Track</);
  assert.match(html, />flye Mirror Track</);
  assert.doesNotMatch(html, /主 ds 轨道|辅 ds 轨道|mirror 轨道/);
});

test("assembly main view renders unified single-card track container", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: null,
        supportChrCtgs: [],
      },
    }),
  );

  assert.match(html, /assembly-track-unified/);
  assert.doesNotMatch(html, /assembly-track-stack/);
  assert.match(html, /assembly-track-label-column/);
  assert.match(html, /data-focus-start="/);
  assert.match(html, /ref_chr1/);
  assert.match(html, /主 ds 轨道/);
  assert.doesNotMatch(html, /block_length/);
  assert.doesNotMatch(html, /<h4>ctg 操作<\/h4>/);
  assert.doesNotMatch(html, /<h4>sequence 操作<\/h4>/);
  assert.doesNotMatch(html, /assembly-action-feedback/);
  assert.doesNotMatch(html, /Junction 检查/);
  assert.doesNotMatch(html, /run-junction-inspection-button/);
  assert.doesNotMatch(html, /subview2-a-ctg-id/);
  assert.doesNotMatch(html, /enter-subview-2/);
});

test("local refresh renderers exclude unrelated assembly regions", () => {
  const state = createState({
    assembly: {
      supportDatasetId: null,
      supportChrCtgs: [],
    },
  });
  const mainHtml = __testRenderAssemblyMainTrackSections(state);
  const finalPathHtml = __testRenderAssemblyFinalPathCard(state);

  assert.match(mainHtml, /chr-strip has-members-panel/);
  assert.match(mainHtml, /assembly-track-unified/);
  assert.doesNotMatch(mainHtml, /data-subview-panel="1"/);
  assert.doesNotMatch(mainHtml, /class="card final-path-card"/);

  assert.match(finalPathHtml, /class="card final-path-card"/);
  assert.doesNotMatch(finalPathHtml, /assembly-track-unified/);
  assert.doesNotMatch(finalPathHtml, /data-subview-panel="1"/);
});

test("assembly main view shows phased-track creation only when project enables phased assembly", () => {
  const ordinaryHtml = renderAssemblyPage(createState());
  const phasedEnabledHtml = renderAssemblyPage(createState({
    initializer: {
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
  }));

  assert.doesNotMatch(ordinaryHtml, /data-create-phased-track="1"/);
  assert.match(phasedEnabledHtml, /data-create-phased-track="1"/);
  assert.match(phasedEnabledHtml, />\+ 分型轨道</);
  assert.doesNotMatch(phasedEnabledHtml, /主分型/);
});

test("assembly main view inserts phased rows after primary and before mirror rows", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      datasets: [
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22], phasedAssemblyEnabled: true }],
    },
    assembly: {
      supportDatasetId: 22,
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "support-a", totalLength: 700, anchorStart: 100, hits: [] },
      ],
      supportMirroredCtgs: [
        {
          datasetId: 22,
          datasetName: "flye",
          assemblyCtgId: 30,
          startBp: 100,
          endBp: 799,
          lengthBp: 700,
          laneIndex: 0,
          hits: [],
        },
      ],
      phasedChrTracks: [
        {
          phasedTrackId: 1,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 101, phasedTrackId: 1, assemblyCtgId: 2, displayOrder: 1 }],
        },
        {
          phasedTrackId: 2,
          haplotypeKey: "B",
          label: "Chr01B",
          displayOrder: 2,
          items: [],
        },
      ],
    },
  }));

  const trackLabels = Array.from(
    html.matchAll(/<div class="assembly-track-label-row[^"]*"[^>]*title="([^"]+)"/g),
    (match) => match[1],
  );
  const supportIndex = trackLabels.indexOf("辅(flye)");
  const primaryIndex = trackLabels.findIndex((label) => label === "主 ds 轨道" || label.startsWith("主("));
  const phasedAIndex = trackLabels.indexOf("主分型 Chr01A");
  const phasedBIndex = trackLabels.indexOf("主分型 Chr01B");
  const mirrorIndex = trackLabels.indexOf("flye-镜像轨道");

  assert.ok(supportIndex >= 0, "expected support row label");
  assert.ok(primaryIndex > supportIndex, "expected primary after support");
  assert.ok(phasedAIndex > primaryIndex, "expected phased A after primary");
  assert.ok(phasedBIndex > phasedAIndex, "expected phased B after A");
  assert.ok(mirrorIndex > phasedBIndex, "expected mirror after phased rows");
  assert.match(html, /class="track-ctg[^"]*is-phased-track/);
  assert.match(html, /该分型轨道暂无 contig/);

  const emptyTrackLabelTop = html.match(
    /<div class="assembly-track-label-row[^"]*is-phased-track[^"]*" style="top:([\d.]+)px"[^>]*title="主分型 Chr01B"/,
  );
  const emptyTrackMessageY = html.match(
    /<text class="track-row-empty-label" x="12" y="([\d.]+)">该分型轨道暂无 contig。<\/text>/,
  );
  assert.ok(emptyTrackLabelTop, "expected empty phased-track label geometry");
  assert.ok(emptyTrackMessageY, "expected empty phased-track message geometry");
  assert.equal(
    Number(emptyTrackMessageY[1]) - Number(emptyTrackLabelTop[1]),
    13,
    "expected empty message baseline to align with the phased-track label",
  );
});

test("assembly main view keeps compact phased spacing without mirror rows", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
    assembly: {
      supportDatasetId: null,
      supportChrCtgs: [],
      phasedChrTracks: [
        {
          phasedTrackId: 1,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 101, phasedTrackId: 1, assemblyCtgId: 2, displayOrder: 1 }],
        },
      ],
    },
  }));

  const extractRectMetrics = (htmlText, { ctgId, role, phasedTrackItemId = null }) => {
    const phasedAttr = phasedTrackItemId
      ? `[^>]*data-track-phased-track-item-id="${phasedTrackItemId}"`
      : "";
    const match = htmlText.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${role}"${phasedAttr}[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"[^>]*data-track-rect-height="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect metrics for ${role} ctg ${ctgId}`);
    return { x: Number(match[1]), y: Number(match[2]), width: Number(match[3]), height: Number(match[4]) };
  };
  const primary = extractRectMetrics(html, { ctgId: 2, role: "primary" });
  const phased = extractRectMetrics(html, { ctgId: 2, role: "phased", phasedTrackItemId: 101 });
  const topDelta = phased.y - primary.y;

  assert.ok(Math.abs(topDelta - 24) < 0.01, `expected phased top delta 24px without mirror rows, got ${topDelta}`);
});

test("phased track ctg bars reuse the matching primary layout rect", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
    assembly: {
      supportDatasetId: null,
      supportChrCtgs: [],
      phasedChrTracks: [
        {
          phasedTrackId: 1,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 101, phasedTrackId: 1, assemblyCtgId: 26, displayOrder: 1, orient: "+" }],
        },
      ],
      chrCtgs: [
        {
          assemblyCtgId: 26,
          name: "contig_26",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1_000_000,
          anchorStart: 1,
          orient: "-",
          refOrient: "-",
        },
        {
          assemblyCtgId: 27,
          name: "contig_27",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1_000_000,
          anchorStart: 1_000_001,
          orient: "+",
          refOrient: "+",
        },
      ],
    },
  }));

  const extractRectMetrics = (htmlText, { ctgId, role, phasedTrackItemId = null }) => {
    const phasedAttr = phasedTrackItemId
      ? `[^>]*data-track-phased-track-item-id="${phasedTrackItemId}"`
      : "";
    const match = htmlText.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${role}"${phasedAttr}[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect metrics for ${role} ctg ${ctgId}`);
    return { x: Number(match[1]), width: Number(match[2]) };
  };
  const primary = extractRectMetrics(html, { ctgId: 26, role: "primary" });
  const phased = extractRectMetrics(html, { ctgId: 26, role: "phased", phasedTrackItemId: 101 });

  assert.equal(phased.x, primary.x);
  assert.equal(phased.width, primary.width);
});

test("assembly tab keeps the main view card and subview card but removes their shared outer card wrapper", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: null,
        supportChrCtgs: [],
      },
    }),
  );

  assert.match(html, /<section class="assembly-track-content-stack">/);
  assert.match(html, /<section class="assembly-main-view">/);
  assert.doesNotMatch(html, /<section class="card assembly-main-view">/);
  assert.match(html, /<div class="assembly-track-unified assembly-track-panel">/);
  assert.match(html, /<article class="card subview-selection-panel"[^>]*>/);
  assert.match(html, /<article class="card final-path-card"/);
});

test("assembly tab renders a loading curtain over assembly content while data is loading", () => {
  const loadingHtml = renderAssemblyPage(
    createState({
      assembly: {
        loading: true,
        summary: "正在加载 chromosome...",
      },
    }),
  );
  const loadedHtml = renderAssemblyPage(createState());

  assert.match(loadingHtml, /data-assembly-loading-curtain="1"/);
  assert.doesNotMatch(loadingHtml, /data-track-contig-id="/);
  assert.doesNotMatch(loadedHtml, /data-assembly-loading-curtain="1"/);
});

test("assembly page renders an app-level confirmation dialog for destructive actions", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "delete-selected",
          message: "确认删除已框选的 2 个 contig 吗？",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="delete-selected"/);
  assert.match(html, /class="assembly-confirm-title is-danger"/);
  assert.match(html, /class="assembly-confirm-message is-danger"/);
  assert.match(html, /确认删除已框选的 2 个 contig 吗？/);
  assert.match(html, /data-assembly-confirm-action="confirm"/);
  assert.match(html, /data-assembly-confirm-action="cancel"/);
});

test("assembly page renders a localized non-danger notice with one action", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "phased-grt-notice",
          mode: "notice",
          title: "GRT 结果暂不可用",
          message: "分型轨道暂不支持显示 GRT 预计算结果。关闭所有分型轨道后，即可恢复 GRT 结果。",
          confirmLabel: "我知道了",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-mode="notice"/);
  assert.match(html, /aria-label="GRT 结果暂不可用"/);
  assert.match(html, />我知道了<\/button>/);
  assert.doesNotMatch(html, /assembly-confirm-title is-danger/);
  assert.doesNotMatch(html, /data-assembly-confirm-action="cancel"/);
});

test("assembly page can render support ds rules unsaved-close confirmation internally", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "support-rules-close",
          message: "修改尚未保存，确定关闭并放弃修改吗？",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="support-rules-close"/);
  assert.match(html, /修改尚未保存，确定关闭并放弃修改吗？/);
  assert.match(html, /data-assembly-confirm-action="confirm"/);
  assert.match(html, /data-assembly-confirm-action="cancel"/);
});

test("assembly page renders an app-level bp threshold prompt dialog", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "delete-shorter-than",
          mode: "prompt",
          message: "删除小于多少 bp 的主 ds contig？",
          defaultValue: "100000",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="delete-shorter-than"/);
  assert.match(html, /删除小于多少 bp 的主 ds contig？/);
  assert.match(html, /data-assembly-confirm-input="delete-shorter-than"/);
  assert.match(html, /value="100000"/);
});

test("assembly page renders anchor offset direction and bp in one dialog", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "anchor-offset",
          mode: "anchor-offset",
          message: "设置偏移方向和 bp 距离。",
          defaultDirection: "left",
          defaultValue: "50",
          anchorOffsetSourceEdge: {
            hitKey: "hit-1",
            edge: "left",
            topEndpointKey: "top",
            bottomEndpointKey: "bottom",
            topContigId: 30,
            bottomContigId: 8,
            topCutBp: 100,
            bottomCutBp: 200,
            topLengthBp: 1000,
            bottomLengthBp: 500,
          },
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="anchor-offset"/);
  assert.match(html, /data-assembly-confirm-mode="anchor-offset"/);
  assert.match(html, /value="right"[\s\S]*data-assembly-anchor-offset-direction="anchor-offset"/);
  assert.match(html, /value="left"[\s\S]*data-assembly-anchor-offset-direction="anchor-offset"[\s\S]*checked/);
  assert.match(html, /data-assembly-confirm-input="anchor-offset"/);
  assert.match(html, /value="50"/);
  assert.doesNotMatch(html, /data-assembly-confirm-action="confirm"[^>]*disabled/);
});

test("assembly anchor offset dialog keeps ambiguous defaults empty and disables confirmation", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "anchor-offset-empty",
          mode: "anchor-offset",
          message: "设置偏移方向和 bp 距离。",
          defaultDirection: "",
          defaultValue: "",
          anchorOffsetSourceEdge: {
            hitKey: "hit-1",
            edge: "left",
            topEndpointKey: "top",
            bottomEndpointKey: "bottom",
            topContigId: 30,
            bottomContigId: 8,
            topCutBp: 100,
            bottomCutBp: 200,
            topLengthBp: 1000,
            bottomLengthBp: 500,
          },
        },
      },
    }),
  );

  assert.doesNotMatch(html, /data-assembly-anchor-offset-direction="anchor-offset-empty"[^>]*checked/);
  assert.match(html, /data-assembly-confirm-input="anchor-offset-empty"/);
  assert.match(html, /data-assembly-confirm-action="confirm"[^>]*disabled/);
  assert.match(html, /data-assembly-anchor-offset-error="anchor-offset-empty"/);
  assert.doesNotMatch(html, /偏移后锚点超出 contig 范围/);
});

test("assembly anchor offset dialog preserves an automatic out-of-range value with an inline error", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "anchor-offset-invalid",
          mode: "anchor-offset",
          message: "设置偏移方向和 bp 距离。",
          defaultDirection: "left",
          defaultValue: "200",
          anchorOffsetSourceEdge: {
            hitKey: "hit-1",
            edge: "left",
            topEndpointKey: "top",
            bottomEndpointKey: "bottom",
            topContigId: 30,
            bottomContigId: 8,
            topCutBp: 400,
            bottomCutBp: 100,
            topLengthBp: 1000,
            bottomLengthBp: 500,
          },
        },
      },
    }),
  );

  assert.match(html, /value="200"/);
  assert.match(html, /偏移后锚点超出 contig 范围，未创建。/);
  assert.match(html, /data-assembly-confirm-action="confirm"[^>]*disabled/);
});

test("assembly tab renders a project-chr members card above main track with name length and member count", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
      },
    }),
  );

  const membersCardIndex = html.indexOf("assembly-members-panel");
  const mainTrackIndex = html.indexOf("assembly-track-unified");
  const ctgGridCount = (html.match(/class="[^"]*ctg-chip-grid[^"]*"/g) || []).length;

  assert.match(html, /assembly-members-panel/);
  assert.match(html, /<div class="chr-strip has-members-panel">[\s\S]*assembly-members-panel-inline is-collapsed/);
  assert.doesNotMatch(html, /<\/div>\s*<article class="card assembly-members-panel"/);
  assert.match(html, /project1_Chr01 主ds轨道成员/);
  assert.match(
    html,
    /<button[^>]*data-members-card-toggle="1"[^>]*aria-expanded="false"[^>]*>/,
  );
  assert.doesNotMatch(html, /assembly-member-chip-region/);
  assert.doesNotMatch(html, /data-track-focus-mode="start"/);
  assert.equal(ctgGridCount, 0);
  assert.ok(membersCardIndex >= 0);
  assert.ok(mainTrackIndex >= 0);
  assert.ok(membersCardIndex < mainTrackIndex);
});

test("assembly tab expands the members card body when membersCardCollapsed is false", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
      },
    }),
  );

  assert.match(html, /project1_Chr01 主ds轨道成员/);
  assert.match(
    html,
    /<button[^>]*data-members-card-toggle="1"[^>]*aria-expanded="true"[^>]*>/,
  );
  assert.match(
    html,
    /<span class="assembly-members-panel-title-inline">\s*<strong>project1_Chr01 主ds轨道成员<\/strong>\s*<button[^>]*data-reset-members-state="1"[^>]*aria-label="重置：撤销删除、撤销隐藏"/,
  );
  assert.match(html, /ctg-beta/);
  assert.match(html, /600 bp/);
  assert.doesNotMatch(html, /600 bp ;/);
  assert.match(html, /data-track-focus-mode="start"/);
  assert.equal((html.match(/class="[^"]*ctg-chip-grid[^"]*"/g) || []).length, 1);
});

test("assembly tab appends deleted members into the same members card without inline restore buttons", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
        deletedCtgs: [
          {
            deletedCtgRecordId: 9101,
            assemblyCtgId: 77,
            name: "ctg-deleted-77",
            memberCount: 2,
            totalLength: 65432,
          },
        ],
      },
    }),
  );

  assert.match(html, /已删除成员/);
  assert.match(
    html,
    /<span class="assembly-members-panel-title-inline">\s*<strong>已删除成员<\/strong>\s*<button[^>]*data-restore-all-deleted-ctgs="1"[^>]*aria-label="撤销全部删除"[^>]*title="撤销全部删除"/,
  );
  assert.match(html, /ctg-deleted-77/);
  assert.match(html, /65,432 bp/);
  assert.doesNotMatch(html, /65,432 bp ;/);
  assert.match(html, /data-deleted-ctg-record-id="9101"/);
  assert.doesNotMatch(html, /data-restore-deleted-ctg-id=/);
  assert.doesNotMatch(html, /撤销删除（Ctg77）/);
});

test("restore-all deleted members button restores every deleted record in the current chr", async () => {
  const listeners = new Map();
  const restoreButton = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "[data-restore-all-deleted-ctgs='1']" ? restoreButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        deletedCtgs: [
          { deletedCtgRecordId: 9101, assemblyCtgId: 77 },
          { deletedCtgRecordId: 9102, assemblyCtgId: 88 },
          { deletedCtgRecordId: null, assemblyCtgId: 99 },
        ],
      },
    }),
  );
  const calls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.restoreSelectedDeletedCtgs = async (_host, _store, selectedRecordIds) => {
    calls.push(selectedRecordIds);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listeners.get("click")?.({ preventDefault() {} });

  assert.deepEqual(calls, [[9101, 9102]]);
});

test("reset members button clears hidden primary contigs and restores every deleted record", async () => {
  const listeners = new Map();
  const resetButton = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "[data-reset-members-state='1']" ? resetButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [2, 8],
        deletedCtgs: [
          { deletedCtgRecordId: 9101, assemblyCtgId: 77 },
          { deletedCtgRecordId: 9102, assemblyCtgId: 88 },
        ],
      },
    }),
  );
  const restoreCalls = [];
  const persistedHiddenIds = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async (_host, currentStore) => {
    persistedHiddenIds.push(currentStore.getState().assembly.hiddenPrimaryCtgIds);
  };
  deps.restoreSelectedDeletedCtgs = async (_host, _store, selectedRecordIds) => {
    restoreCalls.push(selectedRecordIds);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listeners.get("click")?.({ preventDefault() {} });

  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, []);
  assert.deepEqual(persistedHiddenIds, [[]]);
  assert.deepEqual(restoreCalls, [[9101, 9102]]);
});

test("member cards render multi-selected style for selected primary ctgs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        trackSelectedCtgIds: [2, 8],
      },
    }),
  );

  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="2"/,
  );
  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="8"/,
  );
});

test("member cards mark primary ctgs assigned to other chromosome groups", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ptg000001l@Chr01",
            originId: "ptg000001l",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            coAssignedChrNames: ["Chr02", "Chr05"],
          },
        ],
      },
    }),
  );

  assert.doesNotMatch(html, /class="ctg-chip-coassigned-tag"/);
  assert.match(
    html,
    /title="ptg000001l@Chr01&#10;同时被分配到：Chr02, Chr05"/,
  );
  assert.match(
    html,
    /<span class="ctg-chip-name is-coassigned" title="ptg000001l@Chr01&#10;同时被分配到：Chr02, Chr05">ptg000001l<\/span>/,
  );
});

test("batch hide patches member DOM without replacing the assembly tab body", async () => {
  const tabBody = {
    innerHTML: "old tab",
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const routeHost = {
    innerHTML: "old route",
    querySelector(selector) {
      return selector === ".tab-body" ? tabBody : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const host = {
    closest(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        membersCardCollapsed: false,
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );
  const patchedHiddenIds = [];
  await __testSetSelectedPrimaryTrackCtgsHidden(host, store, [2], true, {
    async persistProjectAssemblyViewState() {},
    patchPrimaryHiddenCtgDom(_host, _store, hiddenIds) {
      patchedHiddenIds.push(hiddenIds);
      return true;
    },
  });

  assert.equal(routeHost.innerHTML, "old route");
  assert.equal(tabBody.innerHTML, "old tab");
  assert.deepEqual(patchedHiddenIds, [[2]]);
});

test("single hide refreshes final path log after local hidden patch", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathViewMode: "log",
        hiddenPrimaryCtgIds: [],
      },
    }),
  );
  const patchedHiddenIds = [];
  const refreshedHiddenIds = [];

  await __testTogglePrimaryTrackCtgHidden(host, store, 2, true, {
    async persistProjectAssemblyViewState() {},
    patchPrimaryHiddenCtgDom(_host, _store, hiddenIds) {
      patchedHiddenIds.push(hiddenIds);
      return true;
    },
    refreshFinalPathLogAfterPrimaryHiddenPatch(_host, currentStore) {
      refreshedHiddenIds.push(currentStore.getState().assembly.hiddenPrimaryCtgIds);
      return true;
    },
  });

  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, [2]);
  assert.deepEqual(patchedHiddenIds, [[2]]);
  assert.deepEqual(refreshedHiddenIds, [[2]]);
});

test("member cards normalize duplicated and noisy selected primary ctg ids", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        trackSelectedCtgIds: [8, "2", 8, 0, -1, "foo", 2.9],
      },
    }),
  );

  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="2"/,
  );
  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="8"/,
  );
  assert.doesNotMatch(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="5"/,
  );
});

test("hidden primary contig updates card tag and shifts only its own track bar up by 30px", () => {
  const normalHtml = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
        hiddenPrimaryCtgIds: [],
      },
    }),
  );
  const hiddenHtml = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );

  assert.match(
    hiddenHtml,
    /<button class="ctg-chip[^"]*is-hidden-contig[^"]*" data-assembly-ctg-id="2"[\s\S]*?<span class="ctg-chip-hidden-tag">\s*（已隐藏）<\/span>/,
  );
  assert.match(
    hiddenHtml,
    /<g class="track-ctg-group[^"]*is-hidden-contig[^"]*"[^>]*data-track-contig-id="2"[^>]*>/,
  );
  assert.match(hiddenHtml, /<rect\s+class="track-ctg is-hidden-contig"[\s\S]*?data-track-focus="false"/);

  const extractTrackRectY = (html, ctgId) => {
    const regex = new RegExp(
      `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-rect-y="([^"]+)"`,
    );
    const match = html.match(regex);
    assert.ok(match, `expected data-track-rect-y for ctg ${ctgId}`);
    return Number(match[1]);
  };
  const normalHiddenTargetY = extractTrackRectY(normalHtml, 2);
  const hiddenTargetY = extractTrackRectY(hiddenHtml, 2);
  const normalNeighborY = extractTrackRectY(normalHtml, 8);
  const hiddenNeighborY = extractTrackRectY(hiddenHtml, 8);

  assert.ok(
    Math.abs((normalHiddenTargetY - hiddenTargetY) - 30) < 0.01,
    `expected hidden ctg y shift to be 30px, got normal=${normalHiddenTargetY}, hidden=${hiddenTargetY}`,
  );
  assert.ok(
    Math.abs(normalNeighborY - hiddenNeighborY) < 0.01,
    `expected neighbor ctg y unchanged, got normal=${normalNeighborY}, hidden=${hiddenNeighborY}`,
  );
});

test("hidden primary contig does not render its own collinearity hit bands", () => {
  const buildState = (hiddenPrimaryCtgIds = []) =>
    createState({
      assembly: {
        hiddenPrimaryCtgIds,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [
              {
                refStart: 10_000,
                refEnd: 20_000,
                ctgStart: 5_000,
                ctgEnd: 15_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
          {
            assemblyCtgId: 8,
            name: "ctg-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 300,
            hits: [
              {
                refStart: 30_000,
                refEnd: 40_000,
                ctgStart: 25_000,
                ctgEnd: 35_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
      },
    });

  const visibleHtml = renderAssemblyPage(buildState([]));
  const hiddenHtml = renderAssemblyPage(buildState([8]));
  const countBands = (html) => (html.match(/class="track-collinearity-band"/g) || []).length;

  assert.equal(countBands(visibleHtml), 2);
  assert.equal(countBands(hiddenHtml), 1);
});
