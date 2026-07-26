import { cpSync, mkdirSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";

const docsRoot = resolve(process.cwd(), "docs");
const publicDir = resolve(docsRoot, "public");
const configuredOutDir = process.env.CGAT_DOCS_OUT_DIR || ".vitepress/dist";
const outDir = isAbsolute(configuredOutDir)
  ? configuredOutDir
  : resolve(docsRoot, configuredOutDir);

mkdirSync(outDir, { recursive: true });
cpSync(publicDir, outDir, { recursive: true, force: true });
