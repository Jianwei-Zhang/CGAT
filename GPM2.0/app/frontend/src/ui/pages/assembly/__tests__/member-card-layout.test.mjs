import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";

for (const locale of ["zh", "en"]) test(`every member type has exactly two rows and complete immediate details (${locale})`, () => {
  const state = { ...createState({ assembly: { membersCardCollapsed: false, chrCtgs: [
    { assemblyCtgId: 1, name: "MiXeD_normal", totalLength: 10000 },
    { assemblyCtgId: 2, name: "long_fragment[5001-10000].2", totalLength: 5000, sourceFragment: { sourceStart: 5001, sourceEnd: 10000, sourceLength: 10000 } },
  ], hiddenPrimaryCtgIds: [2], deletedCtgs: [{ deletedCtgRecordId: 77, assemblyCtgId: 3, name: "deleted-piece", totalLength: 2500,
    sourceRange: { sourceStart: 2501, sourceEnd: 5000 } }] } }), locale };
  const html = renderAssemblyPage(state), panel = html.match(/<article class="assembly-members-panel[^]*?<\/article>/)[0];
  const cards = [...panel.matchAll(/<button\b[^>]*class="ctg-chip[^]*?<\/button>/g)].map(m => m[0]);
  assert.equal(cards.length, 3);
  for (const card of cards) {
    assert.equal((card.match(/class="ctg-chip-heading"/g) || []).length, 1);
    assert.equal((card.match(/class="ctg-chip-details"/g) || []).length, 1);
    assert.match(card, /data-member-tooltip=/);
    assert.doesNotMatch(card, /\stitle=|ctg-chip-source-range|ctg-chip-local-row/);
  }
  assert.match(cards[0], />MiXeD_normal<\/span>/);
  assert.match(cards[1], /Source 5,001–10,000|源 5,001–10,000/);
  assert.match(cards[1], /10,000 bp/);
  assert.match(cards[2], /2,500 bp/);
});

test("member cards use content-fit flex widths and fixed two-row typography, not half-row or 78px placeholders", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  const card = css.slice(css.indexOf(".assembly-members-panel .ctg-chip {"), css.indexOf(".assembly-members-panel .ctg-chip-heading"));
  assert.match(card, /grid-template-rows: 1\.4em 1\.4em/); assert.match(card, /width: max-content/);
  assert.doesNotMatch(css, /member-chip-row-height|290px|78px/);
  assert.match(css, /ctg-chip-tags > :not\(:first-child\):not\(\.ctg-chip-more-states\)/);
});

for (const locale of ["zh", "en"]) test(`member trigger and panel use generic titles with a compact reset action (${locale})`, () => {
  const name = "ProjectNameThatMustNotAppearInTheMemberTrigger";
  const html = renderAssemblyPage({ ...createState({ session: { projectName: name }, assembly: { membersCardCollapsed: false } }), locale });
  const panel = html.match(/<article class="assembly-members-panel[^]*?<\/article>/)[0];
  const title = locale === "zh" ? "主数据集成员" : "Primary Dataset Members";
  const reset = locale === "zh" ? "重置" : "Reset";
  const full = locale === "zh" ? "重置：撤销删除、撤销隐藏" : "Reset: restore deletions and hidden contigs";
  assert.ok(!panel.includes(name));
  assert.match(panel, new RegExp(`<strong>${title}<\\/strong>`));
  assert.ok(panel.includes(`aria-labelledby="assembly-members-popover-title"`));
  const tools = panel.match(/<div class="assembly-members-popover-tools">[^]*?<\/div>/)[0];
  assert.ok(tools.includes(`<strong id="assembly-members-popover-title">${title}</strong>`));
  assert.ok(tools.includes(`aria-label="${full}" data-app-tooltip="${full}">↺ ${reset}</button>`));
  assert.ok(tools.indexOf("<strong") < tools.indexOf("data-reset-members-state"));
});

test("member panel heading and compact reset share the leading edge like deleted-member headings", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.assembly-members-popover-tools\s*\{[^}]*align-items: center;[^}]*justify-content: flex-start;[^}]*gap: 6px;[^}]*flex-wrap: wrap;/);
});
