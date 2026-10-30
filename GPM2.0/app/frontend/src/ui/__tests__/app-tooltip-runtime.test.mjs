import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { tooltipFixture } from "./tooltip-fixture.mjs";
import { bindAppTooltips, hideAppTooltips, findAppTooltipTarget, tooltipPosition, inTooltipCorridor } from "../app-tooltip-runtime.js";
import { parseTooltipColor, compositeTooltipColor, resolveTooltipColors } from "../tooltip-colors.js";
import { resolveAlignmentBandStyle, resolveDarkAlignmentBandStyle } from "../pages/assembly/alignment-band-style.js";
import { restoreSvgTooltipTitles } from "../tooltip-export.js";
import { renderSettingsContent } from "../shell/app-settings-panel.js";
const hidden = h => h.panel.getAttribute("aria-hidden") === "true";
const target = (h, text = "tip", attribute = "data-app-tooltip") => h.create("button", { [attribute]: text });

// Explicit layout fragments exercise sizing math; they are not browser/native
// rendering evidence. offsetWidth responds to the fitted border-box width.
function measuredTooltip(h, fragments, { cap = 480, naturalWidth = cap, scrollbar = 0 } = {}) {
  const measurements = [];
  Object.assign(h.panel.computed, { paddingRight: "8px", borderLeftWidth: "1px", borderRightWidth: "1px" });
  const actualWidth = () => Math.min(cap, parseFloat(h.panel.style.width) || naturalWidth);
  Object.defineProperty(h.panel, "offsetWidth", { get: () => Math.round(actualWidth()) });
  Object.defineProperty(h.panel, "clientWidth", { get: () => Math.round(actualWidth() - 2 - scrollbar) });
  h.panel.getBoundingClientRect = () => {
    const left = parseFloat(h.panel.style.left) || 20, top = parseFloat(h.panel.style.top) || 20;
    return { left, top, right: left + actualWidth(), bottom: top + h.panel.offsetHeight, width: actualWidth(), height: h.panel.offsetHeight };
  };
  h.doc.createRange = () => ({
    selectNodeContents(node) { assert.equal(node, h.panel); },
    getClientRects() {
      measurements.push(h.panel.style.width);
      const { left } = h.panel.getBoundingClientRect();
      return fragments.map(fragment => {
        const { width, offset = 0, height = 19 } = typeof fragment === "number" ? { width: fragment } : fragment;
        return { left: left + 9 + offset, right: left + 9 + offset + width, width, height };
      });
    },
  });
  return { measurements, setFragments(value) { fragments = value; } };
}

test("wrapped project paths fit the longest rendered line without altering the full path", () => {
  const h = tooltipFixture(); measuredTooltip(h, [360, 185]);
  const path = String.raw`D:\Desktop\cgat-data\GPM_40550763_full-self-m200-n100_20261022_164241`;
  h.fire("pointerover", target(h, path));
  assert.equal(h.panel.style.width, "379px");
  assert.equal(h.panel.textContent, path);
  assert.equal(hidden(h), false);
});

test("fitting uses the farthest inline fragment, including its offset within a line", () => {
  const h = tooltipFixture();
  measuredTooltip(h, [{ width: 140 }, { width: 130, offset: 140 }, { width: 150 }, { width: 0, offset: 450 }]);
  h.fire("pointerover", target(h, "heading\nfull detail"));
  assert.equal(h.panel.style.width, "289px");
  assert.equal(h.panel.textContent, "heading\nfull detail");
  assert.equal(h.panel.children.length, 2);
});

test("fitted widths retain scrollbar space and fractional glyph safety without exceeding the original cap", () => {
  for (const [cap, scrollbar, fragment, expected] of [
    [480, 15, 360, "394px"], [480, 0, 360.25, "380px"],
    [240, 0, 222, "240px"], [80, 0, 62, "80px"], [84, 0, 60, "79px"],
  ]) {
    const h = tooltipFixture(); measuredTooltip(h, [fragment], { cap, scrollbar });
    h.fire("pointerover", target(h));
    assert.equal(h.panel.style.width, expected);
    assert.ok(parseFloat(h.panel.style.width) <= cap);
  }
});

test("fractional natural ctg widths are never rounded down into a premature heading wrap", () => {
  // Windows Chromium, app-font-size 16 / 18, screenshot-equivalent ctg title.
  for (const naturalWidth of [399.40625, 447.15625]) {
    const h = tooltipFixture(); measuredTooltip(h, [naturalWidth - 18], { naturalWidth });
    h.fire("pointerover", target(h, "NC_089035.1_RagTag[11596222-15049775]@chr01\nStart: 11596221 bp\nLength: 343554 bp"));
    assert.equal(parseFloat(h.panel.style.width), Math.ceil(naturalWidth));
    assert.ok(h.panel.getBoundingClientRect().width >= naturalWidth);
  }
});

test("bp remains in the same atomic display span as its value without changing the copied text", () => {
  const h = tooltipFixture(), text = "ctg\nStart: 11,596,221 bp\nLength: 343554 bp";
  h.fire("pointerover", target(h, text));
  assert.equal(h.panel.textContent, text);
  assert.deepEqual(h.panel.querySelectorAll(".app-tooltip-measure").map(node => node.textContent), ["11,596,221 bp", "343554 bp"]);
  const css = readFileSync(new URL("../../styles/tooltips.css", import.meta.url), "utf8");
  assert.match(css, /\.app-tooltip-measure\s*\{[^}]*display:\s*inline-block;[^}]*white-space:\s*pre;[^}]*overflow-wrap:\s*normal;/);
});

test("unit spans refresh for single-line text and keep HTML-looking payloads literal", () => {
  const h = tooltipFixture(), node = target(h, "<safe> 12.5 bp");
  h.fire("pointerover", node);
  assert.equal(h.panel.textContent, "<safe> 12.5 bp");
  assert.equal(h.panel.querySelectorAll(".app-tooltip-measure")[0]?.textContent, "12.5 bp");
  node.setAttribute("data-app-tooltip", "other 1bp and bps"); h.owner.refresh();
  assert.equal(h.panel.textContent, "other 1bp and bps");
  assert.deepEqual(h.panel.querySelectorAll(".app-tooltip-measure").map(node => node.textContent), ["1bp"]);
});

test("new objects and payload updates reset fitted width, while same-object movement never measures again", () => {
  const h = tooltipFixture(), layout = measuredTooltip(h, [120]);
  const first = target(h, "short"); h.fire("pointerover", first);
  assert.equal(h.panel.style.width, "139px");
  const left = h.panel.style.left;
  h.fire("pointermove", first, { clientX: 80, clientY: 45 }); h.owner.refresh();
  assert.equal(h.panel.style.left, left); assert.equal(layout.measurements.length, 1);
  layout.setFragments([360, 185]);
  const second = target(h, "long project path"); h.fire("pointerover", second);
  assert.equal(h.panel.style.width, "379px");
  layout.setFragments([200]); second.setAttribute("data-app-tooltip", "完整路径说明"); h.owner.refresh();
  assert.equal(h.panel.style.width, "219px");
  assert.deepEqual(layout.measurements, ["", "", ""]);
  assert.equal(h.panel.textContent, "完整路径说明");
});

test("absent or empty text measurements keep intrinsic sizing and never retain a stale fitted width", () => {
  const h = tooltipFixture(), layout = measuredTooltip(h, [120]);
  h.fire("pointerover", target(h)); assert.equal(h.panel.style.width, "139px");
  layout.setFragments([{ width: 0 }, { width: 400, height: 0 }]);
  h.fire("pointerover", target(h, "empty rectangles")); assert.equal(h.panel.style.width, "");
  delete h.doc.createRange;
  h.fire("pointerover", target(h, "intrinsic fallback")); assert.equal(h.panel.style.width, "");
});

test("pointer and keyboard edge placement use the compact width on the first synchronous display", () => {
  for (const keyboard of [false, true]) {
    const h = tooltipFixture(); measuredTooltip(h, [120]);
    const node = target(h); node.box = { left: 860, top: 20, bottom: 50, right: 890 };
    h.fire(keyboard ? "focusin" : "pointerover", node, { clientX: 890, clientY: 30 });
    assert.equal(h.panel.style.width, "139px");
    assert.equal(h.panel.style.left, keyboard ? "753px" : "737px");
    assert.equal(h.panel.style.top, keyboard ? "56px" : "44px");
  }
});

test("all four authored payload types display synchronously under one delegated owner", () => {
  const h = tooltipFixture();
  for (const attribute of ["data-app-tooltip", "data-final-path-tooltip", "data-member-tooltip", "data-subview-band-tooltip"]) {
    const node = target(h, "<safe>\nLength: 42 bp", attribute);
    h.fire("pointerover", node);
    assert.equal(hidden(h), false); assert.equal(h.panel.textContent, "<safe>\nLength: 42 bp");
    assert.equal(node.getAttribute("aria-describedby"), h.panel.id);
    assert.equal(bindAppTooltips(h.host), h.owner);
    assert.equal(h.events.get("pointerover").length, 1);
  }
  assert.equal(h.doc.body.querySelectorAll(".app-tooltip").length, 1);
});

test("placement is stable across pointer/label movement and repositions only for a new object", () => {
  const h = tooltipFixture(), node = target(h), label = h.create("span"); node.append(label);
  h.fire("pointerover", label, { clientX: 30, clientY: 40 });
  assert.equal(h.panel.style.left, "44px"); assert.equal(h.panel.style.top, "54px");
  h.fire("pointermove", node, { clientX: 80, clientY: 42 });
  assert.equal(h.panel.style.left, "44px");
  h.fire("pointerout", node, { relatedTarget: label }); assert.equal(hidden(h), false);
  h.fire("pointerover", target(h, "next"), { clientX: 100, clientY: 100 });
  assert.equal(h.panel.style.left, "114px");
});

test("viewport placement flips before the pointer, clamps to 8px and never changes content", () => {
  assert.deepEqual(tooltipPosition({ x: 899, y: 599, width: 240, height: 100, viewportWidth: 900, viewportHeight: 600 }), { left: 645, top: 485 });
  assert.deepEqual(tooltipPosition({ x: 1, y: 1, width: 480, height: 100, viewportWidth: 400, viewportHeight: 150 }), { left: 8, top: 15 });
});

test("pointer crosses the gap, then selects and scrolls tooltip content without hiding it", () => {
  const h = tooltipFixture(), node = target(h);
  h.fire("pointerover", node, { clientX: 30, clientY: 30 });
  h.fire("pointerout", node, { relatedTarget: h.doc.body, clientX: 32, clientY: 32 });
  h.fire("pointermove", h.doc.body, { clientX: 39, clientY: 39 }); assert.equal(hidden(h), false);
  h.fire("pointerover", h.panel, { clientX: 50, clientY: 50 });
  h.fire("pointerdown", h.panel, { buttons: 1 });
  h.fire("pointermove", h.panel, { buttons: 1 });
  h.fire("scroll", h.panel); assert.equal(hidden(h), false);
  h.fire("pointerout", h.panel, { relatedTarget: h.doc.body, clientX: 400, clientY: 300 });
  assert.equal(hidden(h), true);
});

test("corridors are geometric and cannot hold an unrelated distant position open", () => {
  const r = { left: 44, top: 44, right: 284, bottom: 144 }, a = { x: 30, y: 30 };
  assert.equal(inTooltipCorridor({ x: 39, y: 39 }, a, r), true);
  assert.equal(inTooltipCorridor({ x: 5, y: 500 }, a, r), false);
  assert.equal(inTooltipCorridor({ x: 800, y: 30 }, { x: 30, y: 30 }, { left: 44, top: 20, right: 284, bottom: 120 }), false);
});

test("keyboard focus is immediate, preserves existing descriptions and Escape does not immediately reopen", () => {
  const h = tooltipFixture(), node = target(h); node.setAttribute("aria-describedby", "existing");
  h.doc.activeElement = node;
  h.fire("focusin", node); assert.equal(hidden(h), false); assert.equal(h.panel.style.top, "56px");
  assert.equal(node.getAttribute("aria-describedby"), `existing ${h.panel.id}`);
  h.fire("keydown", node, { key: "Escape" }); assert.equal(hidden(h), true);
  h.fire("pointermove", node); assert.equal(hidden(h), true);
  assert.equal(h.doc.activeElement, node); assert.equal(node.getAttribute("aria-describedby"), "existing");
  h.fire("focusout", node, { relatedTarget: h.doc.body }); h.fire("focusin", node);
  assert.equal(hidden(h), false);
});

test("disabled buttons keep their explanation without changing disabled state or requiring a click", () => {
  const h = tooltipFixture(), node = target(h, "Open a project first"); node.setAttribute("disabled", "");
  h.fire("pointermove", node); assert.equal(hidden(h), false);
  assert.equal(node.hasAttribute("disabled"), true);
});

test("external actions hide and suppress stale same-object hover, internal scroll is exempt", () => {
  const h = tooltipFixture();
  for (const type of ["scroll", "contextmenu", "pointerdown", "click", "dragstart", "pointercancel"]) {
    const node = target(h);
    h.fire("pointerover", node); h.fire(type, node);
    assert.equal(hidden(h), true, type);
    h.fire("pointermove", node); assert.equal(hidden(h), true, type);
    h.fire("pointerout", node, { relatedTarget: null });
  }
  const node = target(h); h.fire("pointerup", h.doc.body); h.fire("pointerover", node);
  assert.equal(h.windowOptions.get("blur"), false, "child input blur must not be treated as window departure");
  h.windowFire("blur"); assert.equal(hidden(h), true);
});

test("dragging suppresses hover and later genuine entry still works", () => {
  const h = tooltipFixture(), a = target(h, "first"), b = target(h, "second");
  h.fire("pointerover", a); h.fire("pointerdown", a, { buttons: 1 });
  h.fire("pointermove", b, { buttons: 1 }); assert.equal(hidden(h), true);
  h.fire("pointerup", b); h.fire("pointerout", b, { relatedTarget: h.doc.body });
  h.fire("pointerover", a); assert.equal(hidden(h), false);
});

test("single panel portals inside its native dialog and returns to body for page owners", () => {
  const h = tooltipFixture(), page = target(h), dialog = h.create("dialog", { open: "" }), modal = target(h, "modal"); dialog.append(modal);
  h.fire("pointerover", page); h.fire("pointerover", modal);
  assert.equal(h.panel.parentElement, dialog); assert.equal(page.getAttribute("aria-describedby"), null);
  h.fire("pointerover", page); assert.equal(h.panel.parentElement, h.doc.body);
  h.mutate([{ type: "attributes", target: dialog, attributeName: "open" }]); assert.equal(hidden(h), true);
  h.fire("pointerover", modal); dialog.removeAttribute("open");
  h.fire("close", dialog); assert.equal(hidden(h), true);
});

test("removed owners and route/cache hides never resurrect stale panels or duplicate handlers", () => {
  const h = tooltipFixture(), node = target(h); h.host.append(node);
  h.fire("pointerover", node); node.remove(); h.owner.refresh(); assert.equal(hidden(h), true);
  h.host.append(node); h.fire("pointerover", node); hideAppTooltips(h.host); assert.equal(hidden(h), true);
  bindAppTooltips(h.host); assert.equal(h.events.get("pointerover").length, 1);
  h.fire("pointerover", node); h.windowFire("gpm-next:route-refresh"); assert.equal(hidden(h), true);
  h.owner.destroy(); assert.equal(h.events.get("pointerover").length, 0);
});

test("locale/payload updates are safe plain text and do not move an active tooltip", () => {
  const h = tooltipFixture(), node = target(h, "old"); h.fire("pointerover", node);
  const left = h.panel.style.left; node.setAttribute("data-app-tooltip", '<img src=x onerror=alert(1)>');
  h.owner.refresh(); assert.equal(h.panel.textContent, '<img src=x onerror=alert(1)>');
  assert.equal(h.panel.children.length, 0); assert.equal(h.panel.style.left, left);
  h.doc.documentElement.setAttribute("data-theme", "dark");
  h.mutate([{ type: "attributes", target: h.doc.documentElement, attributeName: "data-theme" }]);
  assert.equal(hidden(h), true);
});

test("SVG descriptions resolve to painted ctg objects and preserve accessible identity", () => {
  const h = tooltipFixture(), group = h.create("g", {}, {}, true), ctg = h.create("rect", {}, { fill: "rgb(210, 223, 239)" }, true);
  const desc = h.create("desc", { "data-app-tooltip-source": "" }, {}, true); desc.textContent = "ctg full name";
  const label = h.create("text", {}, {}, true); ctg.append(desc); group.append(ctg, label);
  h.mutate([{ type: "childList", target: group, addedNodes: [group] }]);
  assert.equal(ctg.getAttribute("aria-label"), "ctg full name"); assert.equal(findAppTooltipTarget(label), ctg);
  h.fire("pointerover", ctg); assert.equal(h.panel.style.background, "rgb(210, 223, 239)");
  desc.textContent = "完整 ctg 名称";
  h.mutate([{ type: "characterData", target: { parentElement: desc } }]);
  assert.equal(ctg.getAttribute("aria-label"), "完整 ctg 名称");
});

test("actual ctg fills, reference gray and default light/dark surfaces use one color rule", () => {
  const h = tooltipFixture();
  for (const fill of ["#d2dfef", "#e7dec4", "#cfcfcf", "#234567"]) {
    const ctg = h.create("rect", { "data-app-tooltip": "ctg" }, { fill }, true);
    h.fire("pointerover", ctg);
    assert.equal(h.panel.style.background, `rgb(${parseTooltipColor(fill).slice(0, 3).join(", ")})`);
  }
  h.fire("pointerover", target(h)); assert.equal(h.panel.style.background, "#ffffff");
  h.doc.documentElement.setAttribute("data-theme", "dark");
  h.fire("pointerover", target(h)); assert.equal(h.panel.style.background, "#223044");
});

test("Canvas proxies match the exact per-band identity shade in both themes, not just the role", () => {
  const h = tooltipFixture();
  for (const dark of [false, true]) for (const tone of ["primary", "companion"]) {
    h.doc.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    const backgrounds = [];
    for (const identity of [80, 95, 100, null]) {
      const light = resolveAlignmentBandStyle(tone, identity), shade = resolveDarkAlignmentBandStyle(tone, identity);
      const node = h.create("polygon", { class: "track-collinearity-band", "data-track-band-proxy": "1", "data-subview-band-tooltip": "band" },
        { fill: "rgba(0, 0, 0, 0)", opacity: "0", "--alignment-band-fill": light.fill, "--alignment-band-dark-fill": shade.fill }, true);
      h.fire("pointerover", node); backgrounds.push(h.panel.style.background);
      assert.equal(h.panel.style.background, dark ? shade.fill : light.fill);
    }
    assert.equal(new Set(backgrounds).size, 4);
  }
});

test("transparent LGZ proxies inherit their painted sibling, including composited opacity", () => {
  const h = tooltipFixture(), group = h.create("g", {}, {}, true);
  const paint = h.create("rect", { class: "grt-result-interval" }, { fill: "rgba(47, 158, 68, .72)" }, true);
  const proxy = h.create("rect", { class: "grt-result-hover-proxy", "data-subview-band-tooltip": "LGZ" }, { fill: "transparent" }, true);
  group.append(paint, proxy); h.fire("pointerover", proxy);
  assert.equal(h.panel.style.background, "rgb(105, 185, 120)");
  assert.equal(h.panel.style.color, "rgb(30, 41, 59)");
  paint.computed.fill = "rgb(10, 20, 30)"; h.owner.refresh();
  assert.equal(h.panel.style.background, "rgb(10, 20, 30)"); assert.equal(h.panel.style.color, "rgb(248, 250, 252)");
});

test("evidence opacity composites against plot surface instead of changing tooltip opacity", () => {
  const h = tooltipFixture(), plot = h.create("svg", {}, { backgroundColor: "rgb(100, 100, 100)" }, true);
  const band = h.create("polygon", {}, { fill: "rgba(200, 0, 100, .5)", fillOpacity: ".5" }, true); plot.append(band);
  const colors = resolveTooltipColors(band, { getStyle: h.win.getComputedStyle });
  assert.equal(colors.background, "rgb(125, 75, 100)");
  assert.deepEqual(compositeTooltipColor([200, 0, 0, .5], [100, 100, 100, 1]), [150, 50, 50, 1]);
  assert.deepEqual(parseTooltipColor("color(srgb 1 0.5 0 / 25%)"), [255, 127.5, 0, .25]);
});

test("export clone restores title information while live SVG stays app-owned", () => {
  const h = tooltipFixture(), svg = h.create("svg", {}, {}, true), shape = h.create("rect", {}, {}, true);
  const desc = h.create("desc", { "data-app-tooltip-source": "" }, {}, true); desc.textContent = "full source <name>"; shape.append(desc); svg.append(shape);
  const clone = svg.cloneNode(true); restoreSvgTooltipTitles(clone);
  assert.equal(clone.querySelector("title").textContent, "full source <name>");
  assert.equal(svg.querySelector("title"), null);
  restoreSvgTooltipTitles(clone); assert.equal(clone.querySelectorAll("title").length, 1);
});

test("settings hover uses shared tooltip but click expansion remains a separate shared-style note", () => {
  const html = renderSettingsContent("en");
  assert.match(html, /settings-help-button[^>]*data-app-tooltip=/);
  assert.match(html, /aria-controls="settings-graph-help"/);
  assert.match(html, /role="note" class="settings-tooltip app-tooltip-surface/);
  const h = tooltipFixture(), wrapper = h.create("span", { class: "settings-help is-open" }), button = target(h); wrapper.append(button);
  h.fire("pointerover", button); assert.equal(hidden(h), true);
});

test("surface contract has one geometry, scrollable full text and no delay/animation", () => {
  const css = readFileSync(new URL("../../styles/tooltips.css", import.meta.url), "utf8");
  for (const token of ["min-width: 0", "480px", "padding: 6px 8px", "border-radius: 6px", "line-height: 1.5", "overflow: auto", "user-select: text", "transition: none", "animation: none"]) assert.ok(css.includes(token), token);
  const runtime = readFileSync(new URL("../app-tooltip-runtime.js", import.meta.url), "utf8");
  assert.doesNotMatch(runtime, /setTimeout|setInterval|innerHTML/);
  const patch = readFileSync(new URL("../i18n/presentation-patch.js", import.meta.url), "utf8");
  assert.match(patch, /app\|member\|final-path\|alignment\|subview-band/);
});

test("App has no authored native HTML title or dynamic title assignment; SVG titles are export-only", () => {
  const src = new URL("../../", import.meta.url), files = [];
  const walk = dir => { for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__tests__") continue;
    const url = new URL(entry.name + (entry.isDirectory() ? "/" : ""), dir);
    if (entry.isDirectory()) walk(url); else if (entry.name.endsWith(".js")) files.push(url);
  } }; walk(src);
  const exportSources = new Set(["final-path-card.js", "project-export-page.js", "project-preview-image-export.js"]);
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    assert.doesNotMatch(text, /(?<![\w-])title=["']|\.title\s*=|setAttribute\(["']title["']/, file.pathname);
    if (text.includes("<title>")) assert.ok(exportSources.has(file.pathname.split("/").at(-1)), file.pathname);
  }
});


test("transparent ctg fragment targets use the actual source fill, including selection state", () => {
  const h = tooltipFixture(), group = h.create("g", {}, {}, true);
  const source = h.create("rect", { class: "track-ctg is-companion" }, { fill: "rgb(220, 203, 164)" }, true);
  const nest = h.create("g", {}, {}, true), fragment = h.create("rect", { class: "main-anchor-fragment-hit-zone", "data-app-tooltip": "fragment" }, { fill: "transparent" }, true);
  group.append(source, nest); nest.append(fragment);
  h.fire("pointerover", fragment); assert.equal(h.panel.style.background, "rgb(220, 203, 164)");
  source.computed.fill = "rgb(231, 222, 196)"; h.owner.refresh();
  assert.equal(h.panel.style.background, "rgb(231, 222, 196)");
});

test("line object color comes from its visible stroke rather than the SVG default black fill", () => {
  const h = tooltipFixture(), line = h.create("line", { "data-app-tooltip": "gap" }, { fill: "rgb(0, 0, 0)", stroke: "rgb(100, 116, 139)" }, true);
  h.fire("pointerover", line); assert.equal(h.panel.style.background, "rgb(100, 116, 139)");
});

test("tall panels reserve a full side of the pointer and scroll rather than covering it", () => {
  const h = tooltipFixture(), node = target(h);
  h.fire("pointerover", node, { clientX: 450, clientY: 300 });
  assert.equal(h.panel.style.maxHeight, "278px");
});


test("neutral controls use default palette, while coloured controls and ctg cards keep object paint", () => {
  const h = tooltipFixture(); h.doc.documentElement.computed["--surface-subtle"] = "#f8fafc";
  const plain = target(h); plain.computed.backgroundColor = "rgb(248, 250, 252)";
  h.fire("pointerover", plain); assert.equal(h.panel.style.background, "#ffffff"); assert.equal(h.panel.style.borderColor, "#cbd5e1");
  const card = target(h); card.className = "ctg-chip"; card.computed.backgroundColor = "rgb(248, 250, 252)";
  h.fire("pointerover", card); assert.equal(h.panel.style.background, "rgb(248, 250, 252)");
  const primary = target(h); primary.computed.backgroundColor = "rgb(35, 75, 118)";
  h.fire("pointerover", primary); assert.equal(h.panel.style.background, "rgb(35, 75, 118)");
});

test("departure away from the panel closes immediately instead of redefining a corridor around the exit", () => {
  const h = tooltipFixture(), node = target(h); h.fire("pointerover", node);
  h.fire("pointerout", node, { relatedTarget: h.doc.body, clientX: 10, clientY: 15 });
  assert.equal(hidden(h), true);
});


test("SVG contig detail renders a name heading and one line per field without rewriting source identity", () => {
  const h = tooltipFixture(), shape = h.create("rect", {}, { fill: "#d2dfef" }, true);
  const desc = h.create("desc", { "data-app-tooltip-source": "" }, {}, true);
  desc.textContent = "ctg full | Start: 5 bp | Length: 10 bp"; shape.append(desc);
  h.fire("pointerover", shape);
  assert.equal(h.panel.textContent, "ctg full\nStart: 5 bp\nLength: 10 bp");
  assert.equal(h.panel.children[0].tagName, "strong");
  assert.equal(desc.textContent, "ctg full | Start: 5 bp | Length: 10 bp");
});


test("route/cache cleanup clears a prior Escape suppression without retaining an old DOM owner", () => {
  const h = tooltipFixture(), node = target(h); h.host.append(node);
  h.fire("focusin", node); h.fire("keydown", node, { key: "Escape" });
  hideAppTooltips(h.host); h.fire("focusin", node);
  assert.equal(hidden(h), false);
  h.fire("keydown", node, { key: "Escape" }); node.remove(); h.owner.refresh();
  h.host.append(node); h.fire("focusin", node); assert.equal(hidden(h), false);
});


test("nested targets select the innermost object and SVG sibling labels retain the same owner", () => {
  const h = tooltipFixture(), outer = target(h, "outer"), inner = target(h, "inner"); outer.append(inner);
  h.fire("pointerover", inner); assert.equal(h.panel.textContent, "inner");
  assert.equal(outer.getAttribute("aria-describedby"), null);
  const group = h.create("g", {}, {}, true), shape = h.create("rect", {}, { fill: "#d2dfef" }, true);
  const desc = h.create("desc", { "data-app-tooltip-source": "" }, {}, true); desc.textContent = "ctg";
  const label = h.create("text", {}, {}, true); shape.append(desc); group.append(shape, label);
  h.fire("pointerover", shape);
  h.fire("pointerout", shape, { relatedTarget: label, clientX: 10, clientY: 15 });
  assert.equal(hidden(h), false);
  const left = h.panel.style.left; h.fire("pointerover", label, { clientX: 10, clientY: 15 });
  assert.equal(h.panel.style.left, left);
});


test("LGZ interval shades composite the actual SVG mask and source ctg, not just the page background", () => {
  for (const masked of [false, true]) for (const sourceFill of [[210, 223, 239, 1], [90, 110, 130, 1]]) {
    const h = tooltipFixture(), sourceGroup = h.create("g", {}, {}, true);
    const source = h.create("rect", { class: "track-ctg" }, { fill: `rgb(${sourceFill.slice(0, 3).join(", ")})` }, true);
    const overlay = h.create("g", { class: "grt-result-overlay" }, {}, true);
    const intervalGroup = h.create("g", { class: "grt-result-interval-group" }, {}, true);
    const interval = h.create("rect", { class: "grt-result-interval" }, { fill: "rgba(47, 158, 68, .72)" }, true);
    const proxy = h.create("rect", { class: "grt-result-hover-proxy", "data-subview-band-tooltip": "LGZ" }, { fill: "transparent" }, true);
    sourceGroup.append(source, overlay); overlay.append(intervalGroup); intervalGroup.append(interval, proxy);
    if (masked) {
      const mask = h.create("rect", { class: "grt-result-mask" }, { fill: "rgba(224, 229, 225, .76)" }, true);
      overlay.replaceChildren(mask, intervalGroup);
    }
    const back = masked ? compositeTooltipColor([224, 229, 225, .76], sourceFill) : sourceFill;
    const expected = compositeTooltipColor([47, 158, 68, .72], back);
    h.fire("pointerover", proxy);
    assert.equal(h.panel.style.background, `rgb(${expected.slice(0, 3).map(Math.round).join(", ")})`);
  }
});
