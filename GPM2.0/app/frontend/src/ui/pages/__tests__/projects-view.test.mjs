import test from "node:test";
import assert from "node:assert/strict";
import { renderProjectsBody } from "../projects-view.js";
import { getMessages } from "../../i18n/index.js";

function render({ session = {}, importer = {}, records = [], summaryHtml = "" } = {}) {
  const state = { locale: "en", session, importer, initializer: {} };
  return renderProjectsBody(state, {
    records, summaryHtml, messages: getMessages(state, "importer"), formatTime: () => "2026/09/08",
  });
}

test("empty project page places its only entry actions inside the centered empty state", () => {
  const html = render();
  assert.match(html, /<section class="project-empty"[\s\S]*id="project-import-button"[\s\S]*id="project-open-button"/);
  assert.equal((html.match(/id="project-import-button"/g) || []).length, 1);
  assert.doesNotMatch(html, /class="project-browser|class="project-recents/);
  assert.doesNotMatch(html, /class="project-page-header"/);
});

test("recent projects and current detail share the browser layout without duplicate entry actions", () => {
  const html = render({
    session: { workspacePath: "/rice", projectName: "Rice" },
    records: [{ path: "/rice", projectName: "Rice" }, { path: '/other/"<name>', projectName: "Other" }],
    summaryHtml: '<section class="project-current">Rice detail</section>',
  });
  assert.match(html, /class="project-browser"[\s\S]*class="project-recents"[\s\S]*id="project-import-button"[\s\S]*id="project-open-button"[\s\S]*class="project-recents-header"[\s\S]*class="project-current"/);
  assert.match(html, /data-recent-path="\/rice" aria-current="true"/);
  assert.match(html, /&quot;&lt;name&gt;/);
  assert.match(html, />Project library<span class="project-count">2<\/span>/);
  assert.match(html, /project-recents-header[\s\S]*id="validate-history-button"[\s\S]*project-recent-list/);
  assert.doesNotMatch(html, /data-project-remove|Remove from recent/);
  assert.doesNotMatch(html, /No projects yet|No project open/);
  assert.equal((html.match(/id="project-open-button"/g) || []).length, 1);
});

test("recent-only state is distinct from no projects", () => {
  const html = render({ records: [{ path: "/rice" }] });
  assert.match(html, /project-no-selection/);
  assert.match(html, /No project open/);
  assert.doesNotMatch(html, /No projects yet/);
});

test("active project keeps the sidebar entry actions when its recent record is removed", () => {
  const html = render({ session: { workspacePath: "/rice" }, summaryHtml: "Rice detail" });
  assert.match(html, /class="project-recents"[\s\S]*id="project-import-button"[\s\S]*id="project-open-button"/);
  assert.match(html, /class="project-count">0<\/span>/);
  assert.match(html, /Rice detail/);
  assert.doesNotMatch(html, /No projects yet|project-no-selection|id="validate-history-button"/);
});

test("project actions remain disabled during import and errors retain their text", () => {
  const html = render({ importer: { inFlight: true, projectError: "Permission <denied>" } });
  assert.match(html, /id="project-import-button"[^>]*disabled/);
  assert.match(html, /id="project-open-button"[^>]*disabled/);
  assert.match(html, /role="alert">Permission &lt;denied&gt;/);
});
