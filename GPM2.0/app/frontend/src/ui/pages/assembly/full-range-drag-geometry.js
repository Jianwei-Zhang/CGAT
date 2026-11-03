// Each edge is projected as scale * (position + motion * deltaPx) + offset.
// Geometry scales with the viewport; glyph extents remain in screen pixels.
export function fitFullRangeDragBounds(edges, deltaPx, viewportWidth) {
  const width = Number(viewportWidth);
  if (!(width > 2) || !Number.isFinite(width) || !Number.isFinite(deltaPx) || !edges.length) {
    throw new RangeError("Invalid Full range drag geometry");
  }
  const points = edges.map(edge => ({ x: edge.position + edge.motion * deltaPx, offset: edge.offset || 0 }));
  if (points.some(point => !Number.isFinite(point.x) || !Number.isFinite(point.offset))) {
    throw new RangeError("Non-finite Full range drag edge");
  }
  const range = scale => {
    let min = Infinity, max = -Infinity;
    for (const point of points) {
      const x = point.x * scale + point.offset;
      min = Math.min(min, x); max = Math.max(max, x);
    }
    return { min, max, width: max - min };
  };
  // Anchor edges with zero offset are included by the DOM compiler, making this
  // an upper bound even for right-aligned/rotated constant-width text.
  const limit = width - 2;
  const labelsClipped = range(0).width > limit;
  // In a window narrower than an unbreakable name, fitting glyphs is impossible.
  // Keep its font intact and fit bars/anchors; the viewport clips the label.
  if (labelsClipped) for (const point of points) point.offset = 0;
  const raw = range(1);
  let minPosition = Infinity, maxPosition = -Infinity;
  for (const point of points) { minPosition = Math.min(minPosition,point.x); maxPosition = Math.max(maxPosition,point.x); }
  let low = 0, high = width / Math.max(1e-9,maxPosition-minPosition);
  if (range(high).width > limit) {
    for (let pass = 0; pass < 30; pass++) {
      const mid = (low + high) / 2;
      if (range(mid).width > limit) high = mid;
      else low = mid;
    }
  } else low = high;
  const scale = Math.max(Number.MIN_VALUE, low);
  const fitted = range(scale);
  return { scale, minX: (fitted.min - 1) / scale, width: width / scale,
    screenMinX: fitted.min - 1, rawWidth: raw.width, labelsClipped };
}

export function multiplyMatrix(left, right) {
  const [a,b,c,d,e,f] = left, [g,h,i,j,k,l] = right;
  return [a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j, a*k+c*l+e, b*k+d*l+f];
}
export function inverseMatrix([a,b,c,d,e,f]) {
  const determinant = a*d-b*c;
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12) throw new RangeError("Singular SVG transform");
  return [d/determinant,-b/determinant,-c/determinant,a/determinant,(c*f-d*e)/determinant,(b*e-a*f)/determinant];
}
export function matrixPoint(matrix, x, y) {
  return [matrix[0]*x+matrix[2]*y+matrix[4],matrix[1]*x+matrix[3]*y+matrix[5]];
}
export const IDENTITY_MATRIX = Object.freeze([1,0,0,1,0,0]);

// Counter-scale the glyph around its own anchor, not around the SVG origin.
// Conjugation through the parent supports rotated labels and nested transforms.
export function fullRangeTextMatrix(original, parent, x, y, scale) {
  const anchor = matrixPoint(original, x, y);
  const linear = [parent[0],parent[1],parent[2],parent[3],0,0];
  const counter = multiplyMatrix(inverseMatrix(linear), multiplyMatrix([1/scale,0,0,1,0,0],linear));
  return multiplyMatrix([1,0,0,1,...anchor], multiplyMatrix(counter,
    multiplyMatrix([1,0,0,1,-anchor[0],-anchor[1]], original)));
}

export function compactFullRangeEdges(edges) {
  const groups = new Map();
  for (const edge of edges) {
    const key = `${edge.motion}:${edge.offset || 0}`;
    const old = groups.get(key);
    if (old) { old.min = Math.min(old.min, edge.position); old.max = Math.max(old.max, edge.position); }
    else groups.set(key, { ...edge, min: edge.position, max: edge.position });
  }
  return [...groups.values()].flatMap(edge => [{ ...edge, position: edge.min }, { ...edge, position: edge.max }]);
}
