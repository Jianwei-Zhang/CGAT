import {
  test,
  assert,
  renderAssemblyPage,
  createState,
} from "./tabs-semantics-harness.mjs";

function buildSubviewCtgOverflowHtml(subviewTrackDragOffsets = []) {
  return renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 401,
            name: "support-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5_000,
            anchorStart: 320,
            hits: [
              {
                refStart: 5_000,
                refEnd: 8_000,
                ctgStart: 1_000,
                ctgEnd: 4_000,
                blockLength: 3_000,
                mapq: 60,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 201,
            name: "primary-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30_000,
            anchorStart: 100,
            hits: [
              {
                refStart: 5_000,
                refEnd: 8_000,
                ctgStart: 26_000,
                ctgEnd: 29_000,
                blockLength: 3_000,
                mapq: 60,
              },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 10_000,
          maxTickCount: 10,
          alignmentLength: 1_000,
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
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );
}

function extractSubviewGeometry(html, slot) {
  const scrollTagMatch = html.match(
    /<div[^>]*class="assembly-track-scroll subview-track-scroll"[^>]*>/,
  );
  assert.ok(scrollTagMatch, "expected subview scroll geometry metadata");
  const innerWidthMatch = scrollTagMatch[0].match(/data-subview-inner-width="([^"]+)"/);
  assert.ok(innerWidthMatch, "expected subview base inner width");
  const viewBoxMinXMatch = scrollTagMatch[0].match(/data-subview-viewbox-min-x="([^"]+)"/);
  const svgMatch = html.match(
    /<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"[^>]*viewBox="([^"]+)"/,
  );
  assert.ok(svgMatch, "expected subview SVG geometry");
  const groupMatch = html.match(
    new RegExp(
      `<g[^>]*data-subview-track-slot="${slot}"[\\s\\S]*?data-subview-rect-x="([^"]+)"[\\s\\S]*?data-subview-rect-width="([^"]+)"`,
    ),
  );
  assert.ok(groupMatch, `expected ${slot} subview contig geometry`);
  const viewBox = svgMatch[2].trim().split(/\s+/).map(Number);
  return {
    baseInnerWidth: Number(innerWidthMatch[1]),
    viewBoxMinX: Number(viewBoxMinXMatch?.[1] || 0),
    svgWidth: Number(svgMatch[1]),
    viewBoxWidth: viewBox[2],
    barX: Number(groupMatch[1]),
    barWidth: Number(groupMatch[2]),
  };
}

test("subview-ctg expands right render extent for a short contig already aligned to the edge", () => {
  const base = extractSubviewGeometry(buildSubviewCtgOverflowHtml(), "top");
  const shifted = extractSubviewGeometry(
    buildSubviewCtgOverflowHtml([{ slot: "top", contigId: 401, offsetPx: 120 }]),
    "top",
  );

  assert.ok(
    Math.abs((shifted.barX - base.barX) - 120) < 0.1,
    `expected top contig to cross the right edge by 120px, got ${shifted.barX - base.barX}`,
  );
  assert.equal(shifted.baseInnerWidth, base.baseInnerWidth);
  assert.equal(shifted.viewBoxMinX, 0);
  assert.ok(shifted.svgWidth > shifted.baseInnerWidth);
  assert.equal(shifted.svgWidth, shifted.viewBoxWidth);
  assert.ok(shifted.barX + shifted.barWidth <= shifted.viewBoxMinX + shifted.svgWidth);
});

test("subview-ctg expands the left viewBox without changing its bp scale", () => {
  const base = extractSubviewGeometry(buildSubviewCtgOverflowHtml(), "bottom");
  const shifted = extractSubviewGeometry(
    buildSubviewCtgOverflowHtml([{ slot: "bottom", contigId: 201, offsetPx: -120 }]),
    "bottom",
  );

  assert.ok(
    Math.abs((shifted.barX - base.barX) + 120) < 0.1,
    `expected bottom contig to cross the left edge by 120px, got ${shifted.barX - base.barX}`,
  );
  assert.equal(shifted.baseInnerWidth, base.baseInnerWidth);
  assert.equal(shifted.viewBoxMinX, -120);
  assert.equal(shifted.svgWidth, shifted.baseInnerWidth + 120);
  assert.equal(shifted.svgWidth, shifted.viewBoxWidth);
});
