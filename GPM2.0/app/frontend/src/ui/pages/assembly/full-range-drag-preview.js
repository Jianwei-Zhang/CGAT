import { compileTrackDragPreview } from "./track-drag-preview-runtime.js";
import { buildVisibleSubviewRulerMarkup } from "./subview-ruler-runtime.js";
import { resolveTickBpFromScale } from "./track-prefs.js";
import { compactFullRangeEdges, fitFullRangeDragBounds, fullRangeTextMatrix,
  IDENTITY_MATRIX, inverseMatrix, matrixPoint, multiplyMatrix } from "./full-range-drag-geometry.js";

const PREVIEW_CLASS = "is-full-range-drag-preview";
const matrixValues = matrix => matrix ? [matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f] : [...IDENTITY_MATRIX];
const number = (node, name, fallback = 0) => {
  const raw = node.getAttribute(name);
  return raw === null || raw === "" ? fallback : Number(raw);
};
const tag = node => String(node.localName || node.tagName || "").toLowerCase();
const serializeMatrix = matrix => `matrix(${matrix.join(",")})`;


function captureGeometry(svg, plan, composition) {
  const svgInverse = inverseMatrix(matrixValues(svg.getCTM()));
  const matrices = new WeakMap();
  const relative = node => {
    if (!matrices.has(node)) matrices.set(node,multiplyMatrix(svgInverse,matrixValues(node.getCTM())));
    return matrices.get(node);
  };
  const actions = new Map(plan.actions.map(action => [action.node, action]));
  const groupMotion = node => {
    let motion = 0;
    for (let parent = node.parentNode; parent && parent !== svg; parent = parent.parentNode) {
      const action = actions.get(parent);
      if (action?.kind === "group") motion += relative(parent.parentNode)[0] * action.factor;
    }
    return motion;
  };
  const edges = [], texts = [];
  // Match the renderer's fit envelope: bars and labels, not every CIGAR band
  // and transparent anchor hit-zone. Their endpoints are already inside bars.
  for (const node of svg.querySelectorAll("rect.track-ctg, rect.track-reference-member, rect.track-reference-bar, text")) {
    if (node.closest("defs, clipPath, mask") || node.closest("[data-subview-virtual-ruler]")) continue;
    if (composition && node.classList.contains("track-ruler-line")) continue;
    const matrix = relative(node), motion = groupMotion(node), action = actions.get(node);
    const add = (x, y, extra = 0, offset = 0) => {
      edges.push({ position: matrixPoint(matrix, x, y)[0], motion: motion + matrix[0] * extra, offset });
    };
    const box = node.getBBox();
    if (![box.x,box.y,box.width,box.height].every(Number.isFinite)) throw new RangeError("Invalid SVG bounds");
    if (tag(node) === "text") {
      const x = number(node,"x"), y = number(node,"y"), extra = action?.kind === "text" ? action.factor : 0;
      const parent = relative(node.parentNode);
      const moveFactor = ["sticky","group"].includes(action?.kind) ? action.factor : 0;
      const textMotion = motion+matrix[0]*extra+parent[0]*moveFactor;
      const anchor = matrixPoint(matrix,x,y)[0];
      edges.push({position:anchor,motion:textMotion,offset:0});
      for (const cx of [box.x,box.x+box.width]) for (const cy of [box.y,box.y+box.height]) {
        edges.push({ position: anchor, motion: textMotion, offset: matrixPoint(matrix,cx,cy)[0]-anchor });
      }
      texts.push({ node, x, y, extra, moveFactor, original: multiplyMatrix(inverseMatrix(parent),matrix), parent });
    } else {
      for (const cx of [box.x,box.x+box.width]) for (const cy of [box.y,box.y+box.height]) add(cx,cy);
    }
  }
  return { edges: compactFullRangeEdges(edges), texts };
}

// One handle per gesture. It owns only this rendered scroll/SVG and never
// writes store state, source data, history or a newer graph's DOM.
export function createFullRangeDragPreview(scroll, payload, { subview = false, prefs = {} } = {}) {
  const svg = scroll?.querySelector("svg.assembly-track-svg");
  if (!svg || typeof svg.getCTM !== "function") throw new TypeError("Full range drag requires an SVG graph");
  const prefix = subview ? "subview" : "track";
  const domainSpan = number(scroll,`data-${prefix}-domain-span-bp`);
  const innerWidth = number(scroll,`data-${prefix}-inner-width`);
  const windowStart = number(scroll,`data-${prefix}-window-start-bp`);
  const viewportWidth = scroll.clientWidth;
  const viewBox = String(svg.getAttribute("viewBox")).trim().split(/\s+/).map(Number);
  if (!(domainSpan > 0 && innerWidth > 0 && viewportWidth > 2) || viewBox.length !== 4 || !viewBox.every(Number.isFinite)) {
    throw new RangeError("Invalid Full range viewport");
  }
  const restore = [], saved = new WeakMap();
  const remember = (node, name) => {
    let names = saved.get(node);
    if (!names) { names = new Set(); saved.set(node,names); }
    if (names.has(name)) return;
    names.add(name);
    const value = node.getAttribute(name);
    restore.push(() => value === null ? node.removeAttribute(name) : node.setAttribute(name,value));
  };
  const set = (node,name,value) => { remember(node,name); node.setAttribute(name,String(value)); };
  const plan = compileTrackDragPreview(scroll,payload,{subview});
  const composition = subview && Boolean(scroll.closest("[data-subview-composition-scene]"));
  const ruler = svg.querySelector("[data-subview-virtual-ruler]");
  const rulerLine = svg.querySelector(".track-ruler-line");
  const rulerOptions = ruler ? Object.fromEntries(["window-start","window-end","tick-bp","inner-width","domain-span-bp","edge-label-padding","origin-x","tick-y1","tick-y2","tick-label-y"]
    .map(key => [key.replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase()),number(ruler,`data-subview-ruler-${key}`)])) : null;
  if (ruler) {
    const markup = ruler.innerHTML;
    restore.push(() => { ruler.innerHTML = markup; });
  }
  const oldScrollLeft = scroll.scrollLeft;
  restore.push(() => { scroll.scrollLeft = oldScrollLeft; });
  scroll.classList.add(PREVIEW_CLASS);
  let geometry;
  try { geometry = captureGeometry(svg,plan,composition); }
  catch (error) { scroll.classList.remove(PREVIEW_CLASS); throw error; }
  for (const text of geometry.texts) remember(text.node,"style");
  if (!composition) geometry.edges.push({ position:0,motion:0,offset:0 },{ position:innerWidth,motion:0,offset:0 });
  else geometry.edges.push({ position:0,motion:0,offset:0 });
  const clips = [...svg.querySelectorAll("[data-subview-band-clip-rect]")];
  const memberEnds = composition ? [...svg.querySelectorAll("[data-subview-rect-x][data-subview-rect-width]")].map(node => {
    const action = plan.actions.find(item => item.node === node && item.kind === "group");
    return { position:number(node,"data-subview-rect-x")+number(node,"data-subview-rect-width"),motion:action?.factor || 0 };
  }) : [];
  const first = svg.firstElementChild;
  const children = svg.childElementCount;
  let restored = false;
  return {
    isCurrent: () => !restored && scroll.isConnected !== false && svg.isConnected !== false
      && scroll.contains(svg) && svg.firstElementChild === first && svg.childElementCount === children
      && scroll.clientWidth === viewportWidth,
    update(deltaBp) {
      if (restored) return false;
      const deltaPx = Number(deltaBp)*innerWidth/domainSpan;
      const fit = fitFullRangeDragBounds(geometry.edges,deltaPx,viewportWidth);
      plan.apply(deltaPx);
      set(svg,"width",viewportWidth);
      set(svg,"preserveAspectRatio","none");
      set(svg,"viewBox",`${fit.minX} ${viewBox[1]} ${fit.width} ${viewBox[3]}`);
      for (const text of geometry.texts) {
        const moved = multiplyMatrix([1,0,0,1,text.moveFactor*deltaPx,0],text.original);
        text.node.style.transform = serializeMatrix(fullRangeTextMatrix(
          moved,text.parent,text.x+text.extra*deltaPx,text.y,fit.scale));
      }
      for (const clip of clips) { set(clip,"x",fit.minX); set(clip,"width",fit.width); }
      const projectedInnerWidth = innerWidth*fit.scale;
      set(scroll,`data-${prefix}-inner-width`,projectedInnerWidth);
      set(scroll,`data-${prefix}-viewbox-min-x`,fit.screenMinX);
      set(scroll,"data-view-navigation-start-bp",windowStart+fit.screenMinX*domainSpan/projectedInnerWidth);
      set(scroll,"data-view-navigation-end-bp",windowStart+(fit.screenMinX+viewportWidth)*domainSpan/projectedInnerWidth);
      scroll.scrollLeft = 0;
      if (ruler) {
        const baseEnd = composition ? Math.max(0,...memberEnds.map(edge => edge.position+edge.motion*deltaPx)) : null;
        const options = { ...rulerOptions, innerWidth:composition ? baseEnd*fit.scale : rulerOptions.innerWidth*fit.scale,
          originX:rulerOptions.originX*fit.scale-fit.screenMinX,viewBoxMinX:0,viewportLeft:0,viewportWidth };
        if (composition) {
          options.windowEnd = baseEnd*domainSpan/innerWidth;
          options.domainSpanBp = Math.max(1,options.windowEnd-options.windowStart);
          if (rulerLine) set(rulerLine,"x2",baseEnd);
        }
        options.tickBp = resolveTickBpFromScale({ ...prefs, domainSpanBp:options.domainSpanBp,
          visibleSpanBp:viewportWidth*domainSpan/projectedInnerWidth,baseViewportPx:viewportWidth });
        set(ruler,"transform",`translate(${fit.minX} 0) scale(${1/fit.scale} 1)`);
        const markup = buildVisibleSubviewRulerMarkup(options);
        if (ruler.innerHTML !== markup) ruler.innerHTML = markup;
      }
      return { ...fit, deltaPx };
    },
    restore() {
      if (restored) return;
      restored = true;
      plan.clear();
      for (let index=restore.length-1;index>=0;index--) restore[index]();
      scroll.classList.remove(PREVIEW_CLASS);
    },
  };
}
