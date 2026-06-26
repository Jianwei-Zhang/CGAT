import test from "node:test";
import assert from "node:assert/strict";

import { renderAssemblyPage } from "../../assembly-page.js";

function createState(overrides = {}) {
  return {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
      projectName: "p1",
    },
    initializer: {
      datasets: [
        { datasetId: 1, name: "hifiasm" },
        { datasetId: 2, name: "flye" },
      ],
      existingProjects: [
        {
          projectId: 7,
          name: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [2],
          autoPipelineDone: true,
          fastaAvailable: true,
        },
      ],
    },
    assembly: {
      loading: false,
      activeTab: "assembly",
      summary: "",
      selectedChrName: "Chr01",
      selectedCtgId: null,
      chromosomes: [
        { chrName: "Chr01", chrOrder: 1, chrLength: 100000, ctgCount: 2, placedBp: 2000 },
      ],
      chrPickerOpen: false,
      chrCtgs: [
        {
          assemblyCtgId: 101,
          name: "primary_ctg",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1000,
          anchorStart: 1,
          refOrient: "+",
          telomereMarks: [
            {
              ruleId: "tel1",
              motif: "TTAGGG",
              minRepeat: 20,
              repeatCount: 21,
              startBp: 101,
              endBp: 226,
              strand: "+",
              ctgStart: 101,
              ctgEnd: 226,
            },
            {
              ruleId: "tel2",
              motif: "TTTAGGG",
              minRepeat: 20,
              repeatCount: 71,
              startBp: 994,
              endBp: 1000,
              strand: "+",
              ctgStart: 994,
              ctgEnd: 1000,
            },
          ],
          centromereMarks: [
            {
              cenId: "cen",
              queryName: "Chr01_centromere",
              startBp: 300,
              endBp: 620,
              strand: "+",
              alignLength: 321,
              identity: 96.5,
              mapq: 60,
              ctgStart: 300,
              ctgEnd: 620,
            },
          ],
          nRegions: [
            {
              startBp: 480,
              endBp: 484,
              lengthBp: 5,
              ctgStart: 480,
              ctgEnd: 484,
            },
          ],
          hits: [],
        },
      ],
      supportDatasetId: 2,
      supportChrCtgs: [
        {
          assemblyCtgId: 202,
          name: "support_ctg",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1000,
          anchorStart: 1,
          refOrient: "+",
          telomereMarks: [
            {
              ruleId: "tel1",
              motif: "TTAGGG",
              minRepeat: 20,
              repeatCount: 22,
              startBp: 10,
              endBp: 140,
              strand: "+",
              ctgStart: 10,
              ctgEnd: 140,
            },
          ],
          centromereMarks: [
            {
              cenId: "cen",
              queryName: "Chr01_centromere",
              startBp: 300,
              endBp: 620,
              strand: "+",
              alignLength: 321,
              identity: 96.5,
              mapq: 60,
              ctgStart: 300,
              ctgEnd: 620,
            },
          ],
          nRegions: [
            {
              startBp: 20,
              endBp: 24,
              lengthBp: 5,
              ctgStart: 20,
              ctgEnd: 24,
            },
          ],
          hits: [],
        },
      ],
      refTrackMembers: [],
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
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
      finalPathByChr: {},
      finalPathViewMode: "graph",
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      supportMirroredCtgs: [],
      trackScrollState: {},
      subviewTrackScrollState: {},
      finalPathTrackScrollState: {},
      subview: {},
      newSequences: { loading: false, error: "", items: [] },
      error: "",
      actionStatus: "",
      actionError: "",
      junctionLoading: false,
      junctionStatus: "",
      junctionError: "",
      junctionReport: null,
    },
    ...overrides,
  };
}

test("assembly main track renders telomere markers only on primary ctg bars", () => {
  const html = renderAssemblyPage(createState());

  assert.match(html, /data-telomere-marker="1"/);
  assert.match(html, /data-telomere-rule-id="tel1"/);
  assert.match(html, /data-telomere-motif="TTAGGG"/);
  assert.match(html, /data-telomere-contig-id="101"/);
  assert.match(html, /TTAGGG\|repeat=21\|range=101-226\|strand=\+/);
  assert.doesNotMatch(html, /data-telomere-contig-id="202"/);
});

test("assembly telomere markers keep an inspectable width at the ctg edge", () => {
  const html = renderAssemblyPage(createState());
  const markerMatch = html.match(/data-telomere-rule-id="tel2"[\s\S]*?width="([0-9.]+)"/);

  assert.ok(markerMatch, "expected edge telomere marker to render");
  assert.ok(Number(markerMatch[1]) >= 6, `expected edge marker width >= 6, got ${markerMatch[1]}`);
  assert.match(html, /TTTAGGG\|repeat=71\|range=994-1000\|strand=\+/);
});

test("assembly main track renders centromere markers only on primary ctg bars", () => {
  const html = renderAssemblyPage(createState());

  assert.match(html, /data-centromere-marker="1"/);
  assert.match(html, /data-centromere-cen-id="cen"/);
  assert.match(html, /data-centromere-query-name="Chr01_centromere"/);
  assert.match(html, /data-centromere-contig-id="101"/);
  assert.match(html, /cen\|range=300-620\|identity=96.5\|strand=\+/);
  assert.doesNotMatch(html, /data-centromere-contig-id="202"/);
});

test("assembly tracks render n region markers with inspectable width and tab tooltip", () => {
  const html = renderAssemblyPage(createState());

  assert.match(html, /data-n-region-marker="1"/);
  assert.match(html, /data-n-region-contig-id="101"/);
  assert.match(html, /data-n-region-contig-id="202"/);
  assert.match(html, /N\t480-484\t5/);
  const markerMatch = html.match(/data-n-region-contig-id="101"[\s\S]*?width="([0-9.]+)"/);
  assert.ok(markerMatch, "expected primary n region marker to render");
  assert.ok(Number(markerMatch[1]) >= 6, `expected n marker width >= 6, got ${markerMatch[1]}`);
});
