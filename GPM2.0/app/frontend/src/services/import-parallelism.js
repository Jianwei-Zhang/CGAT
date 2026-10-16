export const MIN_IMPORT_PARSER_WORKERS = 1;
export const MAX_IMPORT_PARSER_WORKERS = 8;

export function recommendedImportParserWorkers(hardwareConcurrency = globalThis.navigator?.hardwareConcurrency) {
  const detected = Number(hardwareConcurrency);
  if (!Number.isFinite(detected) || detected < 1) {
    return 1;
  }
  return Math.min(
    MAX_IMPORT_PARSER_WORKERS,
    Math.max(MIN_IMPORT_PARSER_WORKERS, Math.floor(detected) - 1),
  );
}

export function normalizeImportParserWorkers(value, hardwareConcurrency = globalThis.navigator?.hardwareConcurrency) {
  const parsed = Number(String(value ?? "").trim());
  if (Number.isInteger(parsed) && parsed >= MIN_IMPORT_PARSER_WORKERS && parsed <= MAX_IMPORT_PARSER_WORKERS) {
    return String(parsed);
  }
  return String(recommendedImportParserWorkers(hardwareConcurrency));
}

export function importParserWorkerChoices() {
  return Array.from(
    { length: MAX_IMPORT_PARSER_WORKERS - MIN_IMPORT_PARSER_WORKERS + 1 },
    (_, index) => String(index + MIN_IMPORT_PARSER_WORKERS),
  );
}
