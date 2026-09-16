import test from "node:test";
import assert from "node:assert/strict";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";

// gs3 Chr05: the short ctg and its reference hit both span 179,256 bp.
const ctgs = [
  { assemblyCtgId: 15, name: "left", totalLength: 15204261, anchorStart: 3 },
  { assemblyCtgId: 33, name: "short", totalLength: 179280, anchorStart: 15192530,
    orient: "+", hits: [{ ctgStart: 9, ctgEnd: 179264, refStart: 15192530, refEnd: 15371785, blockLength: 179257, strand: "+" }] },
  { assemblyCtgId: 1, name: "right", totalLength: 17266739, anchorStart: 15372059 },
];
const members = [
  { segmentStartBp: 1, segmentEndBp: 15192421 },
  { segmentStartBp: 15192522, segmentEndBp: 15371864 },
  { segmentStartBp: 15371965, segmentEndBp: 32638756 },
];

function render(items = ctgs, trackDragOffsets = []) {
  return renderAssemblyPage(createState({ assembly: {
    selectedChrName: "Chr05", chromosomes: [{ chrName: "Chr05", chrLength: 32638756 }],
    selectedCtgId: 15, chrCtgs: items, supportDatasetId: 22,
    supportChrCtgs: items.map(ctg => ({ ...ctg, assemblyCtgId: ctg.assemblyCtgId + 100 })),
    refTrackMembers: members, trackDragOffsets,
    trackView: { alignmentLength: 10000, supportDsCtgLen: 0 },
  }, initializer: {
    datasets: [{ datasetId: 11, name: "hifiasm" }, { datasetId: 22, name: "flye" }],
    existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
  } }));
}

function rect(html, role, id) {
  const match = html.match(new RegExp(`<g class="track-ctg-group[^>]*data-track-contig-id="${id}"[^>]*data-track-role="${role}"[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`));
  assert.ok(match, `missing ${role} ctg ${id}`);
  return { x: +match[1], width: +match[3] };
}

function band(html, role, id) {
  const match = html.match(new RegExp(`<polygon class="track-collinearity-band[^>]*data-band-track-role="${role}"[^>]*data-band-contig-id="${id}"[^>]*points="([^"]+)"`));
  assert.ok(match, `missing ${role} band ${id}`);
  return match[1].split(/\s+/).map(point => +point.split(",")[0]);
}

test("main ds tracks keep the reference bp scale even for a short ctg between large neighbours", () => {
  const html = render();
  const ref = html.match(/class="track-reference-member[^\"]*"\s+x="[^\"]+"[\s\S]*?width="([\d.]+)"/);
  assert.ok(ref);
  const pxPerBp = +ref[1] / 15192421;
  for (const [role, offset] of [["primary", 0], ["support", 100]]) {
    const boxes = ctgs.map(ctg => rect(html, role, ctg.assemblyCtgId + offset));
    boxes.forEach((box, index) => {
      assert.ok(Math.abs(box.width - ctgs[index].totalLength * pxPerBp) < 0.03, `${role} ctg ${index} preserves width`);
      if (index) assert.ok(box.x - boxes[index - 1].x - boxes[index - 1].width >= 19.98);
    });
    const xs = band(html, role, 33 + offset);
    assert.ok(Math.abs(Math.abs(xs[1] - xs[0]) - Math.abs(xs[3] - xs[2])) < 0.02, `${role} equal bp spans have equal band widths`);
  }
});

test("deleting a neighbour or dragging the short ctg preserves widths and band attachment", () => {
  const base = render();
  const afterDelete = render(ctgs.slice(1));
  const moved = render(ctgs, [{ trackRole: "primary", assemblyCtgId: 33, offsetPx: 120 }]);
  const baseRect = rect(base, "primary", 33);
  assert.equal(rect(afterDelete, "primary", 33).width, baseRect.width);
  assert.equal(rect(moved, "primary", 33).width, baseRect.width);
  assert.ok(Math.abs(rect(moved, "primary", 33).x - baseRect.x - 120) < 0.02);
  const before = band(base, "primary", 33), after = band(moved, "primary", 33);
  assert.deepEqual(after.slice(0, 2), before.slice(0, 2));
  for (let i = 2; i < 4; i++) assert.ok(Math.abs(after[i] - before[i] - 120) < 0.02);
  assert.deepEqual(rect(moved, "primary", 1), rect(base, "primary", 1));
});
