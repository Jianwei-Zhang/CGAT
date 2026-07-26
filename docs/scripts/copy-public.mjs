import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";

const docsRoot = resolve(process.cwd(), "docs");
const publicDir = resolve(docsRoot, "public");
const configuredOutDir = process.env.CGAT_DOCS_OUT_DIR || ".vitepress/dist";
const outDir = isAbsolute(configuredOutDir)
  ? configuredOutDir
  : resolve(docsRoot, configuredOutDir);

function copyDirectory(sourceDir, targetDir) {
  mkdirSync(targetDir, { recursive: true });

  for (const entry of readdirSync(sourceDir, { withFileTypes: true })) {
    if (entry.name === ".gitkeep") continue;

    const sourcePath = join(sourceDir, entry.name);
    const targetPath = join(targetDir, entry.name);

    if (entry.isDirectory()) {
      copyDirectory(sourcePath, targetPath);
    } else {
      writeFileSync(targetPath, readFileSync(sourcePath));
    }
  }
}

copyDirectory(publicDir, outDir);
