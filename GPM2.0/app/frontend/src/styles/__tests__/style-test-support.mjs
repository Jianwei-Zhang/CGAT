import { readFileSync } from "node:fs";

const CSS_IMPORT_PATTERN = /^\s*@import\s+["']([^"']+)["'];\s*$/gm;

export function readStylesheetImports(entryUrl) {
  const source = readFileSync(entryUrl, "utf8");
  return [...source.matchAll(CSS_IMPORT_PATTERN)].map((match) => match[1]);
}

export function readStylesheetTree(entryUrl, visitedOrEncoding = new Set()) {
  const visited = visitedOrEncoding instanceof Set ? visitedOrEncoding : new Set();
  const href = entryUrl.href;
  if (visited.has(href)) {
    throw new Error(`circular stylesheet import: ${href}`);
  }
  visited.add(href);

  const source = readFileSync(entryUrl, "utf8");
  const expanded = source.replace(CSS_IMPORT_PATTERN, (_statement, relativePath) =>
    readStylesheetTree(new URL(relativePath, entryUrl), visited),
  );
  visited.delete(href);
  return expanded;
}
