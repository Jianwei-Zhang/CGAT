import test from "node:test";
import assert from "node:assert/strict";
import { getNativeSubviewHandle, destroyNativeSubviewPeer } from "../subview-native-identity.js";

const id = "local-123", token = "0123456789abcdef";
function peer(label, destroy) {
  return { __TAURI__: { window: { getCurrentWindow: () => ({ label, destroy }) } } };
}

test("native popup accepts only its own generation-specific window identity", () => {
  const label = `local-view-${id}--${token}`;
  assert.equal(getNativeSubviewHandle(peer(label), id, token).label, label);
  for (const invalid of ["main", "local-view-local-other--0123456789abcdef", `local-view-${id}--old-token`])
    assert.throws(() => getNativeSubviewHandle(peer(invalid), id, token), /identity mismatch/);
  assert.throws(() => getNativeSubviewHandle({}, id, token), /identity mismatch/);
});

test("failed popup cleanup never destroys Main or a different popup", async () => {
  let destroyed = 0;
  for (const label of ["main", `local-view-${id}--old-token`])
    assert.equal(await destroyNativeSubviewPeer(peer(label, () => destroyed++), id, token), false);
  assert.equal(await destroyNativeSubviewPeer({}, id, token), false);
  assert.equal(destroyed, 0);
  assert.equal(await destroyNativeSubviewPeer(peer(`local-view-${id}--${token}`, async () => destroyed++), id, token), true);
  assert.equal(destroyed, 1);
});
