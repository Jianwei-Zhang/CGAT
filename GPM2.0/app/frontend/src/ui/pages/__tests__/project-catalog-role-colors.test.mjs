import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderProjectCatalog, projectCatalogKey } from "../project-catalog-view.js";

test("catalog badges carry role identity, not an index-dependent dataset color", () => {
  const state = {locale:"zh", session:{workspacePath:"/ws", projectId:1}, importer:{},
    initializer:{existingProjects:[{projectId:1, supportDatasetIds:[2,3,4]}],datasets:[]}};
  state.initializer.projectCatalog = {key:projectCatalogKey(state),data:{
    references:[{objectType:"reference", objectId:1, role:"reference", displayName:"Ref"}],
    datasets:["primary","support","support","support"].map((role,i)=>({objectType:"dataset", objectId:i+1, role, displayName:`ds${i+1}`}))}};
  const output = renderProjectCatalog(state);
  assert.equal((output.match(/data-dataset-role="support"/g) || []).length, 3);
  assert.match(output, /data-dataset-role="primary"/);
  assert.match(output, /data-dataset-role="reference"/);
  const css = readFileSync(new URL("../../../styles/importer.css", import.meta.url), "utf8");
  for (const [role, palette] of [["reference","ref"],["primary","primary"],["support","companion"]]) {
    assert.match(css, new RegExp(`\\.project-dataset-role\\[data-dataset-role="${role}"\\]\\s*\\{[^}]*background: var\\(--ctg-${palette}-fill\\);[^}]*color: var\\(--ctg-${palette}-text\\)`));
  }
});
