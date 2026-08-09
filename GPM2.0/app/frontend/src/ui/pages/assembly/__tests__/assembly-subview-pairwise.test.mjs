import {
  test,
  assert,
  __testEnterSubviewFromCandidates,
  __testHandleTrackSubviewCandidateSelection,
  __testSelectSubviewCandidate,
  __testSelectSubviewTrack,
  __testBuildSubviewSummaryFromTrackSelections,
  renderAssemblyPage,
  createState,
} from "./tabs-semantics-harness.mjs";

test("subview ctg uses true pairwise paf intervals for ds-ds bands", () => {
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
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 100,
                queryEnd: 1300,
                subjectStart: 20000,
                subjectEnd: 21200,
                strand: "-",
                alignLength: 1200,
                mapq: 60,
              },
            ],
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
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const topWidth = Math.abs(pointList[1][0] - pointList[0][0]);
  const bottomWidth = Math.abs(pointList[2][0] - pointList[3][0]);
  assert.ok(topWidth < 100, `expected top band to use local paf width, got ${topWidth}`);
  assert.ok(bottomWidth < 100, `expected bottom band to use local paf width, got ${bottomWidth}`);
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected negative-strand subview ctg band to cross, got ${JSON.stringify(pointList)}`,
  );
});

test("subview ctg pairwise bands mirror phased item orientation", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-left",
            assignedChrName: "Chr01",
            totalLength: 1000,
            anchorStart: 300,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 1, ctgEnd: 1000, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-forward",
            assignedChrName: "Chr01",
            totalLength: 1000,
            orient: "+",
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 101, ctgEnd: 200, blockLength: 100, mapq: 60 },
            ],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, orient: "-" },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 50,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          pairwiseEvidence: {
            key: "2-contig:support:30:phased:2:9001:101:A",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 101,
                queryEnd: 200,
                subjectStart: 101,
                subjectEnd: 200,
                strand: "+",
                alignLength: 100,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support" },
            bottom: {
              contigId: 2,
              role: "phased",
              phasedTrackId: 101,
              phasedTrackItemId: 9001,
              phasedHaplotypeKey: "A",
            },
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
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const topCenter = (pointList[0][0] + pointList[1][0]) / 2;
  const bottomCenter = (pointList[2][0] + pointList[3][0]) / 2;
  assert.ok(
    bottomCenter - topCenter > 300,
    `expected phased bottom range to be mirrored to the right, got ${JSON.stringify(pointList)}`,
  );
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected phased one-sided mirror to make the positive-strand pairwise band cross, got ${JSON.stringify(pointList)}`,
  );
});

test("phased track contigs can be selected as subview-ctg candidates", () => {
  const nextSubview = __testSelectSubviewCandidate({
    subview: {},
    trackRole: "phased",
    contigId: 2,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
    phasedHaplotypeKey: "A",
    stateOrLocale: "zh",
  });

  assert.deepEqual(nextSubview.selectedAContigId, 2);
  assert.equal(nextSubview.selectedARole, "phased");
  assert.equal(nextSubview.selectedAPhasedTrackId, 101);
  assert.equal(nextSubview.selectedAPhasedTrackItemId, 9001);
  assert.equal(nextSubview.selectedAPhasedHaplotypeKey, "A");
});

test("phased track labels preserve identity for subview-track selection", () => {
  const afterPrimary = __testSelectSubviewTrack({
    subview: {},
    trackRole: "primary",
    stateOrLocale: "zh",
  });
  const afterPhased = __testSelectSubviewTrack({
    subview: afterPrimary,
    trackRole: "phased",
    phasedTrackId: 101,
    haplotypeKey: "A",
    stateOrLocale: "zh",
  });

  assert.deepEqual(afterPhased.selectedTrackSelections, [
    { role: "primary", source: "mother", datasetId: null, isMirror: false },
    {
      role: "phased",
      source: "mother",
      datasetId: null,
      isMirror: false,
      phasedTrackId: 101,
      haplotypeKey: "A",
    },
  ]);
  assert.equal(afterPhased.summary?.bottomTrack?.phasedTrackId, 101);
});

test("subview track-pair uses true pairwise paf intervals for ds-ds bands", () => {
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
            totalLength: 5000,
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
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|primary:2",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 150,
                queryEnd: 310,
                subjectStart: 700,
                subjectEnd: 950,
                strand: "-",
                alignLength: 160,
                mapq: 60,
              },
            ],
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

  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 150-310 bp[^"]*primary-bottom: 700-950 bp/);
  assert.doesNotMatch(html, /support-top: 2,200-3,400 bp/);
  assert.doesNotMatch(html, /primary-bottom: 2,400-3,600 bp/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected negative-strand subview track-pair band to cross, got ${JSON.stringify(pointList)}`,
  );
});

test("subview track-pair pairwise bands mirror phased item orientation", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-left",
            assignedChrName: "Chr01",
            totalLength: 1000,
            anchorStart: 300,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 1, ctgEnd: 1000, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-forward",
            assignedChrName: "Chr01",
            totalLength: 1000,
            orient: "+",
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 101, ctgEnd: 200, blockLength: 100, mapq: 60 },
            ],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, orient: "-" },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 50,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|phased:101:A:2",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 101,
                queryEnd: 200,
                subjectStart: 101,
                subjectEnd: 200,
                strand: "+",
                alignLength: 100,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22 },
            bottomTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
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
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const topCenter = (pointList[0][0] + pointList[1][0]) / 2;
  const bottomCenter = (pointList[2][0] + pointList[3][0]) / 2;
  assert.ok(
    bottomCenter - topCenter > 50,
    `expected phased track-pair range to be mirrored to the right, got ${JSON.stringify(pointList)}`,
  );
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected phased one-sided mirror to make the positive-strand track-pair band cross, got ${JSON.stringify(pointList)}`,
  );
});

test("subview track-pair skips same-contig hits and shows the skipped hint", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        isChrPhased: true,
        activePhasedTrackKey: "A",
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ptg000004l",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [
              {
                itemId: 9001,
                phasedTrackId: 101,
                assemblyCtgId: 2,
                displayOrder: 1,
              },
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
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:primary:2|phased:101:A:2",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 2,
                subjectAssemblyCtgId: 2,
                queryStart: 100,
                queryEnd: 220,
                subjectStart: 700,
                subjectEnd: 820,
                strand: "+",
                alignLength: 120,
                mapq: 60,
              },
              {
                hitKey: "pair-2",
                queryAssemblyCtgId: 2,
                subjectAssemblyCtgId: 2,
                queryStart: 700,
                queryEnd: 820,
                subjectStart: 100,
                subjectEnd: 220,
                strand: "+",
                alignLength: 120,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "primary" },
            bottomTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
    }),
  );

  assert.match(html, /<h4>Subview <span class="subview-same-contig-warning">同 ctg 比对已跳过，故无 hits<\/span><\/h4>/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const bandMatches = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*" points="[^"]+"/g) || [];
  assert.equal(bandMatches.length, 0, `expected same-contig self hits to be skipped, got ${bandMatches.length}`);
});

test("subview ctg pairwise bands mirror local flips and toggle band direction", () => {
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
            hits: [],
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
            hits: [],
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
          flippedCtgs: [{ slot: "bottom", contigId: 2 }],
          pairwiseEvidence: {
            key: "2-contig:support:30:primary:2",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 100,
                queryEnd: 1300,
                subjectStart: 20000,
                subjectEnd: 21200,
                strand: "+",
                alignLength: 1200,
                mapq: 60,
              },
            ],
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

  assert.match(html, /data-subview-band-tooltip="[^"]*support-small: 100-1,300 bp[^"]*primary-broad: 18,801-20,001 bp/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected one-sided local flip to cross the subview ctg band, got ${JSON.stringify(pointList)}`,
  );
});

test("subview track-pair pairwise bands mirror local flips and toggle band direction", () => {
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
            anchorStart: 320,
            hits: [],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [],
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
          flippedCtgs: [{ slot: "top", contigId: 30 }],
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|primary:2",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 150,
                queryEnd: 310,
                subjectStart: 700,
                subjectEnd: 950,
                strand: "+",
                alignLength: 160,
                mapq: 60,
              },
            ],
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

  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 3,691-3,851 bp[^"]*primary-bottom: 700-950 bp/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected one-sided local flip to cross the subview track-pair band, got ${JSON.stringify(pointList)}`,
  );
});

test("subview bands expose only top and bottom ctg interval tooltip payload with 500ms hover delay config", () => {
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

  assert.match(html, /data-subview-band-tooltip-delay-ms="500"/);
  assert.match(html, /class="subview-band-tooltip is-hidden"/);
  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 2,200-3,400 bp[^"]*primary-bottom: 2,400-3,600 bp/);
  assert.match(html, /class="track-band-canvas-layer"[^>]*data-track-band-canvas-scene-kind="subview-ctg"/);
  assert.match(html, /<canvas class="track-band-canvas"[^>]*data-track-band-canvas="1"/);
  assert.match(html, /<polygon class="track-collinearity-band is-companion"[^>]*pointer-events="visibleFill"[^>]*data-track-band-proxy="1"/);
  assert.match(html, /class="track-ctg subview-track-ctg is-companion"[^>]*pointer-events="all"/);
  assert.match(html, /class="track-ctg subview-track-ctg"[^>]*pointer-events="all"/);
  assert.doesNotMatch(html, /data-subview-band-tooltip="[^"]*Ref:/);
});

test("subview low alignment threshold keeps right-side coverage instead of left-biased saturation", () => {
  const leftDenseHits = Array.from({ length: 300 }, (_, index) => {
    const refStart = 1000 + index * 500;
    return {
      refStart,
      refEnd: refStart + 1200,
      ctgStart: 2000 + index * 30,
      ctgEnd: 2000 + index * 30 + 1200,
      blockLength: 1200,
      mapq: 60,
    };
  });
  const rightLongHits = Array.from({ length: 20 }, (_, index) => {
    const refStart = 18_000_000 + index * 300_000;
    const ctgStart = 22_000_000 + index * 150_000;
    return {
      refStart,
      refEnd: refStart + 12_000,
      ctgStart,
      ctgEnd: ctgStart + 12_000,
      blockLength: 12_000,
      mapq: 60,
    };
  });
  const sharedTopHits = [...leftDenseHits, ...rightLongHits];
  const sharedBottomHits = [...leftDenseHits, ...rightLongHits];

  const buildHtml = (alignmentLength) =>
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
              totalLength: 30_000_000,
              anchorStart: 320,
              hits: sharedTopHits,
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 2,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30_000_000,
              anchorStart: 100,
              hits: sharedBottomHits,
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 10000,
            maxTickCount: 10,
            alignmentLength,
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

  const lowThresholdHtml = buildHtml(1000);
  const highThresholdHtml = buildHtml(10000);
  const extractMaxBandX = (html) => {
    const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
    assert.ok(subviewSvgMatch, "expected subview svg");
    const svgMarkup = subviewSvgMatch[0];
    const svgWidthMatch = svgMarkup.match(/<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"/);
    assert.ok(svgWidthMatch, "expected subview svg width");
    const svgWidth = Number(svgWidthMatch[1]);
    const polygons = Array.from(
      svgMarkup.matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
    );
    assert.ok(polygons.length > 0, "expected subview band polygons");
    const maxX = Math.max(
      ...polygons.flatMap((polygon) =>
        polygon[1].split(/\s+/).map((point) => Number(point.split(",")[0])),
      ),
    );
    return { maxX, svgWidth };
  };

  const lowThresholdRange = extractMaxBandX(lowThresholdHtml);
  const highThresholdRange = extractMaxBandX(highThresholdHtml);
  assert.ok(
    lowThresholdRange.maxX > lowThresholdRange.svgWidth * 0.7,
    `expected low-threshold view to retain right-side bands, got maxX=${lowThresholdRange.maxX}, svgWidth=${lowThresholdRange.svgWidth}`,
  );
  assert.ok(
    highThresholdRange.maxX > highThresholdRange.svgWidth * 0.7,
    `expected high-threshold view to show right-side bands, got maxX=${highThresholdRange.maxX}, svgWidth=${highThresholdRange.svgWidth}`,
  );
});

test("subview renders all passed overlapping hit pairs without a fixed band cap", () => {
  const overlapHits = Array.from({ length: 260 }, (_, index) => {
    const refStart = 10_000 + index * 20_000;
    const ctgStart = 50_000 + index * 20_000;
    return {
      refStart,
      refEnd: refStart + 5_000,
      ctgStart,
      ctgEnd: ctgStart + 5_000,
      blockLength: 5_000,
      mapq: 60,
    };
  });

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
            totalLength: 6_000_000,
            anchorStart: 320,
            hits: overlapHits,
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 6_000_000,
            anchorStart: 100,
            hits: overlapHits,
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
  assert.equal(polygons.length, 260, "expected every overlapping hit pair to be rendered");
});

test("track-driven subview selection enters Subview-ctg immediately after selecting the second candidate", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
      ],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 }],
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

  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 8 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 30 });

  const subview = store.getState().assembly.subview;
  assert.equal(subview.summary?.mode, "2-contig");
  assert.equal(subview.summary?.top?.contigId, 30);
  assert.equal(subview.summary?.bottom?.contigId, 8);
  assert.equal(subview.message, "Subview 已进入。");
  assert.equal(subview.error, "");
});

test("enterSubviewFromCandidates copies main-track scale prefs into subviewTrackView", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      trackView: {
        supportDsCtgLen: 10000,
        minTickUnitKb: 750,
        maxTickCount: 18,
        alignmentLength: 12345,
        mapq: 31,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
      ],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-ctg", totalLength: 15000, anchorStart: 320 }],
      subview: {
        mode: "2-contig",
        selectedAContigId: 8,
        selectedARole: "primary",
        selectedBContigId: 30,
        selectedBRole: "support",
        message: "",
        error: "",
        summary: null,
      },
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

  __testEnterSubviewFromCandidates(host, store);

  assert.deepEqual(store.getState().assembly.subviewTrackView, {
    supportDsCtgLen: 10000,
    minTickUnitKb: 750,
    minTickKb: 750,
    maxTickCount: 18,
    alignmentLength: 12345,
    block_length: 12345,
    mapq: 31,
  });
});

test("track-driven subview selection blocks same-ds contigs when self alignment is unavailable", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
    },
    assembly: {
      supportDatasetId: null,
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", datasetId: 11, anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", datasetId: 11, anchorStart: 500 },
      ],
      supportChrCtgs: [],
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

  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 8 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 2 });

  const subview = store.getState().assembly.subview;
  assert.equal(subview.summary, null);
  assert.equal(subview.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
});

test("track-driven subview selection blocks primary-phased and phased-phased same-ds contigs when self alignment is unavailable", () => {
  const host = {
    closest() {
      return null;
    },
  };
  const scenarios = [
    {
      picks: [
        { trackRole: "primary", contigId: 8 },
        { trackRole: "phased", contigId: 2 },
      ],
      expectedSelections: [
        { contigId: 8, role: "primary" },
        { contigId: 2, role: "phased" },
      ],
    },
    {
      picks: [
        { trackRole: "phased", contigId: 8 },
        { trackRole: "phased", contigId: 2 },
      ],
      expectedSelections: [
        { contigId: 8, role: "phased" },
        { contigId: 2, role: "phased" },
      ],
    },
  ];

  for (const { picks, expectedSelections } of scenarios) {
    let state = createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
      assembly: {
        supportDatasetId: null,
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-alpha", datasetId: 11, anchorStart: 100 },
          { assemblyCtgId: 8, name: "ctg-beta", datasetId: 11, anchorStart: 500 },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
          },
          {
            phasedTrackId: 102,
            haplotypeKey: "B",
            items: [{ itemId: 9002, phasedTrackId: 102, assemblyCtgId: 8, displayOrder: 1 }],
          },
        ],
        supportChrCtgs: [],
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

    for (const pick of picks) {
      __testHandleTrackSubviewCandidateSelection(host, store, pick);
    }

    const subview = store.getState().assembly.subview;
    assert.deepEqual(
      [
        { contigId: subview.selectedAContigId, role: subview.selectedARole },
        { contigId: subview.selectedBContigId, role: subview.selectedBRole },
      ],
      expectedSelections,
    );
    assert.equal(subview.summary, null);
    assert.equal(subview.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
  }
});

test("buildSubviewSummaryFromTrackSelections blocks same primary-dataset phased track pairs when self alignment is unavailable", () => {
  const state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
        { datasetId: 22, name: "flye", label: "flye", selfAlignmentAvailable: true },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });
  const scenarios = [
    [
      { role: "primary", source: "mother", datasetId: null, isMirror: false },
      { role: "phased", source: "mother", datasetId: null, isMirror: false, phasedTrackId: 101, haplotypeKey: "A" },
    ],
    [
      { role: "phased", source: "mother", datasetId: null, isMirror: false, phasedTrackId: 101, haplotypeKey: "A" },
      { role: "phased", source: "mother", datasetId: null, isMirror: false, phasedTrackId: 102, haplotypeKey: "B" },
    ],
  ];

  for (const selectedTrackSelections of scenarios) {
    const result = __testBuildSubviewSummaryFromTrackSelections({
      subview: {
        selectedTrackSelections,
      },
      stateOrLocale: state,
    });

    assert.equal(result.ok, false);
    assert.equal(result.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
  }
});

test("track label selection keeps cross-dataset support-phased pairs available when primary self alignment is unavailable", () => {
  const state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
        { datasetId: 22, name: "flye", label: "flye", selfAlignmentAvailable: true },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });

  const afterSupport = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    datasetId: 22,
    stateOrLocale: state,
  });
  const afterPhased = __testSelectSubviewTrack({
    subview: afterSupport,
    trackRole: "phased",
    phasedTrackId: 101,
    haplotypeKey: "A",
    stateOrLocale: state,
  });

  assert.deepEqual(afterPhased.selectedTrackSelections, [
    { role: "support", source: "mother", datasetId: 22, isMirror: false },
    {
      role: "phased",
      source: "mother",
      datasetId: null,
      isMirror: false,
      phasedTrackId: 101,
      haplotypeKey: "A",
    },
  ]);
  assert.equal(afterPhased.summary?.mode, "track-pair");
  assert.equal(afterPhased.summary?.topTrack?.role, "support");
  assert.equal(afterPhased.summary?.bottomTrack?.role, "phased");
  assert.equal(afterPhased.error, "");
});

test("track-driven subview selection re-enters Subview-ctg when Ctrl/Cmd adjusts an already-complete pair", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
      ],
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 },
        { assemblyCtgId: 31, name: "support-ctg-2", anchorStart: 640 },
      ],
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

  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 8 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 30 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 30 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 31 });

  const subview = store.getState().assembly.subview;
  assert.equal(subview.summary?.mode, "2-contig");
  assert.equal(subview.summary?.top?.contigId, 31);
  assert.equal(subview.summary?.bottom?.contigId, 8);
  assert.equal(subview.message, "Subview 已进入。");
  assert.equal(subview.error, "");
});

test("track-driven subview selection supports same-ds picks without support ds", () => {
  const afterFirst = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: null,
    primaryCtgs: [
      { assemblyCtgId: 8, name: "ctg-beta" },
      { assemblyCtgId: 2, name: "ctg-alpha" },
    ],
    supportCtgs: [],
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
    trackRole: "primary",
    contigId: 8,
  });
  const afterSecond = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: null,
    primaryCtgs: [
      { assemblyCtgId: 8, name: "ctg-beta" },
      { assemblyCtgId: 2, name: "ctg-alpha" },
    ],
    supportCtgs: [],
    subview: afterFirst,
    trackRole: "primary",
    contigId: 2,
  });

  assert.equal(afterFirst.selectedAContigId, 8);
  assert.equal(afterFirst.selectedARole, "primary");
  assert.equal(afterFirst.error, "");
  assert.equal(afterSecond.selectedBContigId, 2);
  assert.equal(afterSecond.selectedBRole, "primary");
  assert.equal(afterSecond.summary, null);
});
