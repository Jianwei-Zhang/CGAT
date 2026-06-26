import { getLocale, t } from "./index.js";

function matchesLocalizedValue(value, candidates) {
  const normalized = String(value || "");
  return candidates.some((candidate) => normalized === String(candidate || ""));
}

function resolveLocalizedVariant(currentValue, state, nextLocale, variants) {
  const matched = variants.find((variant) => matchesLocalizedValue(currentValue, variant.all(state)));
  return matched ? matched.next(state, nextLocale) : currentValue;
}

export function relocalizeAppState(state, nextLocale) {
  const targetLocale = getLocale(nextLocale);
  const nextState = {
    ...state,
    locale: targetLocale,
  };

  const importer = state?.importer || {};
  const initializer = state?.initializer || {};

  return {
    ...nextState,
    importer: {
      ...importer,
      status: resolveLocalizedVariant(importer.status, state, targetLocale, [
        {
          all: () => [
            t("zh", "importer.runtime.sessionRestoringStatus"),
            t("en", "importer.runtime.sessionRestoringStatus"),
          ],
          next: () => t(targetLocale, "importer.runtime.sessionRestoringStatus"),
        },
        {
          all: () => [
            t("zh", "importer.runtime.sessionRestoredStatus"),
            t("en", "importer.runtime.sessionRestoredStatus"),
          ],
          next: () => t(targetLocale, "importer.runtime.sessionRestoredStatus"),
        },
        {
          all: () => [
            t("zh", "importer.runtime.sessionRestoreFailedStatus"),
            t("en", "importer.runtime.sessionRestoreFailedStatus"),
          ],
          next: () => t(targetLocale, "importer.runtime.sessionRestoreFailedStatus"),
        },
      ]),
      summary: resolveLocalizedVariant(importer.summary, state, targetLocale, [
        {
          all: (snapshot) => [
            t("zh", "importer.runtime.sessionRestoringSummary", {
              workspacePath: snapshot?.session?.workspacePath || "",
            }),
            t("en", "importer.runtime.sessionRestoringSummary", {
              workspacePath: snapshot?.session?.workspacePath || "",
            }),
          ],
          next: (snapshot, locale) => t(locale, "importer.runtime.sessionRestoringSummary", {
            workspacePath: snapshot?.session?.workspacePath || "",
          }),
        },
        {
          all: () => [
            t("zh", "importer.runtime.sessionRestoredSummary"),
            t("en", "importer.runtime.sessionRestoredSummary"),
          ],
          next: () => t(targetLocale, "importer.runtime.sessionRestoredSummary"),
        },
        {
          all: () => [
            t("zh", "importer.runtime.sessionRestoreFailedSummary"),
            t("en", "importer.runtime.sessionRestoreFailedSummary"),
          ],
          next: () => t(targetLocale, "importer.runtime.sessionRestoreFailedSummary"),
        },
      ]),
      stages: Array.isArray(importer.stages)
        ? importer.stages.map((stage) => resolveLocalizedVariant(stage, state, targetLocale, [
          {
            all: () => [
              "startup restore workspace",
              t("zh", "importer.runtime.sessionRestoringStage"),
              t("en", "importer.runtime.sessionRestoringStage"),
            ],
            next: () => t(targetLocale, "importer.runtime.sessionRestoringStage"),
          },
          {
            all: () => [
              t("zh", "importer.runtime.sessionRestoredStage"),
              t("en", "importer.runtime.sessionRestoredStage"),
            ],
            next: () => t(targetLocale, "importer.runtime.sessionRestoredStage"),
          },
        ]))
        : importer.stages,
    },
    initializer: {
      ...initializer,
      summary: resolveLocalizedVariant(initializer.summary, state, targetLocale, [
        {
          all: () => [
            t("zh", "workspace.runtime.initializerSummary"),
            t("en", "workspace.runtime.initializerSummary"),
          ],
          next: () => t(targetLocale, "workspace.runtime.initializerSummary"),
        },
        {
          all: (snapshot) => [
            t("zh", "workspace.runtime.restoredProjectSummary", {
              projectName: snapshot?.session?.projectName || "",
              projectId: snapshot?.session?.projectId || "",
            }),
            t("en", "workspace.runtime.restoredProjectSummary", {
              projectName: snapshot?.session?.projectName || "",
              projectId: snapshot?.session?.projectId || "",
            }),
          ],
          next: (snapshot, locale) => t(locale, "workspace.runtime.restoredProjectSummary", {
            projectName: snapshot?.session?.projectName || "",
            projectId: snapshot?.session?.projectId || "",
          }),
        },
        {
          all: () => [
            t("zh", "workspace.runtime.restoredWorkspaceSummary"),
            t("en", "workspace.runtime.restoredWorkspaceSummary"),
          ],
          next: () => t(targetLocale, "workspace.runtime.restoredWorkspaceSummary"),
        },
      ]),
    },
  };
}
