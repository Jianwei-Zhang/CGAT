// Windows Node 22+, no npm dependencies. Attach only to an isolated QA WebView2.
// Usage: node four_dataset_native_smoke.mjs <port> <bundle.zip> <new-workspace> <evidence-dir>
// The app must have its own WEBVIEW2_USER_DATA_FOLDER and debug port.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const [port, bundle, workspace, output] = process.argv.slice(2);
assert.ok(/^\d+$/.test(port || "") && bundle && workspace && output, "Expected port, ZIP, new workspace and evidence directory");
assert.ok(existsSync(bundle), "ZIP must exist");
assert.ok(!existsSync(workspace), "Refusing to reuse an existing workspace");
assert.notEqual(resolve(workspace), resolve(output));
mkdirSync(output, { recursive: true });
const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = pages.find(item => item.type === "page" && item.url.startsWith("http://127.0.0.1:"));
assert.ok(page?.webSocketDebuggerUrl, "No native app page on the QA debug port");
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let serial = 0;
const pending = new Map();
const exceptions = [];
socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const item = pending.get(message.id);
    if (item) { pending.delete(message.id); clearTimeout(item.timer); message.error ? item.reject(message.error) : item.resolve(message.result); }
  } else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails);
});
function cdp(method, params = {}) {
  const id = ++serial;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 120000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function waitFor(expression, label) {
  for (let attempt = 0; attempt < 600; attempt++) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out: ${label}; page: ${await evaluate("document.body.innerText")}`);
}
async function click(selector) {
  await waitFor(`Boolean(document.querySelector(${JSON.stringify(selector)}))`, selector);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
}
async function fill(selector, value) {
  await evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)}); if(!element)throw Error("Missing input"); element.value=${JSON.stringify(value)}; element.dispatchEvent(new Event("input",{bubbles:true}));})()`);
}
async function screenshot(name) {
  const shot = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(output, name + ".png"), Buffer.from(shot.data, "base64"));
}
const report = { bundle, workspace, nativePage: page.url, started: new Date().toISOString(), supportSelections: [] };
try {
  await cdp("Runtime.enable"); await cdp("Page.enable");
  await waitFor("Boolean(document.querySelector('#project-import-button'))", "initial project page");
  assert.equal(await evaluate("typeof window.__TAURI__?.core?.invoke"), "function", "Must use native Tauri, not a browser mock");
  assert.equal(await evaluate("localStorage.getItem('gpm_next:last_workspace')"), null, "Must use an empty isolated app profile");
  await click("#project-import-button");
  await fill("#zip-path-input", bundle);
  await fill("#zip-workspace-root-input", workspace);
  await fill("#import-project-name", "QA four datasets");
  await click("#import-zip-start-button");
  await waitFor("document.querySelectorAll('#project-data-catalog [data-dataset-role=\"support\"]').length === 3", "native import and catalog");
  report.catalog = await evaluate(`([...document.querySelectorAll('#project-data-catalog tbody tr')].map(row=>({role:row.querySelector('[data-dataset-role]')?.dataset.datasetRole,name:row.querySelector('.project-dataset-name')?.textContent})))`);
  assert.deepEqual(report.catalog.filter(row => row.role === "support").map(row => row.name), ["support", "support2", "support3"]);
  assert.deepEqual(report.catalog.filter(row => row.role === "primary").map(row => row.name), ["primary"]);
  report.initializer = await evaluate(`window.__TAURI__.core.invoke('list_project_initializer_options',{workspaceRoot:${JSON.stringify(workspace)}})`);
  assert.equal(report.initializer.datasets.length, 4);
  assert.equal(report.initializer.existingProjects.length, 1);
  const project = report.initializer.existingProjects[0];
  assert.equal(project.supportDatasetIds.length, 3);
  assert.ok(!project.supportDatasetIds.includes(project.primaryDatasetId));
  await screenshot("catalog");
  await click('[data-route="assembly"]');
  await waitFor("document.querySelectorAll('#assembly-support-dataset-id option').length === 3", "Assembly support options");
  report.supportOptions = await evaluate(`([...document.querySelectorAll('#assembly-support-dataset-id option')].map(option=>({id:Number(option.value),name:option.textContent.trim()})))`);
  assert.deepEqual(report.supportOptions.map(item => item.name), ["support", "support2", "support3"]);
  assert.deepEqual(report.supportOptions.map(item => item.id), project.supportDatasetIds);
  for (const option of report.supportOptions) {
    await evaluate(`(()=>{const select=document.querySelector('#assembly-support-dataset-id');select.value=${JSON.stringify(String(option.id))};select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await waitFor(`document.querySelector('#assembly-support-dataset-id')?.value === ${JSON.stringify(String(option.id))} && !document.querySelector('#assembly-support-dataset-id')?.disabled`, `switch ${option.name}`);
    await new Promise(resolve => setTimeout(resolve, 500));
    report.supportSelections.push(await evaluate(`({selected:Number(document.querySelector('#assembly-support-dataset-id').value),options:[...document.querySelectorAll('#assembly-support-dataset-id option')].map(option=>Number(option.value)),errors:[...document.querySelectorAll('.error-text')].filter(e=>e.textContent.trim()&&e.getClientRects().length).map(e=>e.textContent.trim())})`));
    assert.equal(report.supportSelections.at(-1).selected, option.id);
    assert.equal(report.supportSelections.at(-1).options.length, 3);
    assert.deepEqual(report.supportSelections.at(-1).errors, []);
    await screenshot(option.name);
  }
  await cdp("Page.reload");
  await waitFor("Boolean(document.querySelector('#project-import-button:not(:disabled)'))", "restored session");
  await waitFor("document.querySelectorAll('#project-data-catalog [data-dataset-role=\"support\"]').length === 3", "catalog after reload");
  await click('[data-route="assembly"]');
  await waitFor("document.querySelectorAll('#assembly-support-dataset-id option').length === 3", "supports after reload");
  report.reloadSupportOptions = await evaluate("[...document.querySelectorAll('#assembly-support-dataset-id option')].map(option=>option.textContent.trim())");
  assert.deepEqual(report.reloadSupportOptions, ["support", "support2", "support3"]);
  assert.deepEqual(exceptions, []);
  report.exceptions = exceptions;
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.error = String(error.stack || error);
  report.exceptions = exceptions;
  try { report.pageText = await evaluate("document.body.innerText"); await screenshot("failure"); } catch {}
  throw error;
} finally {
  writeFileSync(join(output, "native-report.json"), JSON.stringify(report, null, 2) + "\n");
  socket.close();
}
console.log(JSON.stringify(report, null, 2));
