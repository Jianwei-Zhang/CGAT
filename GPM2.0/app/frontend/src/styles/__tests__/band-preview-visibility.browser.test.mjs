import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";
import { readStylesheetTree } from "./style-test-support.mjs";

test("band preview keeps one visible rendering layer for both tones with scroll and ancestor owners", async (t) => {
  const browser = process.platform === "win32" && [
    join(process.env.ProgramFiles || "C:\\Program Files", "Google/Chrome/Application/chrome.exe"),
    join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)", "Microsoft/Edge/Application/msedge.exe"),
  ].find((path) => existsSync(path));
  if (!browser) {
    t.skip("Computed-style regression requires installed Windows Chrome or Edge");
    return;
  }
  const directory = mkdtempSync(join(tmpdir(), "gpm-band-style-"));
  const htmlPath = join(directory, "fixture.html");
  const css = readStylesheetTree(new URL("../components.css", import.meta.url));
  // Exercise the real cascade. Matching a CSS rule's text cannot show which
  // rule wins when preview and canvas-ready classes share the same element.
  writeFileSync(htmlPath, `<!doctype html><style>${css}</style>
    <div id="fixture"></div><output id="style-results"></output><script>
    const results = [];
    for (const owner of ['scroll', 'ancestor', 'subview-ancestor']) {
      const subview = owner === 'subview-ancestor';
      document.querySelector('#fixture').innerHTML = '<section><div class="assembly-track-scroll">'
        + '<div data-track-band-canvas-scene-kind="' + (subview ? 'subview-ctg' : 'main-track') + '"></div>'
        + '<svg data-track-band-svg-overlay="1" class="' + (subview ? 'subview-track-svg' : '') + '">'
        + '<polygon class="track-collinearity-band" data-track-band-proxy="1" points="0,0 40,0 40,40 0,40"/>'
        + '<polygon class="track-collinearity-band is-companion" data-track-band-proxy="1" points="50,0 90,0 90,40 50,40"/>'
        + '</svg></div></section>';
      const scroll = document.querySelector('#fixture .assembly-track-scroll');
      const previewHost = owner === 'scroll' ? scroll : scroll.parentElement;
      const previewClass = subview ? 'is-subview-track-drag-preview' : 'is-track-drag-preview';
      for (const ready of [false, true]) {
        scroll.classList.toggle('is-track-band-canvas-ready', ready);
        for (const phase of ['idle', 'drag', 'released', 'drag', 'cancelled']) {
          const preview = phase === 'drag';
          previewHost.classList.toggle(previewClass, preview);
          const canvas = scroll.querySelector('[data-track-band-canvas-scene-kind]');
          results.push({ owner, ready, preview, phase,
            canvasVisible: ready && getComputedStyle(canvas).visibility !== 'hidden',
            bands: [...scroll.querySelectorAll('polygon')].map(band => {
              const style = getComputedStyle(band);
              return { fill: style.fill, stroke: style.stroke };
            }) });
        }
      }
    }
    document.querySelector('#style-results').textContent = JSON.stringify(results);
    </script>`, "utf8");
  let child;
  let socket;
  let send;
  try {
    const profile = join(directory, "profile");
    child = spawn(browser, [
      "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
      `--user-data-dir=${profile}`, "--remote-debugging-port=0", "about:blank",
    ], { stdio: "ignore", windowsHide: true });
    let page;
    for (let attempt = 0; attempt < 100 && !page; attempt += 1) {
      const portFile = join(profile, "DevToolsActivePort");
      if (existsSync(portFile)) {
        const port = Number(readFileSync(portFile, "utf8").split("\n")[0]);
        if (port > 0) {
          const response = await fetch(`http://127.0.0.1:${port}/json`, { signal: AbortSignal.timeout(1000) });
          page = (await response.json()).find((entry) => entry.type === "page");
        }
      }
      if (!page) await delay(50);
    }
    assert.ok(page, "isolated browser must start its debugging endpoint");
    socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    const pending = new Map();
    let sequence = 0;
    socket.onmessage = ({ data }) => {
      const message = JSON.parse(data);
      const waiter = pending.get(message.id);
      if (!waiter) return;
      pending.delete(message.id);
      clearTimeout(waiter.timer);
      if (message.error) waiter.reject(message.error);
      else waiter.resolve(message.result);
    };
    send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Browser command timed out: ${method}`));
      }, 3000);
      pending.set(id, { resolve, reject, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
    await send("Page.navigate", { url: pathToFileURL(htmlPath).href });
    let report;
    for (let attempt = 0; attempt < 100 && !report; attempt += 1) {
      const response = await send("Runtime.evaluate", {
        expression: "document.querySelector('#style-results')?.textContent", returnByValue: true,
      });
      assert.equal(response.exceptionDetails, undefined);
      report = response.result.value;
      if (!report) await delay(25);
    }
    assert.ok(report, "browser must execute the computed-style fixture");
    const results = JSON.parse(report);
    assert.equal(results.length, 30);
    for (const row of results) {
      const svgVisible = row.preview || !row.ready;
      const context = `${row.owner}/${row.ready}/${row.phase}`;
      assert.equal(row.canvasVisible, row.ready && !row.preview, context);
      assert.deepEqual(row.bands, svgVisible ? [
        { fill: "rgba(97, 129, 170, 0.24)", stroke: "rgba(97, 129, 170, 0.38)" },
        { fill: "rgba(154, 126, 78, 0.22)", stroke: "rgba(154, 126, 78, 0.34)" },
      ] : [
        { fill: "rgba(0, 0, 0, 0)", stroke: "rgba(0, 0, 0, 0)" },
        { fill: "rgba(0, 0, 0, 0)", stroke: "rgba(0, 0, 0, 0)" },
      ], context);
    }
  } finally {
    if (send) await send("Browser.close").catch(() => {});
    socket?.close();
    child?.kill();
    await delay(200);
    rmSync(directory, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  }
});
