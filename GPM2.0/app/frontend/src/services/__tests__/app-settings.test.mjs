import test from "node:test";
import assert from "node:assert/strict";
import { normalizeAppSettings, setAppSettings, getAppSettings, DEFAULT_APP_SETTINGS, getGraphFontSize, estimateGraphTextWidth, APP_SETTINGS_KEY } from "../app-settings.js";

test("invalid or older stored settings migrate to readable defaults", () => {
  assert.deepEqual(normalizeAppSettings(null), DEFAULT_APP_SETTINGS);
  assert.deepEqual(normalizeAppSettings({fontSize:999, graphFontSize:-1, historyCapacity:-1}), DEFAULT_APP_SETTINGS);
  assert.equal(normalizeAppSettings({historyCapacity:0}).historyCapacity, 0);
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
