import {
  test,
  assert,
  readStylesheetTree,
  bindAssemblyPageImpl,
  __testRerenderBatchDeleteProgress,
  __testResolveAppendToPathFocusPatch,
  renderAssemblyPage,
  createState,
  createStore,
} from "./tabs-semantics-harness.mjs";

test("assembly main view renders the persisted final path card for the current chr", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
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
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "flye_ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /final-path-track-min-tick-unit-kb/);
  assert.match(html, /final-path-track-max-tick-count/);
  assert.match(html, /assembly-final-path-layout/);
  assert.match(html, /assembly-final-path-svg-wrap/);
  assert.match(html, /assembly-final-path-svg/);
  assert.match(html, /track-ruler-line/);
  assert.match(html, /track-tick-guide/);
  assert.match(html, /track-ctg-group/);
  assert.match(html, /flye_ctg9/);
  assert.match(html, /data-final-path-export-toggle="true"/);
  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.match(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("final path graph hides labels that do not fit inside bars and keeps hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
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
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "final-path-very-long-segment-label",
                overallLen: 1_000,
                start: 1,
                end: 1_000,
              },
              {
                segmentId: "gap-1",
                type: "gap",
                gapSizeBp: 499_000,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*"[^>]*>final-path-very-long-segment-label \(\+\)<\/text>/);
  assert.match(html, /<title>final-path-very-long-segment-label \|/);
});

test("assembly main view keeps final path all export while hiding fasta when project dataset fasta is unavailable", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        datasets: [
          { datasetId: 3, name: "flye", label: "flye", fastaAvailable: false },
        ],
        existingProjects: [
          {
            projectId: 7,
            projectName: "projA",
            primaryDatasetId: 3,
            supportDatasetIds: [],
          },
        ],
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
                assemblyCtgId: 9,
                datasetName: "flye",
                ctgName: "ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.doesNotMatch(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("assembly main view keeps final path fasta export visible for full partitioned delivery packages", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        packageMetadata: {
          packageMode: "fast",
          sequenceLayout: "partitioned",
          preassignedChr: true,
          chrAssignmentMinCoveragePercent: 60,
          selfAlignmentScope: "chr_partition",
          crossAlignmentScope: "chr_partition",
        },
        datasets: [
          { datasetId: 3, name: "flye", label: "flye", fastaAvailable: true },
        ],
        existingProjects: [
          {
            projectId: 7,
            projectName: "projA",
            primaryDatasetId: 3,
            supportDatasetIds: [],
          },
        ],
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
                assemblyCtgId: 9,
                datasetName: "flye",
                ctgName: "ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.match(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("assembly main view renders an empty final path card for the current chr without persisted rows", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {},
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.match(html, /assembly-final-path-svg-wrap/);
  assert.match(html, /data-final-path-export-toggle="true"/);
});

test("phased mode final path card defaults to all haplotypes and omits the parent path card", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [{ segmentId: "parent", type: "gap", gapSizeBp: 100 }],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /data-phased-final-path-key="__all__"/);
  assert.match(html, /data-phased-final-path-current-key="__all__"/);
  assert.match(html, />All <span aria-hidden="true">/);
  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*data-final-path-all-card="Chr01B"/);
  assert.doesNotMatch(html, /projA_Chr01 path/);
  assert.match(html, /data-phased-final-path-key="A"/);
  assert.match(html, /data-phased-final-path-key="B"/);
  assert.match(html, /data-phased-final-path-chr-name="Chr01B"/);
  assert.match(html, /data-final-path-remove-row="hap-b"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01B"[\s\S]*data-final-path-remove-row="hap-b"/);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*>Chr01A<\/div>[\s\S]*class="final-path-card-list-head"[\s\S]*>Chr01B<\/div>/);
});

test("phased mode final path card can select one haplotype independently of the main phased track", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        activePhasedTrackKey: "A",
        activeFinalPathKey: "B",
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [{ segmentId: "hap-a", type: "gap", gapSizeBp: 100 }],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /data-phased-final-path-current-key="B"/);
  assert.match(html, />B <span aria-hidden="true">/);
  assert.match(html, /projA_Chr01B path/);
  assert.doesNotMatch(html, /projA_Chr01A path/);
  assert.match(html, /data-final-path-remove-row="hap-b"/);
});

test("append-to-phased-path focus patch switches single final path selection to the target haplotype", () => {
  const patch = __testResolveAppendToPathFocusPatch(
    {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "B",
      activeFinalPathKeyByChr: {
        Chr01: "B",
      },
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A" },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B" },
      ],
    },
    "A",
  );

  assert.deepEqual(patch, {
    activeFinalPathKey: "A",
    activeFinalPathKeyByChr: {
      Chr01: "A",
    },
  });
});

test("append-to-phased-path focus patch preserves all final path selection", () => {
  const patch = __testResolveAppendToPathFocusPatch(
    {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "__all__",
      activeFinalPathKeyByChr: {
        Chr01: "__all__",
      },
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A" },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B" },
      ],
    },
    "A",
  );

  assert.deepEqual(patch, {});
});

test("phased all final path graph renders haplotype labels in the graph label column", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [{ segmentId: "hap-a", type: "gap", gapSizeBp: 100 }],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*data-final-path-all-graph-label="Chr01A"/);
  assert.match(html, /data-final-path-all-card="Chr01B"[\s\S]*data-final-path-all-graph-label="Chr01B"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01A"[\s\S]*data-final-path-segment-id="hap-a"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01B"[\s\S]*data-final-path-segment-id="hap-b"/);
});

test("phased all Graph view renders one DEGAP jobs card under each haplotype that has jobs", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [
              { segmentId: "a-left", type: "ctg", assemblyCtgId: 2, datasetName: "hifiasm", ctgName: "A-left", overallLen: 100, start: 1, end: 100 },
              { segmentId: "gap-a", type: "gap", gapSizeBp: 20 },
              { segmentId: "a-right", type: "ctg", assemblyCtgId: 8, datasetName: "hifiasm", ctgName: "A-right", overallLen: 100, start: 1, end: 100 },
            ],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [
              { segmentId: "b-left", type: "ctg", assemblyCtgId: 12, datasetName: "hifiasm", ctgName: "B-left", overallLen: 100, start: 1, end: 100 },
              { segmentId: "gap-b", type: "gap", gapSizeBp: 20 },
              { segmentId: "b-right", type: "ctg", assemblyCtgId: 18, datasetName: "hifiasm", ctgName: "B-right", overallLen: 100, start: 1, end: 100 },
            ],
          },
        },
        finalPathViewMode: "degap",
        degap: {
          settingsPanelDismissed: true,
          jobs: [
            {
              jobId: "B-left_vs_B-right_Left-job",
              label: "B-left_vs_B-right Left-job",
              chrName: "Chr01B",
              gapSegmentId: "gap-b",
              gapIndex: 2,
              side: "left",
              leftCtg: "B-left",
              rightCtg: "B-right",
              outPath: "/srv/degap/B-left_vs_B-right_Left-job",
              baselineOutPath: "/srv/degap/B-left_vs_B-right_Left-job",
              left: { assemblyCtgId: 12, start: 1, end: 100 },
              right: { assemblyCtgId: 18, start: 1, end: 100 },
              baselineSettings: {
                degapPath: "/opt/DEGAP/bin/DEGAP.py",
                hifiReads: ["/reads/a.fq.gz"],
                gpmServerPath: "/srv/gpm_server",
                outRoot: "/srv/degap",
              },
            },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.doesNotMatch(html, /data-final-path-view-mode="degap"/);
  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*data-final-path-all-graph-label="Chr01A"/);
  assert.match(html, /data-final-path-all-card="Chr01B"[\s\S]*data-final-path-all-graph-label="Chr01B"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01A"[\s\S]*data-final-path-segment-id="gap-a"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01B"[\s\S]*data-final-path-segment-id="gap-b"/);
  const chrAStart = html.indexOf('data-final-path-all-card="Chr01A"');
  const chrBStart = html.indexOf('data-final-path-all-card="Chr01B"');
  assert.ok(chrAStart >= 0 && chrBStart > chrAStart);
  assert.doesNotMatch(html.slice(chrAStart, chrBStart), /data-degap-job-card/);
  assert.match(html.slice(chrBStart), /data-final-path-segment-id="gap-b"[\s\S]*data-degap-job-card[\s\S]*data-degap-job-card-chr-name="Chr01B"[\s\S]*B-left_vs_B-right Left-job/);
});

test("phased all final path log renders one titled log card per haplotype", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [
              {
                segmentId: "hap-a",
                type: "ctg",
                assemblyCtgId: 2,
                datasetName: "hifiasm",
                ctgName: "ctg-alpha",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [
              {
                segmentId: "hap-b",
                type: "ctg",
                assemblyCtgId: 8,
                datasetName: "hifiasm",
                ctgName: "ctg-beta",
                overallLen: 600,
                start: 1,
                end: 600,
              },
            ],
          },
        },
        finalPathViewMode: "log",
      },
    }),
  );

  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*class="final-path-all-card-title">Chr01A<\/strong>/);
  assert.match(html, /data-final-path-all-card="Chr01B"[\s\S]*class="final-path-all-card-title">Chr01B<\/strong>/);
  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*final-path-log-body[\s\S]*data-final-path-all-card="Chr01B"[\s\S]*final-path-log-body/);
});

test("assembly main view renders a placeholder row for an empty final path in table mode", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {},
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /data-final-path-view-mode="table"/);
  assert.match(html, /data-final-path-empty-row="true"/);
  assert.match(html, /data-final-path-export-toggle="true"/);
});

test("assembly main view renders ref final-path rows as fixed-name bounded segments in table mode", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
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
                sourceKind: "ref_segment",
                assemblyCtgId: 9001,
                referenceChrId: 1,
                referenceChrName: "Chr01",
                datasetName: "",
                ctgName: "ref_Chr01:5201-5600",
                originId: "Chr01",
                overallLen: 5000,
                memberStartBp: 5101,
                memberEndBp: 10100,
                start: 101,
                end: 500,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /data-final-path-cell="ctg"[^>]*value="ref_Chr01:5201-5600"[^>]*disabled/);
  assert.match(html, /data-final-path-cell="start"[^>]*value="101"/);
  assert.match(html, /data-final-path-cell="end"[^>]*value="500"/);
});

test("assembly page renders a blocking final-path export modal when export job is open", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        finalPathExportJob: {
          open: true,
          kind: "all",
          chrName: "Chr01",
          status: "running",
          currentStep: "导出图(.png)",
          completedOutputs: [],
          cancelRequested: false,
          error: "",
          steps: [
            { kind: "png", label: "图(.png)", outputPath: "a.png" },
            { kind: "tsv", label: "表(.tsv)", outputPath: "a.tsv" },
            { kind: "fasta", label: "序列(.fasta)", outputPath: "a.fasta" },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-final-path-export-modal="true"/);
  assert.match(html, /data-final-path-export-overlay="true"/);
  assert.match(html, /正在导出 Final Path/);
  assert.match(html, /Chr01/);
  assert.match(html, /data-final-path-export-step-status="running"/);
  assert.match(html, /class="pipeline-spinner"/);
  assert.match(html, /图\(.png\)/);
  assert.match(html, /表\(.tsv\)/);
  assert.match(html, /序列\(.fasta\)/);
  assert.match(html, /data-final-path-export-close="true"/);
});

test("assembly page renders a blocking batch-delete progress modal", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        batchDeleteProgress: {
          open: true,
          current: 1,
          total: 2,
          items: [
            { assemblyCtgId: 2, label: "ctg-alpha", status: "success" },
            { assemblyCtgId: 8, label: "ctg-beta", status: "running" },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-batch-delete-progress-modal="true"/);
  assert.match(html, /批量删除进度/);
  assert.match(html, /1\/2/);
  assert.match(html, /ctg-alpha/);
  assert.match(html, /assembly_ctg_id=2/);
  assert.match(html, /ctg-beta/);
  assert.match(html, /assembly_ctg_id=8/);
  assert.match(html, /pipeline-done/);
  assert.match(html, /pipeline-spinner/);
});

test("assembly page renders add_ctg import progress modal", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        addCtgImportProgress: {
          open: true,
          status: "running",
          summary: "正在导入 add_ctg 包。",
          stages: [
            { label: "index_ref_paf", progressIndex: 2, progressTotal: 4 },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-add-ctg-import-progress-overlay="true"/);
  assert.match(html, /add_ctg 导入进度/);
  assert.match(html, /index_ref_paf \(2\/4\)/);
  assert.match(html, /2\/4/);
  assert.match(html, /pipeline-spinner/);
});

test("add_ctg import progress meter includes frontend stages after backend completion", () => {
  const backendStages = Array.from({ length: 45 }, (_, index) => ({
    label: index === 44 ? "complete" : `backend_stage_${index + 1}`,
    progressIndex: index + 1,
    progressTotal: 45,
  }));
  const html = renderAssemblyPage(
    createState({
      assembly: {
        addCtgImportProgress: {
          open: true,
          status: "success",
          summary: "add_ctg 包导入完成。",
          stages: [
            "workspace_root=/tmp/workspace",
            "project_id=1",
            "target=Chr01/hifiasm",
            "add_ctg_zip_path=/tmp/add.zip",
            "调用后端 import_add_ctg_package",
            ...backendStages,
            "刷新当前 chr 视图",
          ],
        },
      },
    }),
  );

  assert.match(html, /class="import-progress-meter" aria-label="51\/51"/);
  assert.match(html, /刷新当前 chr 视图 \(51\/51\)/);
});

test("derived ctg source tags render in track labels and primary member cards", () => {
  const html = renderAssemblyPage(
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
      assembly: {
        membersCardCollapsed: false,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "gap_filled",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 45_000_000,
            anchorStart: 100,
            derivedSource: "gapfiller",
            derivedTargetDatasetId: 11,
            derivedTargetDatasetName: "hifiasm",
          },
        ],
      },
    }),
  );

  assert.match(html, /track-ctg-source-tag is-source-gapfiller[^>]*> \[gapfiller\]<\/tspan>/);
  assert.match(html, /ctg-chip-source-tag is-source-gapfiller[^>]*>\[gapfiller\]<\/span>/);
});

test("batch delete progress modal closes even when the action host was detached", () => {
  let removed = false;
  const overlay = {
    remove() {
      removed = true;
    },
  };
  let routeHost = null;
  const doc = {
    createElement() {
      return {
        innerHTML: "",
        content: {
          firstElementChild: null,
        },
      };
    },
    querySelector(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  routeHost = {
    ownerDocument: doc,
    querySelector(selector) {
      return selector === "[data-batch-delete-progress-overlay='true']" ? overlay : null;
    },
  };
  const detachedHost = {
    ownerDocument: doc,
    closest() {
      return null;
    },
    querySelector() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        batchDeleteProgress: null,
      },
    }),
  );

  __testRerenderBatchDeleteProgress(detachedHost, store);

  assert.equal(removed, true);
});

test("batch delete progress modal close removes stale overlays outside the route host", () => {
  const removed = [];
  const staleOverlay = {
    remove() {
      removed.push("stale");
    },
  };
  let routeHost = null;
  const doc = {
    createElement() {
      return {
        innerHTML: "",
        content: {
          firstElementChild: null,
        },
      };
    },
    querySelector(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
    querySelectorAll(selector) {
      return selector === "[data-batch-delete-progress-overlay='true']" ? [staleOverlay] : [];
    },
  };
  routeHost = {
    ownerDocument: doc,
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const detachedHost = {
    ownerDocument: doc,
    closest() {
      return null;
    },
    querySelector() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        batchDeleteProgress: null,
      },
    }),
  );

  __testRerenderBatchDeleteProgress(detachedHost, store);

  assert.deepEqual(removed, ["stale"]);
});

test("assembly page renders completed export steps with a check mark icon", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        finalPathExportJob: {
          open: true,
          kind: "all",
          chrName: "Chr01",
          status: "success",
          currentStep: "序列(.fasta)",
          completedOutputs: ["a.png", "a.tsv", "a.fasta"],
          cancelRequested: false,
          error: "",
          steps: [
            { kind: "png", label: "图(.png)", outputPath: "a.png" },
            { kind: "tsv", label: "表(.tsv)", outputPath: "a.tsv" },
            { kind: "fasta", label: "序列(.fasta)", outputPath: "a.fasta" },
          ],
        },
      },
    }),
  );

  assert.match(html, /class="assembly-final-path-export-body"/);
  assert.match(html, /data-final-path-export-step-status="done"/);
  assert.match(html, /class="pipeline-done"/);
  assert.match(html, /class="muted assembly-final-path-export-status success"/);
  assert.match(html, /&#10003;/);
});

test("export dialog css centers its content block and keeps step icons pinned on the right", () => {
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-final-path-export-dialog\s*\{[^}]*width:\s*min\(680px,\s*calc\(100vw - 64px\)\);/);
  assert.match(css, /\.assembly-final-path-export-dialog\s*\{[^}]*padding:\s*28px 32px;/);
  assert.match(css, /\.assembly-final-path-export-body\s*\{[^}]*width:\s*min\(100%,\s*560px\);/);
  assert.match(css, /\.assembly-final-path-export-body\s*\{[^}]*margin:\s*0 auto 0 24px;/);
  assert.match(css, /\.assembly-final-path-export-step\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+20px;/);
  assert.match(css, /\.assembly-final-path-export-step\s*\{[^}]*width:\s*100%;/);
  assert.match(css, /\.pipeline-step-label\s*\{[^}]*white-space:\s*nowrap;/);
  assert.match(css, /\.pipeline-step-icon\s*\{[^}]*justify-self:\s*end;/);
  assert.match(css, /\.assembly-final-path-export-status\.success\s*\{[^}]*color:\s*#2c6b2f;/);
});

test("bindings commit edits from the editable empty final-path row", async () => {
  const listenerMap = new Map();
  const emptyCtgInput = {
    value: "flye_Ctg30",
    dataset: {
      finalPathEmptyCell: "ctg",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-empty-cell]") {
        return [emptyCtgInput];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {},
        finalPathViewMode: "table",
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
  deps.createEmptyFinalPathRow = async (_host, _store, payload) => {
    calls.push(payload);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("change")?.();

  assert.deepEqual(calls, [{ field: "ctg", value: "flye_Ctg30" }]);
});

test("bindings send final-path orient edits through updateFinalPathRow", async () => {
  const listenerMap = new Map();
  const orientSelect = {
    value: "-",
    dataset: {
      finalPathCell: "orient",
      finalPathSegmentId: "seg-1",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-cell][data-final-path-segment-id]") {
        return [orientSelect];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
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
        finalPathViewMode: "table",
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
    "createEmptyFinalPathRow",
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
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.updateFinalPathRow = async (_host, _store, payload) => {
    calls.push(payload);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("change")?.();

  assert.deepEqual(calls, [{ segmentId: "seg-1", field: "orient", value: "-" }]);
});

test("bindings preserve all-mode final-path target chr on table edits", async () => {
  const listenerMap = new Map();
  const input = {
    value: "ctg-alpha",
    dataset: {
      finalPathCell: "ctg",
      finalPathSegmentId: "seg-a",
      finalPathTargetChrName: "Chr01A",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-cell][data-final-path-segment-id]") {
        return [input];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState({ assembly: { finalPathViewMode: "table" } }));
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
    "createEmptyFinalPathRow",
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
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.updateFinalPathRow = async (_host, _store, payload) => {
    calls.push(payload);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("change")?.();

  assert.deepEqual(calls, [
    { segmentId: "seg-a", field: "ctg", value: "ctg-alpha", targetChrName: "Chr01A" },
  ]);
});
