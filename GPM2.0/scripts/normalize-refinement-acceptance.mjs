// Headless fixture adapter for the opt-in Windows desktop command roundtrip.
import { readFileSync } from "node:fs";
import { normalizeGrtProjectView } from "../app/frontend/src/ui/pages/assembly/grt-state.js";
import { canonicalizeFinalPathOverallLengths, normalizeFinalPathByChr } from "../app/frontend/src/ui/pages/assembly/final-path-state.js";

const view = JSON.parse(readFileSync(process.argv[2], "utf8"));
const baseline = normalizeFinalPathByChr(normalizeGrtProjectView(view).baselineFinalPathByChr);
process.stdout.write(JSON.stringify(canonicalizeFinalPathOverallLengths(baseline, baseline)));
