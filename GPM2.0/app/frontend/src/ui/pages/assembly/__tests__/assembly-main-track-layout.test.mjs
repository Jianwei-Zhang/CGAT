import {
  test,
  assert,
  renderTracks,
  renderAssemblyPage,
  createState,
} from "./tabs-semantics-harness.mjs";

test("track drag offsets shift only the targeted primary ctg bar and its hit band", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      assembly: {
        trackDragOffsets,
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
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "primary", assemblyCtgId: 8, offsetPx: 120 }]),
  );
  const extractRectX = (html, ctgId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect x for ctg ${ctgId}`);
    return Number(match[1]);
  };
  const extractBandPoints = (html, trackRole, ctgId) => {
    const match = html.match(
      new RegExp(
        `<polygon class="track-collinearity-band(?:\\s+is-companion)?"[^>]*data-band-track-role="${trackRole}"[^>]*data-band-contig-id="${ctgId}"[^>]*points="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected band points for ${trackRole} ctg ${ctgId}`);
    return match[1];
  };

  const baseTargetRectX = extractRectX(baseHtml, 8);
  const movedTargetRectX = extractRectX(movedHtml, 8);
  const baseNeighborRectX = extractRectX(baseHtml, 2);
  const movedNeighborRectX = extractRectX(movedHtml, 2);
  assert.ok(
    Math.abs((movedTargetRectX - baseTargetRectX) - 120) < 0.01,
    `expected target rect shift 120px, got base=${baseTargetRectX}, moved=${movedTargetRectX}`,
  );
  assert.ok(
    Math.abs(movedNeighborRectX - baseNeighborRectX) < 0.01,
    `expected neighbor rect unchanged, got base=${baseNeighborRectX}, moved=${movedNeighborRectX}`,
  );

  assert.notEqual(
    extractBandPoints(baseHtml, "primary", 8),
    extractBandPoints(movedHtml, "primary", 8),
    "expected targeted primary band points to move",
  );
  assert.equal(
    extractBandPoints(baseHtml, "primary", 2),
    extractBandPoints(movedHtml, "primary", 2),
    "expected non-target primary band points to stay",
  );
});

test("track drag offsets also shift support-track ctg bars and their hit bands", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        trackDragOffsets,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
            hits: [
              {
                refStart: 12_000,
                refEnd: 22_000,
                ctgStart: 6_000,
                ctgEnd: 16_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
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
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "support", assemblyCtgId: 30, offsetPx: 96 }]),
  );
  const extractRectXByRole = (html, trackRole, ctgId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${trackRole}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect x for ${trackRole} ctg ${ctgId}`);
    return Number(match[1]);
  };
  const extractBandPoints = (html, trackRole, ctgId) => {
    const match = html.match(
      new RegExp(
        `<polygon class="track-collinearity-band(?:\\s+is-companion)?"[^>]*data-band-track-role="${trackRole}"[^>]*data-band-contig-id="${ctgId}"[^>]*points="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected band points for ${trackRole} ctg ${ctgId}`);
    return match[1];
  };
  const baseX = extractRectXByRole(baseHtml, "support", 30);
  const movedX = extractRectXByRole(movedHtml, "support", 30);
  assert.ok(Math.abs((movedX - baseX) - 96) < 0.01, `expected support rect shift 96px, got ${movedX - baseX}`);
  assert.notEqual(extractBandPoints(baseHtml, "support", 30), extractBandPoints(movedHtml, "support", 30));
});

test("phased track drag offsets target one item instance even when assembly ctg repeats", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 8, displayOrder: 1 }],
          },
          {
            phasedTrackId: 102,
            haplotypeKey: "B",
            label: "Chr01B",
            items: [{ itemId: 9002, phasedTrackId: 102, assemblyCtgId: 8, displayOrder: 1 }],
          },
        ],
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "ctg-beta",
            assignedChrName: "Chr01",
            memberCount: 2,
            totalLength: 600_000,
            anchorStart: 500,
            hits: [],
          },
        ],
      },
    });
  const extractPhasedRectX = (html, itemId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-phased-track-item-id="${itemId}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected phased item ${itemId} rect x`);
    return Number(match[1]);
  };

  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([
      {
        trackRole: "phased",
        assemblyCtgId: 8,
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        offsetPx: 80,
      },
    ]),
  );

  assert.ok(
    Math.abs((extractPhasedRectX(movedHtml, 9001) - extractPhasedRectX(baseHtml, 9001)) - 80) < 0.01,
    "expected only phased item 9001 to move by 80px",
  );
  assert.ok(
    Math.abs(extractPhasedRectX(movedHtml, 9002) - extractPhasedRectX(baseHtml, 9002)) < 0.01,
    "expected repeated ctg instance 9002 to remain fixed",
  );
});

test("phased track drag offsets keep duplicate same-track hit bands item-scoped", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      },
      assembly: {
        activeHitsTrackKey: "A",
        isChrPhased: true,
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 8, displayOrder: 1 },
              { itemId: 9002, phasedTrackId: 101, assemblyCtgId: 8, displayOrder: 2 },
            ],
          },
        ],
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "ctg-beta",
            assignedChrName: "Chr01",
            memberCount: 2,
            totalLength: 600_000,
            anchorStart: 500,
            hits: [
              {
                refStart: 100_000,
                refEnd: 190_000,
                ctgStart: 100_000,
                ctgEnd: 190_000,
                blockLength: 90_001,
                mapq: 60,
                strand: "+",
              },
            ],
          },
        ],
      },
    });
  const extractPhasedBandPoints = (html, itemId) => {
    const match = html.match(
      new RegExp(
        `<polygon class="track-collinearity-band is-phased-track"[^>]*data-band-track-role="phased"[^>]*data-band-contig-id="8"[^>]*data-band-phased-track-item-id="${itemId}"[^>]*points="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected phased item ${itemId} hit band`);
    return match[1];
  };

  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([
      {
        trackRole: "phased",
        assemblyCtgId: 8,
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        offsetPx: 80,
      },
    ]),
  );

  assert.notEqual(extractPhasedBandPoints(movedHtml, 9001), extractPhasedBandPoints(baseHtml, 9001));
  assert.equal(extractPhasedBandPoints(movedHtml, 9002), extractPhasedBandPoints(baseHtml, 9002));
});

test("main track hit bands use backend-projected coordinates for flipped contigs", () => {
  const buildState = (orient, hitRange) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
            orient,
            hits: [
              {
                refStart: 12_000,
                refEnd: 22_000,
                ctgStart: hitRange.ctgStart,
                ctgEnd: hitRange.ctgEnd,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [],
          },
        ],
      },
    });
  const extractBandStartX = (html) => {
    const match = html.match(
      /<polygon class="track-collinearity-band is-companion"[^>]*data-band-track-role="support"[^>]*data-band-contig-id="30"[^>]*points="([^"]+)"/,
    );
    assert.ok(match, "expected support band points");
    return Number(match[1].split(/[ ,]/)[0]);
  };

  const plusStartX = extractBandStartX(
    renderAssemblyPage(buildState("+", { ctgStart: 20_000, ctgEnd: 40_000 })),
  );
  const minusStartX = extractBandStartX(
    renderAssemblyPage(buildState("-", { ctgStart: 960_001, ctgEnd: 980_001 })),
  );

  assert.ok(
    minusStartX > plusStartX,
    `expected backend-projected flipped hit band to stay on the right, got plus=${plusStartX}, minus=${minusStartX}`,
  );
});

test("main track hit bands cross when hit strand opposes ctg display orient", () => {
  const buildState = ({ orient, strand }) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
            orient,
            hits: [
              {
                strand,
                refStart: 12_000,
                refEnd: 22_000,
                ctgStart: 20_000,
                ctgEnd: 40_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [],
          },
        ],
      },
    });
  const extractPoints = (html) => {
    const match = html.match(
      /<polygon class="track-collinearity-band is-companion"[^>]*data-band-track-role="support"[^>]*data-band-contig-id="30"[^>]*points="([^"]+)"/,
    );
    assert.ok(match, "expected support band points");
    return match[1].trim().split(/\s+/).map((point) => {
      const [x, y] = point.split(",").map(Number);
      return { x, y };
    });
  };

  const sameDirectionPoints = extractPoints(renderAssemblyPage(buildState({ orient: "-", strand: "-" })));
  const reversedPoints = extractPoints(renderAssemblyPage(buildState({ orient: "+", strand: "-" })));

  assert.ok(
    sameDirectionPoints[2].x > sameDirectionPoints[3].x,
    `expected non-reversed support band to connect ref right before ref left, got ${JSON.stringify(sameDirectionPoints)}`,
  );
  assert.ok(
    reversedPoints[2].x < reversedPoints[3].x,
    `expected reversed support band to cross by connecting ref left before ref right, got ${JSON.stringify(reversedPoints)}`,
  );
});

test("main-track drag stored in bp stays stable across minTickUnitKb zoom changes", () => {
  const draggedOffsetBp = 180;
  const buildState = ({ minTickUnitKb, trackDragOffsets = [] }) =>
    createState({
      assembly: {
        trackView: {
          minTickUnitKb,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000_000,
            anchorStart: 100,
          },
        ],
        trackDragOffsets,
      },
    });
  const renderMetrics = (html) => {
    const rectMatch = html.match(
      /data-track-contig-id="2"[^>]*data-track-role="primary"[^>]*data-track-rect-x="([^"]+)"/,
    );
    assert.ok(rectMatch, "expected primary ctg rect x");
    const viewMatch = html.match(
      /data-track-role="primary"[\s\S]*?data-track-domain-span-bp="([^"]+)"[\s\S]*?data-track-inner-width="([^"]+)"/,
    );
    assert.ok(viewMatch, "expected primary track domain/width");
    return {
      x: Number(rectMatch[1]),
      domainSpanBp: Number(viewMatch[1]),
      innerWidth: Number(viewMatch[2]),
    };
  };

  const baseFine = renderMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 1000 })));
  const movedFine = renderMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 1000,
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 2, offsetBp: draggedOffsetBp }],
      }),
    ),
  );
  const baseCoarse = renderMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 10000 })));
  const movedCoarse = renderMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 10000,
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 2, offsetBp: draggedOffsetBp }],
      }),
    ),
  );

  const shiftBpFine = ((movedFine.x - baseFine.x) * baseFine.domainSpanBp) / baseFine.innerWidth;
  const shiftBpCoarse = ((movedCoarse.x - baseCoarse.x) * baseCoarse.domainSpanBp) / baseCoarse.innerWidth;

  assert.ok(Math.abs(shiftBpFine - draggedOffsetBp) < 5, `expected fine shift ~${draggedOffsetBp}bp, got ${shiftBpFine}`);
  assert.ok(Math.abs(shiftBpCoarse - draggedOffsetBp) < 5, `expected coarse shift ~${draggedOffsetBp}bp, got ${shiftBpCoarse}`);
  assert.ok(Math.abs(shiftBpFine - shiftBpCoarse) < 5, `expected bp shift stable across zoom, got ${shiftBpFine} vs ${shiftBpCoarse}`);
});

test("main-track drag conversion uses bp-coordinate inner width instead of expanded render width", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000_000,
            anchorStart: 100,
          },
        ],
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 2, offsetPx: -600 }],
      },
    }),
  );

  const trackInnerWidthMatch = html.match(
    /data-track-role="primary"[\s\S]*?data-track-inner-width="([^"]+)"/,
  );
  assert.ok(trackInnerWidthMatch, "expected track inner width dataset");
  const trackInnerWidth = Number(trackInnerWidthMatch[1]);

  const svgWidthMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected primary track svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.ok(
    svgWidth > trackInnerWidth,
    `expected expanded render width (${svgWidth}) > bp-coordinate width (${trackInnerWidth})`,
  );
});

test("subview drag stored in bp stays stable across minTickUnitKb zoom changes", () => {
  const draggedOffsetBp = 1200;
  const buildState = ({ minTickUnitKb, subviewTrackDragOffsets = [] }) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 401,
            name: "support-top",
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
            name: "primary-bottom",
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
          minTickUnitKb,
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
    });
  const extractSubviewMetrics = (html) => {
    const rectMatch = html.match(
      /data-subview-track-slot="bottom"[\s\S]*?data-subview-rect-x="([^"]+)"/,
    );
    assert.ok(rectMatch, "expected subview bottom rect x");
    const viewMatch = html.match(
      /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-domain-span-bp="([^"]+)"[^>]*data-subview-inner-width="([^"]+)"/,
    );
    assert.ok(viewMatch, "expected subview domain/width");
    return {
      x: Number(rectMatch[1]),
      domainSpanBp: Number(viewMatch[1]),
      innerWidth: Number(viewMatch[2]),
    };
  };

  const baseFine = extractSubviewMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 1000 })));
  const movedFine = extractSubviewMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 1000,
        subviewTrackDragOffsets: [{ slot: "bottom", contigId: 201, offsetBp: draggedOffsetBp }],
      }),
    ),
  );
  const baseCoarse = extractSubviewMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 10000 })));
  const movedCoarse = extractSubviewMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 10000,
        subviewTrackDragOffsets: [{ slot: "bottom", contigId: 201, offsetBp: draggedOffsetBp }],
      }),
    ),
  );

  const shiftBpFine = ((movedFine.x - baseFine.x) * baseFine.domainSpanBp) / baseFine.innerWidth;
  const shiftBpCoarse = ((movedCoarse.x - baseCoarse.x) * baseCoarse.domainSpanBp) / baseCoarse.innerWidth;

  assert.ok(Math.abs(shiftBpFine - draggedOffsetBp) < 0.8, `expected fine shift ~${draggedOffsetBp}bp, got ${shiftBpFine}`);
  assert.ok(Math.abs(shiftBpCoarse - draggedOffsetBp) < 0.8, `expected coarse shift ~${draggedOffsetBp}bp, got ${shiftBpCoarse}`);
  assert.ok(Math.abs(shiftBpFine - shiftBpCoarse) < 0.8, `expected bp shift stable across zoom, got ${shiftBpFine} vs ${shiftBpCoarse}`);
});

test("support mirror tracks keep filled bars, share drag offset, and reserve equal tail gap", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
          { datasetId: 33, name: "wtdbg2", label: "wtdbg2" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] }],
      },
      assembly: {
        supportDatasetId: 22,
        trackDragOffsets,
        selectedCtgId: 2,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "wtdbg2",
            chrName: "Chr01",
            assemblyCtgId: 330,
            name: "support-b",
            totalLength: 900_000,
            anchorStart: 130,
            lengthBp: 900_000,
            startBp: 0,
            endBp: 899_999,
            laneIndex: 0,
          },
          {
            datasetId: 22,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 30,
            name: "support-a",
            totalLength: 1_000_000,
            anchorStart: 110,
            lengthBp: 1_000_000,
            startBp: 0,
            endBp: 999_999,
            laneIndex: 0,
          },
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "support", assemblyCtgId: 30, offsetPx: 80 }]),
  );

  assert.match(baseHtml, /flye-镜像轨道/);
  assert.match(baseHtml, /wtdbg2-镜像轨道/);
  assert.match(baseHtml, /class="track-ctg [^"]*is-mirror[^"]*is-companion[^"]*"/);
  assert.match(baseHtml, /data-track-is-mirror="1"/);
  assert.doesNotMatch(baseHtml, /data-band-track-role="support"[^>]*data-band-contig-id="330"/);
  const primaryLabelIndex = baseHtml.indexOf("主(hifiasm)");
  const firstMirrorLabelIndex = baseHtml.indexOf("wtdbg2-镜像轨道");
  const secondMirrorLabelIndex = baseHtml.indexOf("flye-镜像轨道");
  assert.ok(primaryLabelIndex >= 0 && firstMirrorLabelIndex >= 0 && secondMirrorLabelIndex >= 0);
  assert.ok(primaryLabelIndex < firstMirrorLabelIndex);
  assert.ok(firstMirrorLabelIndex < secondMirrorLabelIndex);

  const extractRectX = (html, { ctgId, isMirror }) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="support"[^>]*data-track-is-mirror="${isMirror}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected support rect x for ctg=${ctgId}, mirror=${isMirror}`);
    return Number(match[1]);
  };
  const baseMotherX = extractRectX(baseHtml, { ctgId: 30, isMirror: "0" });
  const movedMotherX = extractRectX(movedHtml, { ctgId: 30, isMirror: "0" });
  const baseMirrorX = extractRectX(baseHtml, { ctgId: 30, isMirror: "1" });
  const movedMirrorX = extractRectX(movedHtml, { ctgId: 30, isMirror: "1" });
  const extractRectY = (html, { ctgId, role, isMirror }) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${role}"[^>]*data-track-is-mirror="${isMirror}"[^>]*data-track-rect-y="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect y for role=${role} ctg=${ctgId}, mirror=${isMirror}`);
    return Number(match[1]);
  };
  const primaryY = extractRectY(baseHtml, { ctgId: 2, role: "primary", isMirror: "0" });
  const firstMirrorY = extractRectY(baseHtml, { ctgId: 330, role: "support", isMirror: "1" });
  const secondMirrorY = extractRectY(baseHtml, { ctgId: 30, role: "support", isMirror: "1" });
  const supportY = extractRectY(baseHtml, { ctgId: 30, role: "support", isMirror: "0" });
  const extractRulerTop = (html) => {
    const match = html.match(/<line class="track-ruler-line"[^>]*y1="([^"]+)"/);
    assert.ok(match, "expected ruler line y1");
    return Number(match[1]);
  };
  const extractSvgHeight = (html) => {
    const match = html.match(/<svg class="assembly-track-svg"[^>]*height="([^"]+)"/);
    assert.ok(match, "expected assembly track svg height");
    return Number(match[1]);
  };
  const mirrorRectMatches = Array.from(
    baseHtml.matchAll(
      /<g class="track-ctg-group[^"]*"[^>]*data-track-role="support"[^>]*data-track-is-mirror="1"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-height="([^"]+)"/g,
    ),
  );
  assert.ok(mirrorRectMatches.length > 0, "expected mirror ctg rect metrics");
  const lastMirrorBottom = Math.max(...mirrorRectMatches.map((match) => Number(match[1]) + Number(match[2])));
  const topGap = supportY - extractRulerTop(baseHtml);
  const bottomGap = extractSvgHeight(baseHtml) - lastMirrorBottom;

  assert.ok(Math.abs((movedMotherX - baseMotherX) - 80) < 0.01);
  assert.ok(Math.abs((movedMirrorX - baseMirrorX) - 80) < 0.01);
  assert.ok(Math.abs((firstMirrorY - primaryY) - 24) < 0.01);
  assert.ok(Math.abs((secondMirrorY - firstMirrorY) - 24) < 0.01);
  assert.ok(Math.abs(bottomGap - topGap) < 0.01, `expected bottom gap (${bottomGap}) == top gap (${topGap})`);
});

test("mirror track label is selectable and support mother selection does not auto-select mirror label", () => {
  const baseState = {
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      supportChrCtgs: [
        {
          assemblyCtgId: 30,
          name: "support-a",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1_000_000,
          anchorStart: 110,
        },
      ],
      supportMirroredCtgs: [
        {
          datasetId: 22,
          datasetName: "flye",
          chrName: "Chr01",
          assemblyCtgId: 30,
          name: "support-a",
          totalLength: 1_000_000,
          anchorStart: 110,
          lengthBp: 1_000_000,
          startBp: 0,
          endBp: 999_999,
          laneIndex: 0,
        },
      ],
    },
  };

  const html = renderAssemblyPage(createState(baseState));
  assert.match(
    html,
    /<div class="assembly-track-label-row[^"]*is-mirror-track[^"]*"[^>]*data-track-label-role="support"[^>]*data-track-label-selectable="1"[^>]*>[\s\S]*flye-镜像轨道/,
  );

  const selectedHtml = renderAssemblyPage(
    createState({
      ...baseState,
      assembly: {
        ...baseState.assembly,
        subview: {
          selectedTrackARole: "support",
          selectedTrackBRole: "",
        },
      },
    }),
  );
  assert.match(
    selectedHtml,
    /<div class="assembly-track-label-row[^"]*is-companion[^"]*is-subview-track-selected[^"]*"[^>]*>[\s\S]*辅\(flye\)/,
  );
  assert.doesNotMatch(
    selectedHtml,
    /<div class="assembly-track-label-row[^"]*is-mirror-track[^"]*is-subview-track-selected[^"]*"[^>]*>[\s\S]*flye-镜像轨道/,
  );
});

test("subview support track selection highlights only the matching dataset/source label", () => {
  const html = renderAssemblyPage(
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
          { datasetId: 33, name: "canu2", label: "canu2" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "flye-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "canu2",
            chrName: "Chr01",
            assemblyCtgId: 1914,
            name: "canu2-a",
            totalLength: 900_000,
            anchorStart: 130,
            lengthBp: 900_000,
            startBp: 0,
            endBp: 899_999,
            laneIndex: 0,
          },
        ],
        subview: {
          selectedTrackARole: "support",
          selectedTrackBRole: "primary",
          selectedTrackBSource: "mother",
          selectedTrackBDatasetId: 22,
          selectedTrackBIsMirror: false,
        },
      },
    }),
  );

  assert.match(
    html,
    /<div class="assembly-track-label-row[^"]*is-companion[^"]*is-subview-track-selected[^"]*"[^>]*data-track-label-source="mother"[^>]*data-track-label-dataset-id="22"[^>]*>[\s\S]*辅\(flye\)/,
  );
  assert.doesNotMatch(
    html,
    /<div class="assembly-track-label-row[^"]*is-mirror-track[^"]*is-subview-track-selected[^"]*"[^>]*data-track-label-source="mirror"[^>]*data-track-label-dataset-id="33"[^>]*>[\s\S]*canu2-mirror/,
  );
});

test("reference track label is selectable for subview-track and ref members expose ref track metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 10100, chrLength: 10100 }],
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-5000",
            referenceChrName: "Chr01",
            segmentStartBp: 1,
            segmentEndBp: 5000,
            anchorStart: 1,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
        ],
      },
    }),
  );

  assert.match(
    html,
    /<div class="assembly-track-label-row[^"]*is-ref[^"]*is-track-selectable[^"]*"[^>]*data-track-label-role="ref"[^>]*data-track-label-selectable="1"[^>]*data-track-label-is-mirror="0"[^>]*>/,
  );
  assert.match(
    html,
    /data-track-contig-id="9001"[^>]*data-track-role="ref"[^>]*data-track-source-kind="ref_segment"[^>]*data-track-reference-chr-name="Chr01"[^>]*data-track-segment-start="1"[^>]*data-track-segment-end="5000"/,
  );
  assert.match(
    html,
    /<text[^>]*class="track-ctg-label track-reference-member-label[^"]*"[^>]*data-track-label-for-contig-id="9001"[^>]*data-track-label-role="ref"[^>]*data-track-label-is-mirror="0"[^>]*>ref_Chr01:1-5000 \(\+\)<\/text>/,
  );
  assert.doesNotMatch(html, /data-track-label-source="mirror"[^>]*data-track-label-role="ref"/);
});

test("subview 2-contig keeps ref bars and labels on the ref gray palette", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-5000",
            referenceChrName: "Chr01",
            segmentStartBp: 1,
            segmentEndBp: 5000,
            anchorStart: 1,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 9001,
          selectedARole: "ref",
          selectedBContigId: 2,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 9001, role: "ref", contigName: "ref_Chr01:1-5000" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
    }),
  );

  assert.match(html, /<div class="assembly-track-label-row is-ref"[^>]*>ref_Chr01:1-5000<\/div>/);
  assert.match(html, /data-subview-track-slot="top"[\s\S]*class="track-ctg subview-track-ctg is-ref"/);
  assert.match(html, /<text class="track-ctg-label[^"]*is-ref[^"]*"[^>]*data-subview-label-slot="top"/);
  const subviewSvg = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/)?.[0] || "";
  assert.match(subviewSvg, /data-subview-virtual-ruler="1"/);
  assert.doesNotMatch(subviewSvg, /track-tick-guide/);
});

test("Subview renderer keeps fine-scale ruler serialization bounded", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      supportChrCtgs: [{
        assemblyCtgId: 30,
        name: "support-43mb",
        assignedChrName: "Chr01",
        totalLength: 43_726_252,
        anchorStart: 1,
        hits: [],
      }],
      chrCtgs: [{
        assemblyCtgId: 2,
        name: "primary-43mb",
        assignedChrName: "Chr01",
        totalLength: 43_726_252,
        anchorStart: 1,
        hits: [],
      }],
      subviewTrackView: {
        minTickUnitKb: 1,
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
        summary: {
          mode: "2-contig",
          top: { contigId: 2, role: "primary", contigName: "primary-43mb" },
          bottom: { contigId: 30, role: "support", contigName: "support-43mb" },
        },
      },
    },
  }));
  const subviewSvg = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/)?.[0] || "";

  assert.match(subviewSvg, /data-subview-virtual-ruler="1"/);
  assert.doesNotMatch(subviewSvg, /track-tick-guide/);
});

test("subview 2-contig hides labels that do not fit inside bars and keeps hover titles", () => {
  const mainLabel = "main-very-long-subview-contig-label";
  const supportLabel = `support-${"very-long-".repeat(28)}subview-contig-label`;
  const html = renderAssemblyPage(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "primary" },
            bottom: { contigId: 30, role: "support" },
          },
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: mainLabel,
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: supportLabel,
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 500_000,
            anchorStart: 10,
          },
        ],
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

  assert.equal(html.includes(`data-subview-label-contig-id="2">${mainLabel} (+)</text>`), false);
  assert.equal(html.includes(`data-subview-label-contig-id="30">${supportLabel} (+)</text>`), false);
  assert.match(html, new RegExp(`<title>${mainLabel} \\|`));
  assert.match(html, new RegExp(`<title>${supportLabel} \\|`));
});

test("subview 2-contig renders anchor fragments for ref members using ref-side hits", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "-",
            hits: [
              {
                hitId: 1,
                datasetId: 11,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-alpha",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
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
          selectedAContigId: 9001,
          selectedARole: "ref",
          selectedBContigId: 2,
          selectedBRole: "primary",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 9001, role: "ref", contigName: "ref_Chr01:1001-2000" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
    }),
  );

  assert.match(
    html,
    /class="subview-anchor-line is-active"[^>]*stroke="red"/,
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-role="ref"[^>]*data-subview-fragment-contig-id="9001"[^>]*data-subview-fragment-start="1"[^>]*data-subview-fragment-end="500"[^>]*data-subview-fragment-ref-orient="-"/,
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-source-kind="ref_segment"[^>]*data-subview-fragment-reference-chr-name="Chr01"[^>]*data-subview-fragment-segment-start-bp="1001"[^>]*data-subview-fragment-segment-end-bp="2000"/,
  );
});

test("subview 2-contig projects only the selected ds hit set onto the ref member", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "+",
            hits: [
              {
                hitId: 1,
                datasetId: 11,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
              {
                hitId: 2,
                datasetId: 11,
                sourceSeqId: 99,
                strand: "+",
                queryStart: 120,
                queryEnd: 420,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            datasetId: 11,
            name: "primary-target",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          supportDsCtgLen: 0,
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedAContigId: 9001,
          selectedARole: "ref",
          selectedBContigId: 2,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 9001, role: "ref" },
            bottom: { contigId: 2, role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*"/g) || [];
  assert.equal(polygons.length, 1);
});

test("render-tracks filters ref subview members to the selected support dataset", () => {
  assert.equal(typeof renderTracks.__testBuildFilteredRefSubviewCtgs, "function");

  const result = renderTracks.__testBuildFilteredRefSubviewCtgs({
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        referenceChrName: "Chr01",
        segmentStartBp: 1,
        segmentEndBp: 5000,
        anchorStart: 1,
        totalLength: 5000,
        refOrient: "+",
        hits: [
          { datasetId: 22, refStart: 100, refEnd: 400, ctgStart: 1, ctgEnd: 300 },
          { datasetId: 33, refStart: 600, refEnd: 900, ctgStart: 1, ctgEnd: 300 },
        ],
      },
    ],
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
        bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
      },
    },
    primaryDatasetId: 11,
  });

  assert.deepEqual(result[0].hits.map((hit) => hit.datasetId), [22]);
});

test("render-tracks reuses cached ref segment pairing for identical inputs", () => {
  assert.equal(typeof renderTracks.__testPairRefSubviewSegmentsWithCache, "function");

  const topSegments = [
    { refStart: 100, refEnd: 400, hitKey: "top-hit", x: 0, width: 10 },
  ];
  const bottomSegments = [
    { refStart: 100, refEnd: 400, hitKey: "bottom-hit", x: 0, width: 10 },
  ];

  const first = renderTracks.__testPairRefSubviewSegmentsWithCache({
    cacheKey: "Chr01:track-pair:22:10000:0",
    topSegments,
    bottomSegments,
    trackMode: "track-pair",
  });
  const second = renderTracks.__testPairRefSubviewSegmentsWithCache({
    cacheKey: "Chr01:track-pair:22:10000:0",
    topSegments,
    bottomSegments,
    trackMode: "track-pair",
  });

  assert.equal(second, first);
});

test("subview track-pair keeps ref track bars and labels on the ref gray palette", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-500000",
            referenceChrName: "Chr01",
            segmentStartBp: 1,
            segmentEndBp: 500000,
            anchorStart: 1,
            totalLength: 500000,
            refOrient: "+",
            hits: [],
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "ref", isMirror: false },
            bottomTrack: { role: "primary", isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
        },
      },
    }),
  );

  assert.match(html, /<div class="assembly-track-label-row is-ref"[^>]*>ref_chr1<\/div>/);
  assert.match(html, /data-subview-track-slot="top"[\s\S]*class="track-ctg subview-track-ctg is-ref"/);
  assert.match(html, /<text class="track-ctg-label[^"]*is-ref[^"]*"[^>]*data-subview-label-slot="top"/);
});

test("subview track-pair hides labels that do not fit inside bars and keeps hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-very-long-trackpair-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-very-long-trackpair-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
            bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
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

  assert.doesNotMatch(
    html,
    /data-subview-label-slot="bottom"[^>]*>primary-very-long-trackpair-label \(\+\)<\/text>/,
  );
  assert.doesNotMatch(
    html,
    /data-subview-label-slot="top"[^>]*>support-very-long-trackpair-label \(\+\)<\/text>/,
  );
  assert.match(html, /<title>primary-very-long-trackpair-label \|/);
  assert.match(html, /<title>support-very-long-trackpair-label \|/);
});

test("subview track-pair renders anchor fragments for ref members using ref-side hits", () => {
  const stablePairHitKey = "pair:9001:hit-1:2:hit-1";
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "-",
            hits: [
              {
                hitId: 1,
                datasetId: 11,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-alpha",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
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
          selectedTrackARole: "ref",
          selectedTrackBRole: "primary",
          activeAnchors: [{ hitKey: stablePairHitKey, edge: "left" }],
          summary: {
            mode: "track-pair",
            topTrack: { role: "ref", isMirror: false },
            bottomTrack: { role: "primary", isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
        },
      },
    }),
  );

  assert.match(
    html,
    new RegExp(`class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="${stablePairHitKey}"[^>]*data-subview-anchor-edge="left"`),
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-role="ref"[^>]*data-subview-fragment-contig-id="9001"[^>]*data-subview-fragment-start="1"[^>]*data-subview-fragment-end="500"/,
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-source-kind="ref_segment"[^>]*data-subview-fragment-reference-chr-name="Chr01"/,
  );
});

test("subview track-pair ref projection keeps only support members visible in the main track", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 10000,
          mapq: 0,
        },
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            datasetId: 22,
            name: "support-hidden",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
          {
            assemblyCtgId: 31,
            datasetId: 22,
            name: "support-visible",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
        ],
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "+",
            hits: [
              {
                hitId: 1,
                datasetId: 22,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
              {
                hitId: 2,
                datasetId: 22,
                sourceSeqId: 2,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        subviewTrackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackSelections: [
            { role: "ref", source: "mother", datasetId: null, isMirror: false },
            { role: "support", source: "mother", datasetId: 22, isMirror: false },
          ],
          selectedTrackARole: "ref",
          selectedTrackBRole: "support",
          selectedTrackBSource: "mother",
          selectedTrackBDatasetId: 22,
          selectedTrackBIsMirror: false,
          summary: {
            mode: "track-pair",
            topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
            bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
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
  const polygons = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*"/g) || [];
  assert.equal(polygons.length, 1);
  assert.match(html, /support-visible/);
  assert.doesNotMatch(html, /support-hidden/);
});

test("hidden primary ctg bar still applies drag offsets", () => {
  const baseHtml = renderAssemblyPage(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [8],
        trackDragOffsets: [],
      },
    }),
  );
  const movedHtml = renderAssemblyPage(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [8],
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 8, offsetPx: 80 }],
      },
    }),
  );
  const extractRectX = (html, ctgId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*is-hidden-contig[^"]*"[^>]*data-track-contig-id="${ctgId}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected hidden rect x for ctg ${ctgId}`);
    return Number(match[1]);
  };
  const baseX = extractRectX(baseHtml, 8);
  const movedX = extractRectX(movedHtml, 8);
  assert.ok(Math.abs((movedX - baseX) - 80) < 0.01, `expected hidden rect shift 80px, got ${movedX - baseX}`);
});

test("within the same track lane, shorter overlapping ctg bars render above longer bars", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 200_000,
            anchorStart: 2_500_000,
          },
        ],
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 8, offsetPx: -520 }],
      },
    }),
  );

  const extractRectMetrics = (markup, ctgId) => {
    const match = markup.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="primary"[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect metrics for primary ctg ${ctgId}`);
    return {
      x: Number(match[1]),
      y: Number(match[2]),
      width: Number(match[3]),
    };
  };

  const longRect = extractRectMetrics(html, 2);
  const shortRect = extractRectMetrics(html, 8);
  assert.equal(shortRect.y, longRect.y, "expected both ctgs on the same lane");
  assert.ok(
    shortRect.x < longRect.x + longRect.width && shortRect.x + shortRect.width > longRect.x,
    "expected dragged short ctg to overlap long ctg",
  );

  const longMarkupIndex = html.indexOf(`data-track-contig-id="2" data-track-role="primary"`);
  const shortMarkupIndex = html.indexOf(`data-track-contig-id="8" data-track-role="primary"`);
  assert.ok(longMarkupIndex >= 0 && shortMarkupIndex >= 0, "expected both primary ctg groups in svg");
  assert.ok(shortMarkupIndex > longMarkupIndex, "expected shorter ctg to render after longer ctg (on top)");
});

test("negative drag offsets extend left scrollable range in main track view", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      assembly: {
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 300,
          },
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "primary", assemblyCtgId: 2, offsetPx: -220 }]),
  );

  const parseMainTrackWidth = (html) => {
    const svgMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
    assert.ok(svgMatch, "expected main track svg width");
    return Number(svgMatch[1]);
  };
  const parsePrimaryViewboxMinX = (html) => {
    const match = html.match(
      /class="assembly-track-scroll"[\s\S]*?data-track-role="primary"[\s\S]*?data-track-viewbox-min-x="([^"]+)"/,
    );
    assert.ok(match, "expected main track viewBox min-x");
    return Number(match[1]);
  };

  const baseWidth = parseMainTrackWidth(baseHtml);
  const movedWidth = parseMainTrackWidth(movedHtml);
  const movedViewboxMinX = parsePrimaryViewboxMinX(movedHtml);

  assert.ok(movedViewboxMinX < 0, `expected negative viewBox min-x, got ${movedViewboxMinX}`);
  assert.ok(movedWidth > baseWidth, `expected moved width (${movedWidth}) > base width (${baseWidth})`);
  assert.match(
    movedHtml,
    new RegExp(`<svg class="assembly-track-svg"[^>]*viewBox="${movedViewboxMinX} 0 ${movedWidth} `),
  );
});
