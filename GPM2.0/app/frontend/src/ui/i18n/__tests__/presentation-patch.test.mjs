import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { patchLocalePresentation } from "../presentation-patch.js";

// Small tree fixture exercises the DOM patch protocol, not a second renderer.
function element(tag, attrs = {}, children = []) {
  const node = { nodeType: 1, nodeName: tag, childNodes: children, attrs: { ...attrs },
    get attributes() { return Object.entries(this.attrs).map(([name, value]) => ({ name, value })); },
    get id() { return this.attrs.id || ""; },
    get classList() { const values = (this.attrs.class || "").split(/\s+/).filter(Boolean); return Object.assign(values, { contains: key => values.includes(key) }); },
    getAttribute(key) { return this.attrs[key] ?? null; }, setAttribute(key, value) { this.attrs[key] = value; },
    querySelectorAll() { return this.childNodes.flatMap(child => child.nodeType === 1 ? [child, ...child.querySelectorAll()] : []); },
    isEqualNode(other) { return same(this, other); } };
  return node;
}
function text(value) { return { nodeType: 3, nodeName: "#text", nodeValue: value, childNodes: [], isEqualNode(other) { return same(this, other); } }; }
function snapshot(node) { return [node.nodeType, node.nodeName, node.nodeValue, node.attrs, node.childNodes.map(snapshot)]; }
function same(a, b) { return JSON.stringify(snapshot(a)) === JSON.stringify(snapshot(b)); }
const field = (label, id = "") => element("label", { class: "field", ...(id ? { id } : {}) }, [element("span", {}, [text(label)]), element("input", { value: "10" })]);

test("unchanged sibling fields are consumed before matching changed identical wrappers", () => {
  const before = element("section", {}, [field("same"), field("长度"), field("一致性")]);
  const after = element("section", {}, [field("same"), field("Length"), field("Identity")]);
  const live = element("section", {}, [field("same"), field("长度"), field("一致性")]);
  const result = patchLocalePresentation(live, before, after);
  assert.equal(result.unmatched, 0);
  assert.deepEqual(live.childNodes.map(n => n.childNodes[0].childNodes[0].nodeValue), ["same", "Length", "Identity"]);
});

test("locale updates only translated text/attributes, preserving live identity, typed input and runtime menu paint", () => {
  const before = element("div", {}, [element("button", { id: "toggle", title: "选项", "aria-expanded": "false", style: "" }, [text("长度")]), field("名称", "name")]);
  const after = element("div", {}, [element("button", { id: "toggle", title: "Options", "aria-expanded": "false", style: "" }, [text("Length")]), field("Name", "name")]);
  const trigger = element("button", { id: "toggle", title: "选项", "aria-expanded": "true", style: "position:fixed" }, [text("长度")]);
  const inputField = field("名称", "name"), input = inputField.childNodes[1]; input.value = "uncommitted";
  const live = element("div", {}, [trigger, inputField]); live.scrollTop = 75;
  const result = patchLocalePresentation(live, before, after);
  assert.deepEqual(result, { text: 2, attributes: 1, unmatched: 0 });
  assert.equal(live.childNodes[0], trigger); assert.equal(inputField.childNodes[1], input);
  assert.equal(input.value, "uncommitted"); assert.equal(live.scrollTop, 75);
  assert.equal(trigger.attrs["aria-expanded"], "true"); assert.equal(trigger.attrs.style, "position:fixed");
  assert.equal(trigger.attrs.title, "Options");
});

test("stable IDs find a shell-enhanced native select through its runtime wrapper", () => {
  const before = element("div", {}, [element("select", { id: "language" }, [element("option", {}, [text("选项")])])]);
  const after = element("div", {}, [element("select", { id: "language" }, [element("option", {}, [text("Option")])])]);
  const native = element("select", { id: "language" }, [element("option", {}, [text("选项")])]);
  const live = element("div", {}, [element("div", { class: "shell-select" }, [native])]);
  assert.equal(patchLocalePresentation(live, before, after).unmatched, 0);
  assert.equal(native.childNodes[0].childNodes[0].nodeValue, "Option");
});

test("locale-only snapshots cannot overwrite unrelated current data or rebuild unsupported structure", () => {
  const before = element("div", {}, [text("名称")]), after = element("div", {}, [element("b", {}, [text("Name")])]);
  const liveText = text("user data"), live = element("div", {}, [liveText]);
  const result = patchLocalePresentation(live, before, after);
  assert.equal(live.childNodes[0], liveText); assert.equal(liveText.nodeValue, "user data"); assert.equal(result.unmatched, 1);
});

test("Assembly language-switch branch patches shell and route instead of replacing/rebinding them", () => {
  const source = readFileSync(new URL("../../../main.js", import.meta.url), "utf8");
  const branch = source.slice(source.indexOf('if (previous.activeRoute === "assembly")'), source.indexOf('root.innerHTML = renderAppShell(storeRef.getState());'));
  assert.match(branch, /patchLocaleMarkup\(root, renderAppShell\(previous\), renderAppShell\(next\)\)/);
  assert.match(branch, /patchLocaleMarkup\(routeHost, renderAssemblyPage\(previous\), renderAssemblyPage\(next\)\)/);
  assert.match(branch, /retagAssemblyDomLocale/); assert.match(branch, /return;/);
  assert.doesNotMatch(branch, /innerHTML|registerRoutes|bindGlobalLanguageSwitch/);
});

test("authored layouts remain reachable through a navigation runtime wrapper", () => {
  const layout = label => element("div", { class: "assembly-track-layout" }, [element("span", {}, [text(label)])]);
  const before = element("section", {}, [layout("一致性")]), after = element("section", {}, [layout("Identity")]);
  const graph = layout("一致性"), wrapper = element("div", { "data-view-navigation-card": "primary" }, [element("div", { "data-view-navigation": "primary" }), graph]);
  const live = element("section", {}, [wrapper]);
  assert.equal(patchLocalePresentation(live, before, after).unmatched, 0);
  assert.equal(graph.childNodes[0].childNodes[0].nodeValue, "Identity");
  assert.equal(live.childNodes[0], wrapper);
});
