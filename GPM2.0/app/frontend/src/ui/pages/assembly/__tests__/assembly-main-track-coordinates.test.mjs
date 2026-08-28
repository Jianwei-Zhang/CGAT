import {
  test,
  assert,
  renderAssemblyPage,
  createState,
} from "./tabs-semantics-harness.mjs";

test("assembly main view renders chr-length reference span, all guides, sparse ruler labels, and hit-filtered bands", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-zeta",
            assignedChrName: "Chr01",
            memberCount: 3,
            totalLength: 800,
            anchorStart: 900,
          },
          {
            assemblyCtgId: 2,
            name: "ctg-alpha",
            assignedChrName: "Chr01",
            memberCount: 5,
            totalLength: 900,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-beta",
            assignedChrName: "Chr01",
            memberCount: 2,
            totalLength: 999,
            anchorStart: 500,
            hits: [
              {
                ctgStart: 120,
                ctgEnd: 620,
                refStart: 1000,
                refEnd: 1500,
                blockLength: 500,
              },
              {
                ctgStart: 80,
                ctgEnd: 780,
                refStart: 250000,
                refEnd: 250700,
                blockLength: 1000,
              },
            ],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 3, placedBp: 3300, chrLength: 5000000 }],
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 700, anchorStart: 320 },
        ],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
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

  const mainTrackSvg = html.match(/<svg class="assembly-track-svg"[\s\S]*?<\/svg>/)?.[0] || "";
  const tickGuideCount = (mainTrackSvg.match(/track-tick-guide/g) || []).length;
  const tickLabelCount = (mainTrackSvg.match(/track-tick-label/g) || []).length;
  const bandCount = (html.match(/track-collinearity-band/g) || []).length;

  assert.match(html, /data-ref-span-bp="5000000"/);
  assert.match(html, /class="track-band-canvas-layer"[^>]*data-track-band-canvas-scene-kind="main-track"/);
  assert.match(html, /<canvas class="track-band-canvas"[^>]*data-track-band-canvas="1"/);
  assert.match(html, /<rect[\s\S]*class="track-reference-bar"[\s\S]*rx="0"[\s\S]*ry="0"/);
  assert.match(html, /track-collinearity-band[^>]*data-track-band-proxy="1"/);
  assert.equal(tickGuideCount, tickLabelCount + 1);
  assert.equal(tickLabelCount, 20);
  assert.match(html, /<text class="track-tick-label"[^>]*>0<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>250k<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>5,000,000 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,750k<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>50k<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>100k<\/text>/);
  assert.equal(bandCount, 1);
});

test("main-view history controls stay grouped after MAPQ and expose independent disabled states", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [{
          assemblyCtgId: 2,
          name: "ctg-alpha",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 900,
          anchorStart: 100,
        }],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 900 }],
        membersCardCollapsed: false,
        historyHighlightCtgId: 2,
        mainViewHistory: {
          chrName: "Chr01",
          canUndo: true,
          canRedo: false,
          canReset: true,
          undoOperation: { kind: "delete-ctg", targetCount: 3, targetName: "Chr01" },
          redoOperation: null,
          appliedOperationCount: 4,
          retainedOperationCount: 4,
          inFlight: false,
        },
      },
    }),
  );

  const mapqIndex = html.indexOf("assembly-track-mapq");
  const historyIndex = html.indexOf("main-view-history-controls");
  assert.ok(mapqIndex >= 0 && historyIndex > mapqIndex);
  assert.match(html, /data-main-history-action="undo"[^>]*title="回退：删除 3 个 ctg"/);
  assert.match(html, /data-main-history-action="redo"[^>]*disabled/);
  assert.match(html, /data-main-history-action="reset"[^>]*title="重置：撤销 Chr01 当前 4 项可逆编辑"/);
  assert.equal((html.match(/data-main-history-action=/g) || []).length, 3);
  assert.ok((html.match(/is-history-highlighted/g) || []).length >= 2);
});

test("full-chr ruler ticks stop at ref_chr end even when ctg extends beyond chr length", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-right-overflow",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600000,
            anchorStart: 4700000,
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 600000, chrLength: 4900000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  assert.match(html, /data-ref-span-bp="4900000"/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,500k<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>4,900,000 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>5M<\/text>/);
});

test("reference track renders a single ref member without gap markers when only one segment is present", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 12, chrLength: 12 }],
        refTrackMembers: [
          {
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-12",
            segmentStartBp: 1,
            segmentEndBp: 12,
            anchorStart: 1,
            totalLength: 12,
            refOrient: "+",
            hits: [],
          },
        ],
      },
    }),
  );

  assert.match(html, /class="track-reference-bar"/);
  assert.match(html, /class="track-reference-member"/);
  assert.match(html, /class="track-ctg-label track-reference-member-label is-ref"/);
  assert.doesNotMatch(html, /class="track-reference-gap-marker"/);
});

test("reference track renders multiple ref members with empty spacing for gap-aware references", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 10100, chrLength: 10100 }],
        refTrackMembers: [
          {
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-5000",
            segmentStartBp: 1,
            segmentEndBp: 5000,
            anchorStart: 1,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
          {
            sourceKind: "ref_segment",
            name: "ref_Chr01:5101-10100",
            segmentStartBp: 5101,
            segmentEndBp: 10100,
            anchorStart: 5101,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
        ],
      },
    }),
  );

  const memberCount = (html.match(/class="track-reference-member"/g) || []).length;
  const memberMatches = [...html.matchAll(
    /<rect[^>]*class="track-reference-member"[^>]*x="([^"]+)"[^>]*width="([^"]+)"[^>]*rx="([^"]+)"[^>]*ry="([^"]+)"/g,
  )];

  assert.doesNotMatch(html, /class="track-reference-bar"/);
  assert.equal(memberCount, 2);
  assert.doesNotMatch(html, /class="track-reference-gap-marker"/);
  assert.match(html, /ref_Chr01:1-5000/);
  assert.match(html, /ref_Chr01:5101-10100/);
  assert.equal(memberMatches.length, 2);
  assert.equal(memberMatches[0][3], "4");
  assert.equal(memberMatches[0][4], "4");
  const firstMemberX = Number(memberMatches[0][1]);
  const firstMemberWidth = Number(memberMatches[0][2]);
  const secondMemberX = Number(memberMatches[1][1]);
  const visibleGapPx = secondMemberX - (firstMemberX + firstMemberWidth);
  assert.ok(visibleGapPx >= 14.9, `expected ref member visible gap >= 15px, got ${visibleGapPx}`);
});

test("negative anchors do not shift viewport start when x layout is sequential", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 87,
            name: "ctg-left-overflow",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: -1000,
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  assert.match(html, /data-track-window-start-bp="0"/);
  assert.match(html, /<text class="track-tick-label"[^>]*>0<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>5,000 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>-1k<\/text>/);
  assert.match(html, /<line class="track-ruler-line" x1="0(?:\.00)?"/);
});

test("collinearity bands use real reference coordinates instead of reusing contig hit coordinates", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 87,
            name: "ctg-real-ref-band",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: -1000,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 400,
                refStart: 4000,
                refEnd: 4400,
                blockLength: 1200,
              },
            ],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  const match = html.match(/<polygon class="track-collinearity-band"[^>]*points="([^"]+)"/);
  assert.ok(match, "expected a rendered collinearity band");
  const points = match[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));
  const xValues = points.map(([x]) => x);

  assert.ok(xValues[0] > 900, `expected ref-left x to land on the right side, got ${xValues[0]}`);
  assert.ok(xValues[1] > xValues[0], "expected ref-right x to be to the right of ref-left");
  assert.ok(xValues[2] < 100, `expected ctg-right x to stay near the left edge, got ${xValues[2]}`);
  assert.ok(xValues[3] <= xValues[2], "expected ctg-left x to be left of ctg-right");
});

test("collinearity bands do not extend left of the visible ref track when hits start near zero", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 87,
            name: "ctg-left-ref-clamp",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: -1000,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 400,
                refStart: 1,
                refEnd: 100,
                blockLength: 1200,
              },
            ],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  const refBarMatch = html.match(/track-reference-bar"[\s\S]*?x="([^"]+)"/);
  assert.ok(refBarMatch, "expected a rendered reference bar");
  const refTrackX = Number(refBarMatch[1]);

  const bandMatch = html.match(/<polygon class="track-collinearity-band"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected a rendered collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));

  assert.ok(
    points[0][0] >= refTrackX,
    `expected ref-side left edge to stay within the visible ref track, got ${points[0][0]} < ${refTrackX}`,
  );
});

test("collinearity bands do not extend right of the visible ref track when hits end near chr end", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 4300000,
            hits: [],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000000 }],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-right-ref-clamp",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1500,
            anchorStart: 4300000,
            hits: [
              {
                ctgStart: 100,
                ctgEnd: 800,
                refStart: 4999800,
                refEnd: 5000000,
                blockLength: 1500,
              },
            ],
          },
        ],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
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

  const refBarMatch = html.match(/track-reference-bar"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/);
  assert.ok(refBarMatch, "expected a rendered reference bar");
  const refTrackRight = Number(refBarMatch[1]) + Number(refBarMatch[2]);

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected a rendered companion-track collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));
  const rightMostX = Math.max(...points.map(([x]) => x));

  assert.ok(
    rightMostX <= refTrackRight,
    `expected right-most band edge to stay within the visible ref track, got ${rightMostX} > ${refTrackRight}`,
  );
});

test("collinearity bands do not artificially widen tiny ref-edge hits", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 4300000,
            hits: [],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000000 }],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-tiny-edge-hit",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1500,
            anchorStart: 4300000,
            hits: [
              {
                ctgStart: 100,
                ctgEnd: 300,
                refStart: 4999800,
                refEnd: 5000000,
                blockLength: 1500,
              },
            ],
          },
        ],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
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

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected a rendered companion-track collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));
  const refEdgeWidth = points[2][0] - points[3][0];

  assert.ok(
    refEdgeWidth < 2,
    `expected tiny ref-edge hit to stay narrow, got widened top edge ${refEdgeWidth}`,
  );
});

test("end tick keeps k-unit label and hides previous label when text overlaps", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-end-overlap",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 200000,
            anchorStart: 4600000,
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 200000, chrLength: 4899999 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
        },
      },
    }),
  );

  const tickGuideCount = (html.match(/track-tick-guide/g) || []).length;
  const tickLabelCount = (html.match(/track-tick-label/g) || []).length;

  assert.match(html, /data-ref-span-bp="4899999"/);
  assert.match(html, /<text class="track-tick-label"[^>]*>4,899,999 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,750k<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,899,999<\/text>/);
  assert.equal(tickGuideCount, tickLabelCount + 1);
});
