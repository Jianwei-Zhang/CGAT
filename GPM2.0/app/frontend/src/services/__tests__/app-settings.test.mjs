import { resolveAppTheme, initializeAppTheme, applyAppTheme } from "../app-settings.js";
import test from "node:test";
import assert from "node:assert/strict";
import { normalizeAppSettings, setAppSettings, getAppSettings, DEFAULT_APP_SETTINGS, getGraphFontSize, estimateGraphTextWidth, APP_SETTINGS_KEY } from "../app-settings.js";

test("invalid or older stored settings migrate to readable defaults", () => {
  assert.equal(DEFAULT_APP_SETTINGS.historyCapacity, 0);
  assert.deepEqual(normalizeAppSettings(null), DEFAULT_APP_SETTINGS);
  assert.deepEqual(normalizeAppSettings({fontSize:999, graphFontSize:-1, historyCapacity:-1}), DEFAULT_APP_SETTINGS);
  assert.equal(normalizeAppSettings({fontSize:14}).historyCapacity, 0);
  assert.equal(normalizeAppSettings({historyCapacity:0}).historyCapacity, 0);
  assert.equal(normalizeAppSettings({historyCapacity:50}).historyCapacity, 50);
  assert.equal(normalizeAppSettings({historyCapacity:123}).historyCapacity, 123);
});

test("graph text follows interface unless explicitly sized, with CJK width accounted for", () => {
  try {
    setAppSettings({fontSize:14}, {persist:false});
    const baseline = estimateGraphTextWidth("contig_012345");
    assert.equal(getGraphFontSize(), 12);
    setAppSettings({fontSize:18}, {persist:false});
    assert.ok(estimateGraphTextWidth("contig_012345") > baseline);
    setAppSettings({fontSize:18,graphFontSize:10}, {persist:false});
    assert.equal(getGraphFontSize(), 10);
    assert.ok(estimateGraphTextWidth("染色体") > estimateGraphTextWidth("chr"));
  } finally { setAppSettings(DEFAULT_APP_SETTINGS, {persist:false}); }
});

test("persistence failure leaves previously applied settings intact", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  let saved;
  try {
    Object.defineProperty(globalThis,"localStorage",{configurable:true,value:{setItem:(key,value)=>{saved={key,value};}}});
    setAppSettings({fontSize:16,historyCapacity:0});
    assert.equal(saved.key, APP_SETTINGS_KEY);
    assert.equal(JSON.parse(saved.value).historyCapacity, 0);
    Object.defineProperty(globalThis,"localStorage",{configurable:true,value:{setItem:()=>{throw Error("quota");}}});
    assert.throws(()=>setAppSettings(DEFAULT_APP_SETTINGS), /quota/);
    assert.equal(getAppSettings().fontSize,16);
  } finally {
    if(original)Object.defineProperty(globalThis,"localStorage",original);else delete globalThis.localStorage;
    setAppSettings(DEFAULT_APP_SETTINGS,{persist:false});
  }
});


test("theme defaults to system and manual light/dark takes precedence over OS", () => {
  assert.equal(normalizeAppSettings({}).theme, "system");
  assert.equal(normalizeAppSettings({theme:"obsolete"}).theme, "system");
  for (const systemDark of [false, true]) {
    assert.equal(resolveAppTheme("system", systemDark), systemDark ? "dark" : "light");
    assert.equal(resolveAppTheme("dark", systemDark), "dark");
    assert.equal(resolveAppTheme("light", systemDark), "light");
  }
});

test("system theme changes live while manual selection stays fixed, and listener is disposable", () => {
  const root = {dataset:{}};
  const listeners = new Set();
  const media = {matches:true, addEventListener:(name, listener)=>listeners.add(listener),
    removeEventListener:(name, listener)=>listeners.delete(listener)};
  try {
    setAppSettings({theme:"system"}, {persist:false});
    const dispose = initializeAppTheme({root, matchMedia:()=>media});
    assert.equal(root.dataset.theme, "dark");
    media.matches = false;
    listeners.forEach(listener=>listener());
    assert.equal(root.dataset.theme, "light");
    setAppSettings({theme:"dark"}, {persist:false});
    listeners.forEach(listener=>listener());
    assert.equal(root.dataset.theme, "dark");
    setAppSettings({theme:"light"}, {persist:false});
    media.matches = true;
    listeners.forEach(listener=>listener());
    assert.equal(root.dataset.theme, "light");
    setAppSettings({theme:"system"}, {persist:false});
    assert.equal(applyAppTheme(root, true), "dark");
    dispose();
    assert.equal(listeners.size, 0);
  } finally { setAppSettings(DEFAULT_APP_SETTINGS,{persist:false}); }
});
