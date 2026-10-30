import test from "node:test";
import assert from "node:assert/strict";
import { tooltipFixture } from "../../../__tests__/tooltip-fixture.mjs";
import { bindAlignmentTooltips } from "../alignment-tooltip-runtime.js";
import { __testCreateSubviewBandTooltipCoordinator } from "../../assembly-page.js";

test("alignment adapter is synchronous and delegates to the single App owner", () => {
  const h = tooltipFixture();
  bindAlignmentTooltips(h.host, { createCoordinator() { throw new Error("No delayed coordinator allowed"); } });
  const band = h.create("polygon", { "data-subview-band-tooltip": "ctgA | Ref: 2–101 · <safe>" }, {}, true);
  h.fire("pointerover", band);
  assert.equal(h.panel.textContent, "ctgA\nRef: 2–101\n<safe>");
  assert.equal(h.panel.getAttribute("aria-hidden"), "false");
  bindAlignmentTooltips(h.host); assert.equal(h.events.get("pointerover").length, 1);
});

test("legacy coordinator has no timer and immediate enter/leave semantics", () => {
  const calls = [];
  const owner = __testCreateSubviewBandTooltipCoordinator({
    setTimeoutFn() { throw new Error("No wait"); }, onShow: c => calls.push(c.text), onHide: () => calls.push("hide"),
  });
  const token = {}; owner.enter({ token, text: "now" }); assert.deepEqual(calls, ["now"]);
  owner.leave(token); assert.deepEqual(calls, ["now", "hide"]);
});
