import test from "node:test";
import assert from "node:assert/strict";

import {
  __testNormalizeWorkflowError,
  addCtgToPhasedChrTrack,
  createPhasedChrTrack,
  deleteProject,
  deletePhasedChrTrack,
  exportDegapJobs,
  exportFinalPathFasta,
  exportProjectFinalPathFasta,
  initializeProject,
  listPhasedChrTracks,
  listProjectInitializerOptions,
  openWorkspace,
  removePhasedChrTrackItem,
  reorderPhasedChrTrackItems,
  runCtgEditorAction,
  setProjectAutoPipelineDone,
  updateProject,
  writeFinalPathExportBinaryFile,
  writeFinalPathExportTextFile,
} from "../workflow-api.js";

test("preserves semantics for plain object throws", () => {
  const normalized = __testNormalizeWorkflowError(
    {
      code: "INVALID_PARAMS",
      message: "project_id must be provided",
      detail: "project_id is required",
      data: {
        code: "INVALID_PARAMS",
        detail: "project_id is required",
      },
      source: "dev-bridge",
      operation: "/api/list-project-chromosomes",
    },
    {
      code: "DEV_BRIDGE_ERROR",
      source: "dev-bridge",
      operation: "/api/fallback",
    },
  );

  assert.equal(normalized.message, "project_id must be provided");
  assert.equal(normalized.code, "INVALID_PARAMS");
  assert.equal(normalized.detail, "project_id is required");
  assert.equal(normalized.source, "dev-bridge");
  assert.equal(normalized.operation, "/api/list-project-chromosomes");
  assert.deepEqual(normalized.data, {
    code: "INVALID_PARAMS",
    detail: "project_id is required",
  });
});

test("preserves nested data semantics for Error throws", () => {
  const error = new Error("ctg not found");
  error.data = {
    code: "NOT_FOUND",
    detail: "assembly_ctg_id=42",
  };

  const normalized = __testNormalizeWorkflowError(error, {
    code: "TAURI_INVOKE_ERROR",
    source: "tauri",
    operation: "get_ctg_detail",
  });

  assert.equal(normalized.message, "ctg not found");
  assert.equal(normalized.code, "NOT_FOUND");
  assert.equal(normalized.detail, "assembly_ctg_id=42");
  assert.equal(normalized.source, "tauri");
  assert.equal(normalized.operation, "get_ctg_detail");
  assert.deepEqual(normalized.data, {
    code: "NOT_FOUND",
    detail: "assembly_ctg_id=42",
  });
});

test("writeFinalPathExportTextFile routes text payload through the tauri command", async () => {
  const previousWindow = globalThis.window;
  const calls = [];
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            return { ok: true };
          },
        },
      },
    };

    await writeFinalPathExportTextFile({
      outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.tsv",
      text: "hello",
    });
  } finally {
    globalThis.window = previousWindow;
  }

  assert.equal(calls[0].command, "write_final_path_export_text_file");
  assert.equal(calls[0].args.outputPath, "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.tsv");
  assert.equal(calls[0].args.text, "hello");
});

test("writeFinalPathExportBinaryFile routes bytes payload through the tauri command", async () => {
  const previousWindow = globalThis.window;
  const calls = [];
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            return { ok: true };
          },
        },
      },
    };

    await writeFinalPathExportBinaryFile({
      outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.png",
      bytesBase64: "YWJj",
    });
  } finally {
    globalThis.window = previousWindow;
  }

  assert.equal(calls[0].command, "write_final_path_export_binary_file");
  assert.equal(calls[0].args.outputPath, "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.png");
  assert.equal(calls[0].args.bytesBase64, "YWJj");
});

test("exportFinalPathFasta routes the current finalPathEntry through the tauri command", async () => {
  const previousWindow = globalThis.window;
  const calls = [];
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            return { outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.fasta" };
          },
        },
      },
    };

    await exportFinalPathFasta({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      chrName: "Chr01",
      finalPathEntry: { chrName: "Chr01", segments: [] },
      outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.fasta",
    });
  } finally {
    globalThis.window = previousWindow;
  }

  assert.equal(calls[0].command, "export_final_path_fasta");
  assert.equal(calls[0].args.workspaceRoot, "D:\\Desktop\\GPM\\ws1");
  assert.equal(calls[0].args.projectId, 7);
  assert.equal(calls[0].args.chrName, "Chr01");
  assert.deepEqual(calls[0].args.finalPathEntry, { chrName: "Chr01", segments: [] });
  assert.equal(calls[0].args.outputPath, "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.fasta");
});

test("exportProjectFinalPathFasta routes the merged finalPathByChr through the tauri command", async () => {
  const previousWindow = globalThis.window;
  const calls = [];
  const finalPathByChr = {
    Chr01: { chrName: "Chr01", segments: [] },
    Chr02: { chrName: "Chr02", segments: [] },
  };
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            return { outputPath: "D:\\Desktop\\GPM\\exports\\project1_project_path.fasta" };
          },
        },
      },
    };

    await exportProjectFinalPathFasta({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      finalPathByChr,
      outputPath: "D:\\Desktop\\GPM\\exports\\project1_project_path.fasta",
    });
  } finally {
    globalThis.window = previousWindow;
  }

  assert.equal(calls[0].command, "export_project_final_path_fasta");
  assert.equal(calls[0].args.workspaceRoot, "D:\\Desktop\\GPM\\ws1");
  assert.equal(calls[0].args.projectId, 7);
  assert.deepEqual(calls[0].args.finalPathByChr, finalPathByChr);
  assert.equal(calls[0].args.outputPath, "D:\\Desktop\\GPM\\exports\\project1_project_path.fasta");
});

test("exportDegapJobs uses the dev bridge when tauri is unavailable", async () => {
  const previousWindow = globalThis.window;
  const previousFetch = globalThis.fetch;
  const settings = {
    degapPath: "/opt/DEGAP/bin/DEGAP.py",
    hifiReads: ["/reads/a.fq.gz"],
    gpmServerPath: "/srv/gpm",
    outRoot: "/srv/degap/main",
  };
  const jobs = [
    {
      jobType: "gapfiller",
      jobId: "Chr05_A_B_left",
      leftCtg: "A",
      rightCtg: "B",
      flag: "left",
      outPath: "/srv/degap/job1",
      left: { assemblyCtgId: 11, start: 1, end: 100 },
      right: { assemblyCtgId: 12, start: 1, end: 100 },
    },
  ];
  const calls = [];
  try {
    globalThis.window = {};
    globalThis.fetch = async (path, options) => {
      calls.push({ path, options });
      return {
        ok: true,
        json: async () => ({
          outputDir: "D:\\Desktop\\GPM\\exports\\degap",
          manifestPath: "D:\\Desktop\\GPM\\exports\\degap\\jobs.tsv",
          prepareScriptPath: "D:\\Desktop\\GPM\\exports\\degap\\prepare_degap_shared.sh",
          scripts: [],
        }),
      };
    };

    const result = await exportDegapJobs({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      outputDir: "D:\\Desktop\\GPM\\exports\\degap",
      settings,
      jobs,
    });

    assert.equal(result.manifestPath, "D:\\Desktop\\GPM\\exports\\degap\\jobs.tsv");
  } finally {
    globalThis.window = previousWindow;
    globalThis.fetch = previousFetch;
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, "/api/export-degap-jobs");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["content-type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    workspaceRoot: "D:\\Desktop\\GPM\\ws1",
    projectId: 7,
    outputDir: "D:\\Desktop\\GPM\\exports\\degap",
    settings,
    jobs,
  });
});

test("listProjectInitializerOptions preserves partitioned package metadata from tauri", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command) => {
            assert.equal(command, "list_project_initializer_options");
            return {
              packageMetadata: {
                packageMode: "fast",
                sequenceLayout: "partitioned",
                preassignedChr: true,
                chrAssignmentMinCoveragePercent: 60,
                selfAlignmentScope: "chr_partition",
                crossAlignmentScope: "chr_partition",
              },
              references: [{ referenceGenomeId: 1, label: "Ref #1" }],
              datasets: [{ datasetId: 1, label: "hifiasm", fastaAvailable: true }],
              existingProjects: [],
            };
          },
        },
      },
    };

    const result = await listProjectInitializerOptions({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
    });

    assert.equal(result.packageMetadata.packageMode, "fast");
    assert.equal(result.packageMetadata.sequenceLayout, "partitioned");
    assert.equal(result.packageMetadata.preassignedChr, true);
    assert.equal(result.packageMetadata.selfAlignmentScope, "chr_partition");
  } finally {
    globalThis.window = previousWindow;
  }
});

test("openWorkspace preserves partitioned package metadata from tauri", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command) => {
            assert.equal(command, "open_workspace");
            return {
              packageMetadata: {
                packageMode: "fast",
                sequenceLayout: "partitioned",
                preassignedChr: true,
                chrAssignmentMinCoveragePercent: 60,
                selfAlignmentScope: "chr_partition",
                crossAlignmentScope: "chr_partition",
              },
              references: [{ referenceGenomeId: 1, label: "Ref #1" }],
              datasets: [{ datasetId: 1, label: "hifiasm", fastaAvailable: false }],
              existingProjects: [],
            };
          },
        },
      },
    };

    const result = await openWorkspace({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
    });

    assert.equal(result.packageMetadata.sequenceLayout, "partitioned");
    assert.equal(result.datasets[0].fastaAvailable, false);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("deleteProject tauri does not synthesize an empty project list when backend omits it", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            assert.equal(command, "delete_project");
            assert.equal(args.workspaceRoot, "D:\\Desktop\\GPM\\ws1");
            assert.equal(args.projectId, 7);
            return {
              projectId: 7,
              deleted: true,
            };
          },
        },
      },
    };

    const result = await deleteProject({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
    });

    assert.equal(result.deleted, true);
    assert.equal(Object.hasOwn(result, "existingProjects"), false);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("runCtgEditorAction rejects removed deep-edit actions before dispatch", async () => {
  await assert.rejects(
    () => runCtgEditorAction({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      action: "split-ctg",
      args: {
        assemblyCtgId: 8,
        breakAfterMemberId: 1001,
        newName: "ctg-split",
      },
    }),
    /unsupported|unknown/i,
  );
});

test("updateProject mock allows processed project safe one-way edits only", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};

    const created = await initializeProject({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectName: `project-threshold-lock-${Date.now()}`,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: [2],
      chrAssignmentMinCoveragePercent: 60,
    });

    await setProjectAutoPipelineDone({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      done: true,
    });

    const updated = await updateProject({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      projectName: `${created.projectName}-renamed`,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: [2, 3],
      chrAssignmentMinCoveragePercent: 60,
      phasedAssemblyEnabled: true,
      stateOrLocale: { locale: "en" },
    });
    assert.equal(updated.projectName, `${created.projectName}-renamed`);
    assert.deepEqual(updated.supportDatasetIds, [2, 3]);
    assert.equal(updated.phasedAssemblyEnabled, true);
    assert.equal(updated.isProcessed, true);

    await assert.rejects(
      () => updateProject({
        workspaceRoot: "D:\\Desktop\\GPM\\ws1",
        projectId: created.projectId,
        projectName: `${created.projectName}-renamed`,
        referenceGenomeId: 1,
        primaryDatasetId: 1,
        supportDatasetIds: [2],
        chrAssignmentMinCoveragePercent: 66,
        stateOrLocale: { locale: "en" },
      }),
      /only renaming|allowed/i,
    );

    await assert.rejects(
      () => updateProject({
        workspaceRoot: "D:\\Desktop\\GPM\\ws1",
        projectId: created.projectId,
        projectName: `${created.projectName}-renamed`,
        referenceGenomeId: 1,
        primaryDatasetId: 1,
        supportDatasetIds: [3],
        chrAssignmentMinCoveragePercent: 60,
        phasedAssemblyEnabled: true,
        stateOrLocale: { locale: "en" },
      }),
      /only renaming|allowed/i,
    );

    await assert.rejects(
      () => updateProject({
        workspaceRoot: "D:\\Desktop\\GPM\\ws1",
        projectId: created.projectId,
        projectName: `${created.projectName}-renamed`,
        referenceGenomeId: 1,
        primaryDatasetId: 1,
        supportDatasetIds: [2, 3],
        chrAssignmentMinCoveragePercent: 60,
        phasedAssemblyEnabled: false,
        stateOrLocale: { locale: "en" },
      }),
      /only renaming|allowed/i,
    );
  } finally {
    globalThis.window = previousWindow;
  }
});

test("mock phased track lifecycle allows duplicate ctg references, exact reorder, and delete compaction", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};
    const created = await initializeProject({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectName: `project-phased-${Date.now()}`,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: [2],
      phasedAssemblyEnabled: true,
    });

    const createdTrack = await createPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    assert.equal(createdTrack.track.haplotypeKey, "A");
    assert.equal(createdTrack.track.label, "Chr01A");
    const secondTrack = await createPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    const thirdTrack = await createPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    assert.equal(secondTrack.track.haplotypeKey, "B");
    assert.equal(thirdTrack.track.haplotypeKey, "C");

    const first = await addCtgToPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackId: createdTrack.track.phasedTrackId,
      assemblyCtgId: 42,
    });
    const second = await addCtgToPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackId: createdTrack.track.phasedTrackId,
      assemblyCtgId: 42,
    });
    assert.equal(first.item.gapBeforePx, 20);
    assert.equal(second.item.displayOrder, 2);

    const reordered = await reorderPhasedChrTrackItems({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackId: createdTrack.track.phasedTrackId,
      itemIds: [second.item.itemId, first.item.itemId],
    });
    assert.equal(reordered.itemCount, 2);

    const listed = await listPhasedChrTracks({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    assert.deepEqual(
      listed.tracks[0].items.map((item) => item.itemId),
      [second.item.itemId, first.item.itemId],
    );

    await addCtgToPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackId: thirdTrack.track.phasedTrackId,
      assemblyCtgId: 42,
    });

    const deletedMiddle = await deletePhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackId: secondTrack.track.phasedTrackId,
    });
    assert.equal(deletedMiddle.deleted, true);
    const compacted = await listPhasedChrTracks({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    assert.deepEqual(
      compacted.tracks.map((track) => [track.phasedTrackId, track.haplotypeKey, track.label]),
      [
        [createdTrack.track.phasedTrackId, "A", "Chr01A"],
        [thirdTrack.track.phasedTrackId, "B", "Chr01B"],
      ],
    );

    await removePhasedChrTrackItem({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackItemId: second.item.itemId,
    });
    const deleted = await deletePhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: created.projectId,
      phasedTrackId: createdTrack.track.phasedTrackId,
    });
    assert.equal(deleted.deleted, true);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("phased track services route tauri invoke commands with camelCase payloads", async () => {
  const previousWindow = globalThis.window;
  const calls = [];
  try {
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            if (command === "list_phased_chr_tracks") {
              return { projectId: 7, parentChrName: "Chr01", tracks: [] };
            }
            if (command === "create_phased_chr_track") {
              return {
                track: {
                  phasedTrackId: 3,
                  projectId: 7,
                  parentChrName: "Chr01",
                  haplotypeKey: "A",
                  label: "Chr01A",
                  displayOrder: 1,
                  items: [],
                },
              };
            }
            if (command === "add_ctg_to_phased_chr_track") {
              return {
                item: {
                  itemId: 9,
                  phasedTrackId: 3,
                  assemblyCtgId: 42,
                  displayOrder: 1,
                  gapBeforePx: 20,
                },
              };
            }
            return { ok: true };
          },
        },
      },
    };

    await listPhasedChrTracks({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      parentChrName: "Chr01",
    });
    await createPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      parentChrName: "Chr01",
    });
    await addCtgToPhasedChrTrack({
      workspaceRoot: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      phasedTrackId: 3,
      assemblyCtgId: 42,
    });

    assert.deepEqual(
      calls.map((call) => call.command),
      [
        "list_phased_chr_tracks",
        "create_phased_chr_track",
        "add_ctg_to_phased_chr_track",
      ],
    );
    assert.equal(calls[2].args.phasedTrackId, 3);
    assert.equal(calls[2].args.assemblyCtgId, 42);
  } finally {
    globalThis.window = previousWindow;
  }
});
