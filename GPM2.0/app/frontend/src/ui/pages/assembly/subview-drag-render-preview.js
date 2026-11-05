// A cheap visual cover: copy already-painted canvases and only the sparse
// bars/labels/ruler. Never clone thousands of hit nodes or their source metadata.
let serial = 0;
export function createSubviewRenderCover(scroll) {
  const document = scroll.ownerDocument, cover = document.createElement("div");
  cover.className = "subview-drag-render-preview is-full-range-drag-preview is-subview-track-drag-preview is-subview-band-canvas-drag-preview";
  cover.setAttribute("aria-hidden", "true");
  Object.assign(cover.style, { position: "absolute", inset: "0", zIndex: "3", pointerEvents: "auto", overflow: "hidden" });
  const getStyle = document.defaultView?.getComputedStyle?.bind(document.defaultView);
  for (let parent = scroll; parent; parent = parent.parentElement) {
    const color = getStyle?.(parent)?.backgroundColor;
    if (color && color !== "transparent" && color !== "rgba(0, 0, 0, 0)") { cover.style.backgroundColor = color; break; }
  }
  blockSubviewRenderInput(cover);
  const prefix = `subview-render-cover-${++serial}-`, ids = new Map();
  const copy = node => {
    if (node.nodeType !== 1) return node.cloneNode(false);
    if (node.matches(".track-collinearity-band, .subview-anchor-hit-zone, .subview-anchor-line[stroke='transparent'], [data-subview-anchor-metadata], [data-subview-render-batch]")) return null;
    const clone = node.cloneNode(false);
    for (const attribute of [...clone.attributes]) if (attribute.name.startsWith("data-")) clone.removeAttribute(attribute.name);
    if (clone.id) { ids.set(clone.id, prefix + clone.id); clone.id = prefix + clone.id; }
    if (node.localName === "canvas") {
      clone.width = node.width; clone.height = node.height;
      const context = clone.getContext("2d");
      if (!context) throw new Error("Cannot preserve Local View drag preview");
      context.drawImage(node, 0, 0);
    } else for (const child of node.childNodes) { const next = copy(child); if (next) clone.appendChild(next); }
    return clone;
  };
  for (const layer of scroll.querySelectorAll("[data-subview-band-drag-canvas]")) cover.appendChild(copy(layer));
  const svg = scroll.querySelector("svg.assembly-track-svg");
  if (svg) cover.appendChild(copy(svg));
  for (const node of cover.querySelectorAll("*")) for (const attribute of [...node.attributes]) {
    const value = attribute.value.replace(/url\(#([^)]*)\)/g, (match, id) => ids.has(id) ? `url(#${ids.get(id)})` : match);
    if (value !== attribute.value) node.setAttribute(attribute.name, value);
  }
  return cover;
}

export function blockSubviewRenderInput(node) {
  for (const type of ["pointerdown", "click", "dblclick", "contextmenu", "wheel", "keydown"]) {
    node.addEventListener(type, event => { event.preventDefault(); event.stopPropagation(); }, { capture: true, passive: false });
  }
}
