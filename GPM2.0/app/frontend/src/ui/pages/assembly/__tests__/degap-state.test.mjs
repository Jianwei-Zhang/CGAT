import test from "node:test";
import assert from "node:assert/strict";

import {
  buildDegapJobKey,
  buildDegapExportJobs,
  buildDegapExportSettings,
  buildDegapJobsForGap,
  buildTelseekerCtgJobsForFinalPath,
  findDuplicateDegapJobs,
  mergeDegapJobs,
  normalizeDegapSettings,
  resolveDegapExportSettings,
  resolveDegapJobOutPath,
  resolveDegapJobSettings,
  validateDegapSettings,
} from "../degap-state.js";

const settings = normalizeDegapSettings({
  degapPath: "/opt/DEGAP/bin/DEGAP.py",
  hifiReads: ["/reads/a.fq.gz"],
  ontReads: ["/reads/b.fq.gz"],
  gpmServerPath: "/srv/gpm_server",
  outRoot: "/srv/degap",
  thread: 32,
});

const finalPathEntry = {
  chrName: "Chr01",
  segments: [
    {
      segmentId: "ctg-a",
      type: "ctg",
      assemblyCtgId: 101,
      ctgName: "CtgA",
      overallLen: 1000,
      start: 1000,
      end: 801,
    },
    {
      segmentId: "gap-1",
      type: "gap",
      lengthBp: 100,
    },
    {
      segmentId: "ctg-b",
      type: "ctg",
      assemblyCtgId: 102,
      ctgName: "CtgB",
      overallLen: 900,
      start: 1,
      end: 200,
    },
  ],
};

const adjacentGapFinalPathEntry = {
  chrName: "Chr01",
  segments: [
    {
      segmentId: "ctg-a",
      type: "ctg",
      assemblyCtgId: 101,
      ctgName: "CtgA",
      overallLen: 1000,
      start: 1000,
      end: 801,
    },
    {
      segmentId: "gap-1",
      type: "gap",
      lengthBp: 100,
    },
    {
      segmentId: "gap-2",
      type: "gap",
      lengthBp: 200,
    },
    {
      segmentId: "ctg-b",
      type: "ctg",
      assemblyCtgId: 102,
      ctgName: "CtgB",
      overallLen: 900,
      start: 1,
      end: 200,
    },
  ],
};

test("buildDegapJobsForGap creates ordered left and right jobs with oriented seeds", () => {
  const jobs = buildDegapJobsForGap({
    finalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["right", "left"],
    settings,
  });
  const ordered = mergeDegapJobs([], jobs);

  assert.equal(ordered.length, 2);
  assert.equal(ordered[0].side, "left");
  assert.equal(ordered[1].side, "right");
  assert.deepEqual(ordered[0].left, {
    assemblyCtgId: 101,
    start: 1000,
    end: 801,
  });
  assert.equal(ordered[0].outPath, "/srv/degap/CtgA_vs_CtgB_Left-job");
});

test("buildDegapExportJobs carries per-job settings overrides", () => {
  const [job] = buildDegapJobsForGap({
    finalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
  });
  const [exportJob] = buildDegapExportJobs([
    {
      ...job,
      settings: {
        ...settings,
        thread: 12,
        hifiReads: ["/reads/job-hifi.fq.gz"],
      },
    },
  ], settings);

  assert.equal(exportJob.settings.thread, 12);
  assert.deepEqual(exportJob.settings.hifiReads, ["/reads/job-hifi.fq.gz"]);
  assert.equal(exportJob.flag, "left");
  assert.equal(
    buildDegapExportJobs([{ ...job, settings: { ...settings, outRoot: "" } }], settings)[0].settings.outRoot,
    "/srv/degap",
  );
});

test("DEGAP job settings inherit updated global values unless fields are overridden", () => {
  const [job] = buildDegapJobsForGap({
    finalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
  });
  const updatedGlobalSettings = normalizeDegapSettings({
    ...settings,
    hifiReads: ["/reads/latest-hifi.fq.gz"],
    thread: 64,
    outRoot: "/srv/degap-latest",
  });
  const inheritedSettings = resolveDegapJobSettings(job, updatedGlobalSettings);

  assert.equal(inheritedSettings.thread, 64);
  assert.deepEqual(inheritedSettings.hifiReads, ["/reads/latest-hifi.fq.gz"]);
  assert.equal(resolveDegapJobOutPath(job, updatedGlobalSettings), "/srv/degap-latest/CtgA_vs_CtgB_Left-job");

  const overriddenJob = {
    ...job,
    settings: {
      ...job.settings,
      thread: 12,
    },
    outPath: "/custom/degap/job-left",
  };
  const overriddenSettings = resolveDegapJobSettings(overriddenJob, updatedGlobalSettings);
  const [exportJob] = buildDegapExportJobs([overriddenJob], updatedGlobalSettings);

  assert.equal(overriddenSettings.thread, 12);
  assert.deepEqual(overriddenSettings.hifiReads, ["/reads/latest-hifi.fq.gz"]);
  assert.equal(resolveDegapJobOutPath(overriddenJob, updatedGlobalSettings), "/custom/degap/job-left");
  assert.equal(exportJob.settings.thread, 12);
  assert.deepEqual(exportJob.settings.hifiReads, ["/reads/latest-hifi.fq.gz"]);
  assert.equal(exportJob.settings.outRoot, "/srv/degap-latest");
  assert.equal(exportJob.outPath, "/custom/degap/job-left");
});

test("DEGAP export settings backfill missing global software fields from persisted jobs", () => {
  const [job] = buildDegapJobsForGap({
    finalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
  });
  const workspaceOnlySettings = normalizeDegapSettings({
    hifiReads: ["/reads/latest-hifi.fq.gz"],
    ontReads: ["/reads/latest-ont.fq.gz"],
    gpmServerPath: "/srv/gpm_server",
    outRoot: "/srv/degap-latest",
  });
  const exportSettings = resolveDegapExportSettings(workspaceOnlySettings, [job]);
  const [exportJob] = buildDegapExportJobs([job], exportSettings);

  assert.equal(exportSettings.degapPath, "/opt/DEGAP/bin/DEGAP.py");
  assert.equal(exportSettings.outRoot, "/srv/degap-latest");
  assert.deepEqual(exportSettings.hifiReads, ["/reads/latest-hifi.fq.gz"]);
  assert.equal(exportJob.settings.degapPath, "/opt/DEGAP/bin/DEGAP.py");
  assert.equal(exportJob.settings.outRoot, "/srv/degap-latest");
  assert.equal(exportJob.outPath, "/srv/degap-latest/CtgA_vs_CtgB_Left-job");
});

test("buildTelseekerCtgJobsForFinalPath creates endpoint jobs only from final path ends", () => {
  const jobs = buildTelseekerCtgJobsForFinalPath({
    finalPathEntry: {
      chrName: "ChrTel",
      segments: [
        { segmentId: "left-end", type: "ctg", assemblyCtgId: 501, ctgName: "TelLeft", overallLen: 100, start: 1, end: 100 },
        { segmentId: "gap-1", type: "gap", gapSizeBp: 20 },
        { segmentId: "middle", type: "ctg", assemblyCtgId: 502, ctgName: "Middle", overallLen: 100, start: 1, end: 100 },
        { segmentId: "gap-2", type: "gap", gapSizeBp: 20 },
        { segmentId: "right-end", type: "ctg", assemblyCtgId: 503, ctgName: "TelRight", overallLen: 120, start: 120, end: 1 },
      ],
    },
    ends: ["left", "right"],
    settings: {
      ...settings,
      filterDepthHifi: 20,
      filterDepthOnt: 30,
    },
  });
  const exportJobs = buildDegapExportJobs(jobs, settings);

  assert.equal(jobs.length, 2);
  assert.equal(jobs[0].jobType, "telseeker_ctg");
  assert.equal(jobs[0].endpointCtg, "TelLeft");
  assert.equal(jobs[0].endpointEnd, "L");
  assert.equal(jobs[1].endpointCtg, "TelRight");
  assert.equal(jobs[1].endpointEnd, "R");
  assert.equal(exportJobs[0].settings.filterDepthHifi, null);
  assert.equal(exportJobs[0].settings.filterDepthOnt, null);
  assert.deepEqual(exportJobs[1].endpoint, { assemblyCtgId: 503, start: 120, end: 1 });
});

test("buildDegapJobsForGap resolves the same flanking ctgs across adjacent GAP runs", () => {
  const fromFirstGap = buildDegapJobsForGap({
    finalPathEntry: adjacentGapFinalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["left", "right"],
    settings,
  });
  const fromSecondGap = buildDegapJobsForGap({
    finalPathEntry: adjacentGapFinalPathEntry,
    gapSegmentId: "gap-2",
    sides: ["left", "right"],
    settings,
  });

  assert.deepEqual(
    fromSecondGap.map((job) => job.jobId),
    fromFirstGap.map((job) => job.jobId),
  );
  assert.deepEqual(
    fromSecondGap.map((job) => job.label),
    ["CtgA_vs_CtgB Left-job", "CtgA_vs_CtgB Right-job"],
  );
  assert.deepEqual(fromSecondGap[0].left, { assemblyCtgId: 101, start: 1000, end: 801 });
  assert.deepEqual(fromSecondGap[0].right, { assemblyCtgId: 102, start: 1, end: 200 });
});

test("buildDegapJobsForGap rejects GAP runs missing a flanking ctg", () => {
  assert.throws(() => buildDegapJobsForGap({
    finalPathEntry: {
      chrName: "Chr01",
      segments: adjacentGapFinalPathEntry.segments.slice(1),
    },
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
    stateOrLocale: "zh",
  }), /没有可用 Ctg/);
  assert.throws(() => buildDegapJobsForGap({
    finalPathEntry: {
      chrName: "Chr01",
      segments: adjacentGapFinalPathEntry.segments.slice(0, 3),
    },
    gapSegmentId: "gap-2",
    sides: ["right"],
    settings,
    stateOrLocale: "zh",
  }), /没有可用 Ctg/);
});

test("findDuplicateDegapJobs reports requested jobs that already exist", () => {
  const existingJobs = buildDegapJobsForGap({
    finalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
  });
  const requestedJobs = buildDegapJobsForGap({
    finalPathEntry,
    gapSegmentId: "gap-1",
    sides: ["left", "right"],
    settings,
  });

  const duplicates = findDuplicateDegapJobs(existingJobs, requestedJobs);

  assert.equal(duplicates.length, 1);
  assert.equal(duplicates[0].jobId, "CtgA_vs_CtgB_Left-job");
  assert.equal(mergeDegapJobs(existingJobs, requestedJobs).length, 2);
});

test("DEGAP job identity is scoped by final path chromosome", () => {
  const [jobA] = buildDegapJobsForGap({
    finalPathEntry: {
      ...finalPathEntry,
      chrName: "Chr01A",
    },
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
  });
  const [jobB] = buildDegapJobsForGap({
    finalPathEntry: {
      ...finalPathEntry,
      chrName: "Chr01B",
    },
    gapSegmentId: "gap-1",
    sides: ["left"],
    settings,
  });

  assert.equal(jobA.jobId, jobB.jobId);
  assert.notEqual(buildDegapJobKey(jobA), buildDegapJobKey(jobB));
  assert.equal(mergeDegapJobs([jobA], [jobB]).length, 2);
  assert.equal(findDuplicateDegapJobs([jobA], [jobB]).length, 0);
  assert.equal(findDuplicateDegapJobs([jobA], [jobA]).length, 1);
});

test("validateDegapSettings requires one reads group and server paths", () => {
  assert.equal(validateDegapSettings(settings), "");
  assert.match(validateDegapSettings({ ...settings, hifiReads: [], ontReads: [] }), /Reads PATH/);
  assert.deepEqual(buildDegapExportSettings(settings).ontReads, ["/reads/b.fq.gz"]);
});
