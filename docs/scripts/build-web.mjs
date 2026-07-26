import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("../..", import.meta.url));
const environment = {
  ...process.env,
  CGAT_DOCS_BASE: "/cgat/",
  CGAT_DOCS_HOSTNAME: "https://riceome.hzau.edu.cn/cgat/",
  CGAT_DOCS_OUT_DIR: "web"
};

function runNode(args) {
  const result = spawnSync(process.execPath, args, {
    cwd: projectRoot,
    env: environment,
    stdio: "inherit"
  });

  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

runNode(["docs/scripts/validate-docs.mjs"]);
runNode(["node_modules/vitepress/bin/vitepress.js", "build", "docs"]);
runNode(["docs/scripts/copy-public.mjs"]);
