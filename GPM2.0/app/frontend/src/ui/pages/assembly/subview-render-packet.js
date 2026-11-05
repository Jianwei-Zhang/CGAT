// Split only renderer-owned self-closing dense SVG primitives. Wrappers,
// clipping, draw order, active anchors and scientific metadata stay untouched.
export const SUBVIEW_RENDER_BATCH_SIZE = 384;
export function splitSubviewRenderMarkup(html, batchSize = SUBVIEW_RENDER_BATCH_SIZE) {
  const batches = [];
  const dense = /<(?:polygon|line)\b[^>]*class="(?:track-collinearity-band|subview-anchor-hit-zone|subview-anchor-line)[^"]*"[^>]*\/>/g;
  let skeleton = "", cursor = 0, run = [], runStart = 0, runEnd = 0;
  const flush = () => {
    if (!run.length) return;
    skeleton += html.slice(cursor, runStart) + `<g data-subview-render-batch="${batches.length}"></g>`;
    batches.push(run.join("")); cursor = runEnd; run = [];
  };
  for (const match of html.matchAll(dense)) {
    // Active/manual endpoint descriptors must be available immediately to
    // Main -> Local edits even while inactive hit targets are still loading.
    if (/class="[^"]*\bis-active\b/.test(match[0])) { flush(); continue; }
    if (run.length && (run.length >= batchSize || html.slice(runEnd, match.index).trim())) flush();
    if (!run.length) runStart = match.index;
    run.push(match[0]); runEnd = match.index + match[0].length;
  }
  flush();
  skeleton += html.slice(cursor);
  return { skeleton, batches };
}

// Shallow immutable deltas avoid cloning unchanged, potentially very large hit
// arrays on every release. No transfer list: the live store must keep its data.
export function buildSubviewRenderDelta(state, previous) {
  const delta = {};
  for (const key of ["locale", "activeRoute", "session", "initializer"]) {
    if (!previous || state[key] !== previous[key]) delta[key] = state[key];
  }
  const assembly = {};
  for (const key of new Set([...Object.keys(previous?.assembly || {}), ...Object.keys(state.assembly || {})])) {
    if (!previous || state.assembly?.[key] !== previous.assembly?.[key]) assembly[key] = state.assembly?.[key];
  }
  delta.assembly = assembly;
  return delta;
}

export function applySubviewRenderDelta(state, delta) {
  return { ...state, ...delta, assembly: { ...state?.assembly, ...delta.assembly } };
}
