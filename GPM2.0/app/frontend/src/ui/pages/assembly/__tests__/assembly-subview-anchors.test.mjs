import {
  test,
  assert,
  readFileSync,
  __testCancelSubviewPairwiseEvidence,
  renderAssemblyPage,
  createState,
} from "./tabs-semantics-harness.mjs";

test("subview track controls render independently from main track controls", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 10000,
          mapq: 30,
        },
        subviewTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 5,
          alignmentLength: 1000,
          mapq: 0,
        },
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
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /id="assembly-track-min-tick-unit-kb"[^>]*value="250"/);
  assert.match(html, /id="assembly-track-max-tick-count"[^>]*value="20"/);
  assert.match(html, /id="assembly-track-alignment-length"[^>]*value="10000"/);
  assert.match(html, /id="assembly-track-mapq"[^>]*value="30"/);

  assert.match(html, /id="subview-track-min-tick-unit-kb"[^>]*value="10000"/);
  assert.match(html, /id="subview-track-max-tick-count"[^>]*value="5"/);
  assert.match(html, /id="subview-track-alignment-length"[^>]*value="1000"/);
  assert.match(html, /id="subview-track-mapq"[^>]*value="0"/);
  assert.match(html, /id="assembly-track-min-tick-unit-kb-menu"[\s\S]*data-track-combo-value="100000"/);
  assert.match(html, /id="subview-track-min-tick-unit-kb-menu"[\s\S]*data-track-combo-value="100000"/);
  assert.match(html, /data-subview-action="swap-track-order"/);
  assert.match(
    html,
    /Ctrl\/Cmd 选中任意两个ctg进入subview-ctg；也支持点击任意两个轨道名进入subview-track。<\/p>\s*<div class="subview-candidate-row">/,
  );
  assert.doesNotMatch(html, /已选 \d\/2 个ctg；右键选择“进入Subview-ctg”。/);
  assert.doesNotMatch(html, /已选 \d\/2 条ds轨道。/);
  assert.doesNotMatch(html, /Subview 已进入轨道模式。/);
  assert.doesNotMatch(html, /Subview 已切换上下轨道顺序。/);
  assert.match(
    html,
    /<div class="assembly-track-label-column subview-track-label-column"[\s\S]*class="button ghost tiny subview-track-order-toggle is-in-label-column"[\s\S]*<\/div>\s*<div\s+class="assembly-track-scroll subview-track-scroll"/,
  );
});

test("subview chart uses real relative ctg lengths so top and bottom bars can differ", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-short", assignedChrName: "Chr01", memberCount: 1, totalLength: 600, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-long", assignedChrName: "Chr01", memberCount: 1, totalLength: 2400, anchorStart: 100 },
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
            top: { contigId: 30, role: "support", contigName: "support-short" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-long" },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const barMatches = Array.from(
    subviewSvgMatch[0].matchAll(/<rect class="track-ctg([^"]*)"[^>]*width="([^"]+)"/g),
  );
  assert.equal(barMatches.length >= 2, true);
  const topWidth = Number(barMatches[0][2]);
  const bottomWidth = Number(barMatches[1][2]);
  assert.ok(
    topWidth < bottomWidth,
    `expected top bar width < bottom bar width, got top=${topWidth}, bottom=${bottomWidth}`,
  );
});

test("subview ctg mode renders independent left/right edge targets for each paired hit", () => {
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
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
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

  assert.match(
    html,
    /class="subview-anchor-hit-zone"[^>]*data-subview-anchor-hit-key="hit-1"[^>]*data-subview-anchor-edge="left"/,
  );
  assert.match(
    html,
    /class="subview-anchor-hit-zone"[^>]*data-subview-anchor-hit-key="hit-1"[^>]*data-subview-anchor-edge="right"/,
  );
});

test("active subview anchors render on the same gap-edge geometry as their hit zones", () => {
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
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
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

  assert.match(
    html,
    /class="subview-anchor-line is-active"[^>]*stroke="red"[^>]*stroke-width="3"/,
  );
  assert.match(
    html,
    /data-subview-track-slot="bottom"[\s\S]*class="subview-anchor-line is-active"[^>]*stroke="red"/,
  );
  assert.match(
    html,
    /class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="hit-1"[^>]*data-subview-anchor-edge="left"/,
  );
  assert.match(
    html,
    /class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-top-x="[0-9.]+"[^>]*data-subview-anchor-bottom-x="[0-9.]+"/,
  );
  const topBarMatch = html.match(/data-subview-track-slot="top"[^>]*data-subview-rect-y="([^"]+)"[^>]*data-subview-rect-height="([^"]+)"/);
  const bottomBarMatch = html.match(/data-subview-track-slot="bottom"[^>]*data-subview-rect-y="([^"]+)"/);
  const anchorHitZoneMatch = html.match(/class="subview-anchor-hit-zone is-active"[^>]*y1="([^"]+)"[^>]*y2="([^"]+)"/);
  assert.ok(topBarMatch, "expected a top subview ctg bar");
  assert.ok(bottomBarMatch, "expected a bottom subview ctg bar");
  assert.ok(anchorHitZoneMatch, "expected an active anchor hit zone");
  assert.equal(
    Number(anchorHitZoneMatch[1]).toFixed(2),
    (Number(topBarMatch[1]) + Number(topBarMatch[2])).toFixed(2),
  );
  assert.equal(
    Number(anchorHitZoneMatch[2]).toFixed(2),
    Number(bottomBarMatch[1]).toFixed(2),
  );
});

test("subview keeps anchored hits visible after alignment length filters non-anchored hits away", () => {
  const renderWithAlignmentLength = (alignmentLength) =>
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
              totalLength: 5000,
              anchorStart: 320,
              hits: [
                { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 220, blockLength: 1000, mapq: 60 },
                { refStart: 5000, refEnd: 7000, ctgStart: 1101, ctgEnd: 1460, blockLength: 180000, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 8,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 5000,
              anchorStart: 100,
              hits: [
                { refStart: 1000, refEnd: 2000, ctgStart: 801, ctgEnd: 920, blockLength: 1000, mapq: 60 },
                { refStart: 5000, refEnd: 7000, ctgStart: 2101, ctgEnd: 2460, blockLength: 180000, mapq: 60 },
              ],
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 1000,
            maxTickCount: 10,
            alignmentLength,
            mapq: 0,
          },
          subview: {
            mode: "2-contig",
            selectedAContigId: 8,
            selectedARole: "primary",
            selectedBContigId: 30,
            selectedBRole: "support",
            activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
            summary: {
              mode: "2-contig",
              top: { contigId: 30, role: "support", contigName: "support-top" },
              bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
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

  const baseHtml = renderWithAlignmentLength(1000);
  const filteredHtml = renderWithAlignmentLength(100000);

  assert.match(baseHtml, /class="subview-anchor-line is-active"/);
  assert.match(baseHtml, /data-subview-hit-key="hit-1"/);
  assert.match(filteredHtml, /class="subview-anchor-line is-active"/);
  assert.match(filteredHtml, /data-subview-hit-key="hit-1"/);
});

test("subview drag offsets keep anchor lines aligned with the hit polygon edges", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        subviewTrackDragOffsets: [{ slot: "bottom", assemblyCtgId: 8, offsetPx: 180 }],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
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

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"[^>]*data-subview-hit-key="hit-1"/);
  const lineMatch = html.match(/class="subview-anchor-line is-active"[^>]*x1="([^"]+)"[^>]*y1="([^"]+)"[^>]*x2="([^"]+)"[^>]*y2="([^"]+)"/);
  assert.ok(bandMatch, "expected anchored subview hit polygon");
  assert.ok(lineMatch, "expected active anchor line");
  const [topLeft, , , bottomLeft] = bandMatch[1].split(" ");
  const [topLeftX, topBottomY] = topLeft.split(",").map(Number);
  const [bottomLeftX, bottomTopY] = bottomLeft.split(",").map(Number);

  assert.equal(Number(lineMatch[1]).toFixed(2), topLeftX.toFixed(2));
  assert.equal(Number(lineMatch[2]).toFixed(2), topBottomY.toFixed(2));
  assert.equal(Number(lineMatch[3]).toFixed(2), bottomLeftX.toFixed(2));
  assert.equal(Number(lineMatch[4]).toFixed(2), bottomTopY.toFixed(2));
});

test("anchor-enabled ctgs expose fragment hit zones instead of only whole-contig append targets", () => {
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
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
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

  assert.match(
    html,
    /data-subview-fragment-key="8:1-500"[^>]*data-subview-fragment-contig-id="8"[\s\S]*class="subview-fragment-outline"/,
  );
  assert.match(
    html,
    /<rect\s+class="subview-fragment-hit-zone"[\s\S]*?data-subview-fragment-key="8:1-500"[\s\S]*?<title>primary-bottom \| start=1 \| len=500<\/title>[\s\S]*?<\/rect>/,
  );
  assert.doesNotMatch(
    html,
    /<rect\s+class="subview-fragment-hit-zone"[\s\S]*?data-subview-fragment-key="8:1-500"[\s\S]*?<title>primary-bottom \| start=0 \| len=1000<\/title>[\s\S]*?<\/rect>/,
  );
});

test("subview fragment hover keeps track-colored outlines instead of red", () => {
  const css = readFileSync(new URL("../../../../styles/components.css", import.meta.url), "utf8");

  assert.match(
    css,
    /\.subview-fragment-outline\s*\{[\s\S]*stroke:\s*transparent/i,
  );
  assert.match(
    css,
    /\.subview-fragment-hit-zone\[data-subview-fragment-role="ref"\]:hover\s*\+\s*\.subview-fragment-outline,\s*\.subview-fragment-hit-zone\[data-subview-fragment-role="ref"\]\.is-menu-active\s*\+\s*\.subview-fragment-outline\s*\{[\s\S]*stroke:\s*#8e8e8e/i,
  );
  assert.match(
    css,
    /\.subview-fragment-hit-zone\[data-subview-fragment-role="phased"\]:hover\s*\+\s*\.subview-fragment-outline,\s*\.subview-fragment-hit-zone\[data-subview-fragment-role="phased"\]\.is-menu-active\s*\+\s*\.subview-fragment-outline\s*\{[\s\S]*stroke:\s*#2e567f/i,
  );
  assert.doesNotMatch(css, /\.subview-fragment-hit-zone:hover\s*\+\s*\.subview-fragment-outline[\s\S]*stroke:\s*red/i);
  assert.doesNotMatch(css, /\.subview-fragment-hit-zone\.is-menu-active\s*\+\s*\.subview-fragment-outline[\s\S]*stroke:\s*red/i);
});

test("subview-ctg phased anchor fragments expose hoverable phased hit zones", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        isChrPhased: true,
        supportDatasetId: 22,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "phased-source",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "phased", contigName: "phased-source" },
            bottom: { contigId: 30, role: "support", contigName: "support-bottom" },
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

  assert.match(
    html,
    /data-subview-fragment-role="phased"[^>]*data-subview-fragment-contig-id="2"[\s\S]*class="subview-fragment-outline"/,
  );
  assert.match(html, /data-subview-fragment-phased-track-item-id="9001"/);
  assert.match(
    html,
    /<rect\s+class="subview-fragment-hit-zone"[\s\S]*?data-subview-fragment-role="support"[\s\S]*?data-subview-fragment-contig-id="30"[\s\S]*?data-subview-fragment-start="1"[\s\S]*?data-subview-fragment-end="100"[\s\S]*?<title>support-bottom \| start=1 \| len=100<\/title>[\s\S]*?<\/rect>/,
  );
});

test("subview-track phased anchor fragments expose hoverable phased hit zones", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        isChrPhased: true,
        supportDatasetId: 22,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "phased-source",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [],
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 320,
            hits: [],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          activeAnchors: [{ hitKey: "pair-1", edge: "left" }],
          pairwiseEvidence: {
            key: "track-pair:phased:101:A:2|support:mother:22:30",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 2,
                subjectAssemblyCtgId: 30,
                queryStart: 500,
                queryEnd: 900,
                subjectStart: 1000,
                subjectEnd: 1400,
                strand: "+",
                alignLength: 400,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
            bottomTrack: { role: "support", source: "mother", datasetId: 22 },
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

  assert.match(
    html,
    /data-subview-fragment-role="phased"[^>]*data-subview-fragment-contig-id="2"[\s\S]*class="subview-fragment-outline"/,
  );
  assert.match(html, /data-subview-fragment-phased-track-item-id="9001"/);
  assert.match(
    html,
    /<rect\s+class="subview-fragment-hit-zone"[\s\S]*?data-subview-fragment-role="support"[\s\S]*?data-subview-fragment-contig-id="30"[\s\S]*?data-subview-fragment-start="1"[\s\S]*?data-subview-fragment-end="5000"[\s\S]*?<title>support-bottom \| start=1 \| len=5000<\/title>[\s\S]*?<\/rect>/,
  );
});

test("subview track-pair mode also renders active anchors and fragment hit zones", () => {
  const stablePairHitKey = "pair:30:hit-1:2:hit-1";
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
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          activeAnchors: [{ hitKey: stablePairHitKey, edge: "left" }],
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

  assert.match(
    html,
    /class="subview-anchor-line is-active"[^>]*stroke="red"[^>]*stroke-width="3"/,
  );
  assert.match(
    html,
    new RegExp(`class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="${stablePairHitKey}"[^>]*data-subview-anchor-edge="left"`),
  );
  assert.match(
    html,
    /data-subview-fragment-contig-id="30"[\s\S]*data-subview-fragment-contig-id="2"/,
  );
});

test("swapped subview track-pair keeps original evidence anchors active", () => {
  const previousOrderHitKey = "pair:30:hit-1:2:hit-1";
  const swappedOrderHitKey = "pair:2:hit-1:30:hit-1";
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-bottom",
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
            name: "primary-top",
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
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          activeAnchors: [{ hitKey: previousOrderHitKey, edge: "left" }],
          manualAnchors: [{
            manualAnchorId: "manual:primary:2500:support:2300",
            endpointA: { endpointKey: "role:primary:ctg:2:src:mother", contigId: 2, cutBp: 2500, lengthBp: 20000 },
            endpointB: { endpointKey: "role:support:ctg:30:ds:22:src:mother", contigId: 30, cutBp: 2300, lengthBp: 20000 },
          }],
          summary: {
            mode: "track-pair",
            topTrack: { role: "primary", source: "mother" },
            bottomTrack: { role: "support", source: "mother", datasetId: 22 },
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

  assert.match(
    html,
    new RegExp(`class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="${swappedOrderHitKey}"[^>]*data-subview-anchor-edge="left"`),
  );
  assert.match(
    html,
    /class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-kind="manual"/,
  );
});

test("track-pair anchors keep the same paired hit after alignment length changes", () => {
  const stablePairHitKey = "pair:30:hit-2:2:hit-2";
  const renderWithAlignmentLength = (alignmentLength) =>
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
              totalLength: 30000000,
              anchorStart: 320,
              hits: [
                { refStart: 2_000_000, refEnd: 2_050_000, ctgStart: 2_000_000, ctgEnd: 2_050_000, blockLength: 10_000, mapq: 60 },
                { refStart: 27_500_000, refEnd: 27_650_000, ctgStart: 26_800_000, ctgEnd: 26_950_000, blockLength: 150_000, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 2,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30000000,
              anchorStart: 100,
              hits: [
                { refStart: 2_010_000, refEnd: 2_060_000, ctgStart: 1_900_000, ctgEnd: 1_950_000, blockLength: 10_000, mapq: 60 },
                { refStart: 27_520_000, refEnd: 27_670_000, ctgStart: 27_100_000, ctgEnd: 27_250_000, blockLength: 150_000, mapq: 60 },
              ],
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 10000,
            maxTickCount: 5,
            alignmentLength,
            mapq: 0,
          },
          subview: {
            selectedTrackARole: "primary",
            selectedTrackBRole: "support",
            activeAnchors: [{ hitKey: stablePairHitKey, edge: "left" }],
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

  const strictHtml = renderWithAlignmentLength(100000);
  const relaxedHtml = renderWithAlignmentLength(10000);

  assert.match(strictHtml, new RegExp(`data-subview-hit-key="${stablePairHitKey}"`));
  assert.match(relaxedHtml, new RegExp(`data-subview-hit-key="${stablePairHitKey}"`));
  const bandMatch = relaxedHtml.match(new RegExp(`<polygon class="track-collinearity-band is-companion" points="([^"]+)"[^>]*data-subview-hit-key="${stablePairHitKey}"`));
  const lineMatch = relaxedHtml.match(new RegExp(`class="subview-anchor-line is-active"[^>]*x1="([^"]+)"[^>]*y1="([^"]+)"[^>]*x2="([^"]+)"[^>]*y2="([^"]+)"[\\s\\S]*data-subview-anchor-hit-key="${stablePairHitKey}"`));
  assert.ok(bandMatch, "expected anchored track-pair hit polygon");
  assert.ok(lineMatch, "expected active anchored line for the stable pair key");
  const [topLeft, , , bottomLeft] = bandMatch[1].split(" ");
  const [topLeftX, topBottomY] = topLeft.split(",").map(Number);
  const [bottomLeftX, bottomTopY] = bottomLeft.split(",").map(Number);
  assert.equal(Number(lineMatch[1]).toFixed(2), topLeftX.toFixed(2));
  assert.equal(Number(lineMatch[2]).toFixed(2), topBottomY.toFixed(2));
  assert.equal(Number(lineMatch[3]).toFixed(2), bottomLeftX.toFixed(2));
  assert.equal(Number(lineMatch[4]).toFixed(2), bottomTopY.toFixed(2));
});

test("subview chart keeps longer top bar when top ctg is longer than bottom ctg", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-long", assignedChrName: "Chr01", memberCount: 1, totalLength: 31000000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-short", assignedChrName: "Chr01", memberCount: 1, totalLength: 3096643, anchorStart: 100 },
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
            top: { contigId: 30, role: "support", contigName: "support-long" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-short" },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const barMatches = Array.from(
    subviewSvgMatch[0].matchAll(/<rect class="track-ctg([^"]*)"[^>]*width="([^"]+)"/g),
  );
  assert.equal(barMatches.length >= 2, true);
  const topWidth = Number(barMatches[0][2]);
  const bottomWidth = Number(barMatches[1][2]);
  assert.ok(
    topWidth > bottomWidth,
    `expected top bar width > bottom bar width, got top=${topWidth}, bottom=${bottomWidth}`,
  );
});

test("subview auto-shifts the shorter contig on first render so paired hits are closer to vertical", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30000,
            anchorStart: 320,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
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
            top: { contigId: 30, role: "support", contigName: "support-long" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-short" },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const rectMatches = Array.from(
    subviewSvgMatch[0].matchAll(/<rect class="track-ctg([^"]*)"[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*width="([^"]+)"/g),
  );
  assert.ok(rectMatches.length >= 2, "expected both subview contig bars");
  const topX = Number(rectMatches[0][2]);
  const bottomX = Number(rectMatches[1][2]);
  assert.equal(topX, 0, "expected the longer reference bar to stay anchored");
  assert.ok(bottomX > 700, `expected shorter bar to auto-shift right, got x=${bottomX}`);
});

test("max-scale subview keeps svg width equal to base inner width even with a right-edge overflow label", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30_000,
            anchorStart: 320,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 24_000, ctgEnd: 27_000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-short-right-edge-overflow-label-very-very-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          supportDsCtgLen: 0,
          minTickUnitKb: 10_000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
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
            top: { contigId: 30, role: "support", contigName: "support-long" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-short-right-edge-overflow-label-very-very-long" },
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

  const innerWidthMatch = html.match(
    /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-inner-width="([^"]+)"/,
  );
  assert.ok(innerWidthMatch, "expected subview base inner width");
  const innerWidth = Number(innerWidthMatch[1]);

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const svgWidthMatch = subviewSvgMatch[0].match(/<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected subview svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.equal(
    svgWidth,
    innerWidth,
    `expected max-scale subview svg width ${svgWidth} to match base inner width ${innerWidth}`,
  );
});

test("subview keeps automatic shorter-track alignment without exposing drag metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 401,
            name: "support-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 201,
            name: "primary-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 401,
          selectedARole: "support",
          selectedBContigId: 201,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 401, role: "support" },
            bottom: { contigId: 201, role: "primary" },
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

  assert.doesNotMatch(html, /data-subview-track-draggable=/);
  assert.doesNotMatch(html, /data-subview-track-offset-bp=/);
  assert.doesNotMatch(html, /data-subview-track-offset-source=/);
  assert.doesNotMatch(html, /manualTrackOffset/);
});

test("subview drag offsets move only subview bars and remain independent from main-view bars", () => {
  const sharedAssembly = {
    supportDatasetId: 22,
    supportChrCtgs: [
      {
        assemblyCtgId: 401,
        name: "support-short",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 5000,
        anchorStart: 320,
        hits: [
          { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
        ],
      },
    ],
    chrCtgs: [
      {
        assemblyCtgId: 201,
        name: "primary-long",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 30000,
        anchorStart: 100,
        hits: [
          { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
        ],
      },
    ],
    subviewTrackView: {
      minTickUnitKb: 10000,
      maxTickCount: 10,
      alignmentLength: 1000,
      mapq: 0,
    },
    subview: {
      mode: "2-contig",
      selectedAContigId: 401,
      selectedARole: "support",
      selectedBContigId: 201,
      selectedBRole: "primary",
      summary: {
        mode: "2-contig",
        top: { contigId: 401, role: "support" },
        bottom: { contigId: 201, role: "primary" },
      },
    },
  };
  const baseHtml = renderAssemblyPage(
    createState({
      assembly: {
        ...sharedAssembly,
        subviewTrackDragOffsets: [],
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
  const shiftedHtml = renderAssemblyPage(
    createState({
      assembly: {
        ...sharedAssembly,
        subviewTrackDragOffsets: [{ slot: "top", contigId: 401, offsetPx: 60 }],
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

  const extractSubviewSlotX = (html, slot) => {
    const match = html.match(new RegExp(`<g[^>]*data-subview-track-slot="${slot}"[^>]*data-subview-rect-x="([^"]+)"`));
    assert.ok(match, `expected subview ${slot} bar`);
    return Number(match[1]);
  };
  const extractMainTrackRectX = (html, trackRole, contigId) => {
    const match = html.match(
      new RegExp(`data-track-contig-id="${contigId}"[^>]*data-track-role="${trackRole}"[^>]*data-track-rect-x="([^"]+)"`),
    );
    assert.ok(match, `expected ${trackRole} track bar for ctg ${contigId}`);
    return Number(match[1]);
  };

  const baseTopX = extractSubviewSlotX(baseHtml, "top");
  const shiftedTopX = extractSubviewSlotX(shiftedHtml, "top");
  assert.ok(Math.abs((shiftedTopX - baseTopX) - 60) < 0.1, `expected subview top x shift by 60px, got ${shiftedTopX - baseTopX}`);

  const baseMainPrimaryX = extractMainTrackRectX(baseHtml, "primary", 201);
  const shiftedMainPrimaryX = extractMainTrackRectX(shiftedHtml, "primary", 201);
  assert.equal(shiftedMainPrimaryX, baseMainPrimaryX);

  const baseMainSupportX = extractMainTrackRectX(baseHtml, "support", 401);
  const shiftedMainSupportX = extractMainTrackRectX(shiftedHtml, "support", 401);
  assert.equal(shiftedMainSupportX, baseMainSupportX);
});

test("subview allows dragging the full-width longer ctg bar", () => {
  const buildHtml = (subviewTrackDragOffsets = []) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 401,
              name: "support-long",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30000,
              anchorStart: 320,
              hits: [
                { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 201,
              name: "primary-short",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 5000,
              anchorStart: 100,
              hits: [
                { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
              ],
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 10000,
            maxTickCount: 10,
            alignmentLength: 1000,
            mapq: 0,
          },
          subview: {
            mode: "2-contig",
            selectedAContigId: 401,
            selectedARole: "support",
            selectedBContigId: 201,
            selectedBRole: "primary",
            summary: {
              mode: "2-contig",
              top: { contigId: 401, role: "support" },
              bottom: { contigId: 201, role: "primary" },
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
  const extractTopX = (html) => {
    const match = html.match(
      /data-subview-track-slot="top"[\s\S]*?data-subview-contig-id="401"[\s\S]*?data-subview-rect-x="([^"]+)"/,
    );
    assert.ok(match, "expected full-width top subview bar");
    return Number(match[1]);
  };

  const baseTopX = extractTopX(buildHtml([]));
  const shiftedRightTopX = extractTopX(buildHtml([{ slot: "top", contigId: 401, offsetPx: 60 }]));
  const shiftedLeftTopX = extractTopX(buildHtml([{ slot: "top", contigId: 401, offsetPx: -60 }]));

  assert.ok(Math.abs((shiftedRightTopX - baseTopX) - 60) < 0.1, `expected full-width top x shift right by 60px, got ${shiftedRightTopX - baseTopX}`);
  assert.ok(Math.abs((shiftedLeftTopX - baseTopX) + 60) < 0.1, `expected full-width top x shift left by 60px, got ${shiftedLeftTopX - baseTopX}`);
});

test("subview collinearity pairing follows reference overlap instead of raw index order", () => {
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
            totalLength: 10000,
            anchorStart: 320,
            hits: [
              { refStart: 100, refEnd: 1100, ctgStart: 200, ctgEnd: 1200, blockLength: 1200, mapq: 60 },
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
            totalLength: 10000,
            anchorStart: 100,
            hits: [
              { refStart: 100, refEnd: 1100, ctgStart: 260, ctgEnd: 1260, blockLength: 1200, mapq: 60 },
              { refStart: 2500, refEnd: 2800, ctgStart: 9000, ctgEnd: 9300, blockLength: 1200, mapq: 60 },
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const svgMarkup = subviewSvgMatch[0];
  const svgWidthMatch = svgMarkup.match(/<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected subview svg width");
  const svgWidth = Number(svgWidthMatch[1]);
  const polygons = Array.from(
    svgMarkup.matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.equal(polygons.length, 2, "expected two paired subview bands");
  const secondBandPointList = polygons[1][1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const secondBandBottomStartX = secondBandPointList[3][0];
  assert.ok(
    secondBandBottomStartX < svgWidth * 0.6,
    `expected second band to pair with overlapping ref hit instead of far-right noise, got bottomStartX=${secondBandBottomStartX}, svgWidth=${svgWidth}`,
  );
});

test("subview bands skip non-overlapping hit pairs to avoid noisy cross-region links", () => {
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
            totalLength: 10000,
            anchorStart: 320,
            hits: [
              { refStart: 100, refEnd: 1200, ctgStart: 100, ctgEnd: 1200, blockLength: 1200, mapq: 60 },
              { refStart: 7000, refEnd: 8200, ctgStart: 2100, ctgEnd: 3300, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10000,
            anchorStart: 100,
            hits: [
              { refStart: 100, refEnd: 1200, ctgStart: 140, ctgEnd: 1240, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = Array.from(
    subviewSvgMatch[0].matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.equal(polygons.length, 1, "expected only one overlapping band");
});

test("subview ctg waits for pairwise evidence instead of inferring ds-ds bands from broad ref overlap", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-small",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 100, ctgEnd: 1300, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 40000,
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          pairwiseEvidence: {
            key: "2-contig:support:30:primary:2",
            status: "loading",
            hits: [],
          },
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-small" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-broad" },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  assert.doesNotMatch(
    subviewSvgMatch[0],
    /<polygon class="track-collinearity-band is-companion"/,
    "expected no inferred ds-ds band while true pairwise evidence is loading",
  );
  assert.match(html, /data-subview-pairwise-loading="1"/);
  assert.match(html, /data-subview-pairwise-cancel="1"/);
});

test("subview track-pair waits for pairwise evidence instead of inferring ds-ds bands from ref overlap", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 50000,
            anchorStart: 320,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 50000,
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|primary:2",
            status: "loading",
            hits: [],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22 },
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

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  assert.doesNotMatch(
    subviewSvgMatch[0],
    /<polygon class="track-collinearity-band is-companion"/,
    "expected no inferred ds-ds track-pair band while true pairwise evidence is loading",
  );
  assert.match(html, /data-subview-pairwise-loading="1"/);
  assert.match(html, /data-subview-pairwise-cancel="1"/);
});

test("cancelSubviewPairwiseEvidence reverts subview filters to the loaded cache floor", () => {
  let state = createState({
    assembly: {
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 5000,
        mapq: 0,
      },
      subview: {
        mode: "2-contig",
        summary: {
          mode: "2-contig",
          top: { contigId: 30, role: "support", contigName: "support-small" },
          bottom: { contigId: 2, role: "primary", contigName: "primary-broad" },
        },
        pairwiseEvidence: {
          key: "2-contig:support:30:primary:2",
          requestKey: "2-contig:support:30:primary:2|req:9",
          status: "loading",
          requestedMinAlignmentLength: 5000,
          requestedMinMapq: 0,
          loadedMinAlignmentLength: 10000,
          loadedMinMapq: 0,
          hits: [
            {
              queryAssemblyCtgId: 30,
              subjectAssemblyCtgId: 2,
              queryStart: 100,
              queryEnd: 1300,
              subjectStart: 20000,
              subjectEnd: 21200,
              alignLength: 1200,
              mapq: 60,
            },
          ],
        },
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  let rerenders = 0;

  const cancelled = __testCancelSubviewPairwiseEvidence({}, store, {
    rerender: () => {
      rerenders += 1;
    },
  });

  assert.equal(cancelled, true);
  assert.equal(store.getState().assembly.subviewTrackView.alignmentLength, 10000);
  assert.equal(store.getState().assembly.subviewTrackView.mapq, 0);
  assert.equal(store.getState().assembly.subview.pairwiseEvidence.status, "loaded");
  assert.equal(store.getState().assembly.subview.pairwiseEvidence.requestKey, "");
  assert.equal(rerenders, 1);
});
