import test from "node:test";
import assert from "node:assert/strict";

import { __testCreateDeferredRerenderCoordinator } from "../../assembly-page.js";

test("deferred rerender coordinator schedules one rerender for the next animation frame", () => {
  const scheduled = [];
  const rerenderCalls = [];
  const coordinator = __testCreateDeferredRerenderCoordinator({
    requestAnimationFrame(callback) {
      scheduled.push(callback);
      return scheduled.length;
    },
    cancelAnimationFrame() {},
    rerender(host, store) {
      rerenderCalls.push([host, store]);
    },
  });

  const host = { id: "route-host" };
  const store = { id: "store" };
  coordinator.schedule(host, store);
  coordinator.schedule(host, store);

  assert.equal(rerenderCalls.length, 0);
  assert.equal(scheduled.length, 1);

  scheduled.shift()?.(Date.now());

  assert.deepEqual(rerenderCalls, [[host, store]]);
});

test("deferred rerender coordinator can schedule a subview panel-only rerender", () => {
  const scheduled = [];
  const rerenderCalls = [];
  const subviewPanelCalls = [];
  const coordinator = __testCreateDeferredRerenderCoordinator({
    requestAnimationFrame(callback) {
      scheduled.push(callback);
      return scheduled.length;
    },
    cancelAnimationFrame() {},
    rerender(host, store) {
      rerenderCalls.push([host, store]);
    },
    rerenderSubviewPanel(host, store) {
      subviewPanelCalls.push([host, store]);
    },
  });

  const host = { id: "route-host" };
  const store = { id: "store" };
  coordinator.scheduleSubviewPanel(host, store);
  coordinator.scheduleSubviewPanel(host, store);

  assert.equal(rerenderCalls.length, 0);
  assert.equal(subviewPanelCalls.length, 0);
  assert.equal(scheduled.length, 1);

  scheduled.shift()?.(Date.now());

  assert.deepEqual(rerenderCalls, []);
  assert.deepEqual(subviewPanelCalls, [[host, store]]);
});

test("deferred full rerender takes precedence over a pending subview panel rerender", () => {
  const scheduled = [];
  const rerenderCalls = [];
  const subviewPanelCalls = [];
  const coordinator = __testCreateDeferredRerenderCoordinator({
    requestAnimationFrame(callback) {
      scheduled.push(callback);
      return scheduled.length;
    },
    cancelAnimationFrame() {},
    rerender(host, store) {
      rerenderCalls.push([host, store]);
    },
    rerenderSubviewPanel(host, store) {
      subviewPanelCalls.push([host, store]);
    },
  });

  const host = { id: "route-host" };
  const store = { id: "store" };
  coordinator.scheduleSubviewPanel(host, store);
  coordinator.schedule(host, store);

  scheduled.shift()?.(Date.now());

  assert.deepEqual(rerenderCalls, [[host, store]]);
  assert.deepEqual(subviewPanelCalls, []);
});

test("deferred rerender coordinator cancels a pending frame", () => {
  const scheduled = [];
  const cancelled = [];
  const rerenderCalls = [];
  const coordinator = __testCreateDeferredRerenderCoordinator({
    requestAnimationFrame(callback) {
      scheduled.push(callback);
      return scheduled.length;
    },
    cancelAnimationFrame(token) {
      cancelled.push(token);
    },
    rerender(host, store) {
      rerenderCalls.push([host, store]);
    },
  });

  const host = { id: "route-host" };
  const store = { id: "store" };
  coordinator.schedule(host, store);
  coordinator.cancel();

  assert.deepEqual(cancelled, [1]);
  assert.equal(rerenderCalls.length, 0);
});
