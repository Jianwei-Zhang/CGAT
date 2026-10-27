// Apply only presentation differences caused by locale. The two detached
// snapshots share exactly the same application data. Unchanged attributes and
// subtrees are never written back: open menus, typed values, SVG overlays,
// scroll positions, selection and the actual focused node stay owned by runtime.
const localizedAttribute = name => ["title", "aria-label", "aria-description", "placeholder", "alt", "label"].includes(name)
  || /^data-(?:member|final-path|alignment)-tooltip$/.test(name);

function sameKind(a, b) { return a?.nodeType === b?.nodeType && a?.nodeName === b?.nodeName; }
function stableIdentity(node, peer) {
  if (node.nodeType !== 1) return [];
  return Array.from(node.attributes).filter(attr => (attr.name === "id" || attr.name.startsWith("data-"))
    && !localizedAttribute(attr.name) && peer.getAttribute(attr.name) === attr.value);
}
function findLiveChild(live, before, after, used) {
  const candidates = Array.from(live.childNodes).filter(node => !used.has(node) && sameKind(node, before));
  if (before.nodeType === 3) return candidates.find(node => node.nodeValue === before.nodeValue);
  const identity = stableIdentity(before, after);
  const matches = node => identity.every(attr => node.getAttribute(attr.name) === attr.value);
  if (identity.length) {
    const exact = candidates.find(matches);
    if (exact) return exact;
    // Shell select enhancement wraps the original select without changing its ID.
    if (before.id) return Array.from(live.querySelectorAll?.("[id]") || []).find(node => node.id === before.id && sameKind(node, before));
    return null;
  }
  const classes = Array.from(before.classList || []).filter(name => after.classList?.contains(name));
  const direct = candidates.find(node => classes.every(name => node.classList?.contains(name)));
  if (direct) return direct;
  // View navigation wraps the authored plot layout after its first binding.
  // It is a transparent runtime owner, not a reason to reconstruct the chart.
  if (classes.includes("assembly-track-layout")) {
    return Array.from(live.querySelectorAll?.("[data-view-navigation-card] > .assembly-track-layout") || [])
      .find(node => sameKind(node, before) && classes.every(name => node.classList?.contains(name))) || null;
  }
  return null;
}

export function patchLocalePresentation(live, before, after) {
  const result = { text: 0, attributes: 0, unmatched: 0 };
  const walk = (current, oldNode, nextNode) => {
    if (oldNode.isEqualNode(nextNode)) return;
    if (!sameKind(oldNode, nextNode)) { result.unmatched++; return; }
    if (oldNode.nodeType === 3) {
      if (current.nodeValue === oldNode.nodeValue) { current.nodeValue = nextNode.nodeValue; result.text++; }
      return;
    }
    if (oldNode.nodeType === 1) for (const attr of Array.from(nextNode.attributes)) {
      if (!localizedAttribute(attr.name) || oldNode.getAttribute(attr.name) === attr.value) continue;
      current.setAttribute(attr.name, attr.value); result.attributes++;
    }
    const oldChildren = Array.from(oldNode.childNodes), nextChildren = Array.from(nextNode.childNodes);
    if (oldChildren.length !== nextChildren.length) { result.unmatched++; return; }
    const used = new Set();
    for (let index = 0; index < oldChildren.length; index++) {
      const oldChild = oldChildren[index], nextChild = nextChildren[index];
      const changed = !oldChild.isEqualNode(nextChild);
      const child = findLiveChild(current, oldChild, nextChild, used);
      if (!child) { if (changed) result.unmatched++; continue; }
      used.add(child);
      if (changed) walk(child, oldChild, nextChild);
    }
  };
  walk(live, before, after);
  return result;
}

export function patchLocaleMarkup(live, beforeHtml, afterHtml) {
  const doc = live.ownerDocument;
  const before = doc.createElement("template"), after = doc.createElement("template");
  before.innerHTML = beforeHtml; after.innerHTML = afterHtml;
  return patchLocalePresentation(live, before.content, after.content);
}
