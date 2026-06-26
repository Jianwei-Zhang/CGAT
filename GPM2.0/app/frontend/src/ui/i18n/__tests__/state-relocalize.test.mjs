import test from "node:test";
import assert from "node:assert/strict";

import { relocalizeAppState } from "../state-relocalize.js";
import { t } from "../index.js";

test("relocalizeAppState rewrites restored workspace feedback into the target locale", () => {
  const state = {
    locale: "zh",
    session: {
      workspacePath: "D:/Desktop/GPM/ws1",
      projectId: 2,
      projectName: "p2",
    },
    importer: {
      status: t("zh", "importer.runtime.sessionRestoredStatus"),
      summary: t("zh", "importer.runtime.sessionRestoredSummary"),
      stages: [
        t("zh", "importer.runtime.sessionRestoringStage"),
        t("zh", "importer.runtime.sessionRestoredStage"),
      ],
    },
    initializer: {
      summary: t("zh", "workspace.runtime.restoredProjectSummary", {
        projectName: "p2",
        projectId: 2,
      }),
    },
  };

  const next = relocalizeAppState(state, "en");

  assert.equal(next.locale, "en");
  assert.equal(next.importer.status, "Project Area restored");
  assert.equal(next.importer.summary, "Restored the last project area automatically.");
  assert.deepEqual(next.importer.stages, [
    "Startup: restore project area",
    "Restore succeeded",
  ]);
  assert.equal(next.initializer.summary, "Restored project: p2 (ID 2)");
  assert.equal("settings" in next, false);
});
