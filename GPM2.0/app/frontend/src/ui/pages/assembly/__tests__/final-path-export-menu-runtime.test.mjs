import test from "node:test";
import assert from "node:assert/strict";

import { bindFinalPathExport } from "../final-path-export-runtime.js";

function createStore() {
  return {
    getState() {
      return {
        assembly: {
          selectedChrName: "Chr01",
        },
      };
    },
  };
}

function createMenuFixture() {
  const menuNode = {
    hidden: true,
    classList: {
      contains(name) {
        return name === "is-hidden" ? menuNode.hidden : false;
      },
      toggle(name, force) {
        if (name === "is-hidden") {
          menuNode.hidden = Boolean(force);
        }
      },
    },
  };
  const toggleNode = {
    closest(selector) {
      return selector === "[data-final-path-export]" ? exportRoot : null;
    },
    setAttribute(name, value) {
      this[name] = value;
    },
  };
  const exportRoot = {
    contains(node) {
      return node === toggleNode || node === menuNode;
    },
    querySelector(selector) {
      if (selector === "[data-final-path-export-menu]") {
        return menuNode;
      }
      if (selector === "[data-final-path-export-toggle]") {
        return toggleNode;
      }
      return null;
    },
  };
  const toggleEvent = {
    target: {
      closest(selector) {
        return selector === "[data-final-path-export-toggle]" ? toggleNode : null;
      },
    },
  };
  return {
    exportRoot,
    menuNode,
    toggleEvent,
    toggleNode,
  };
}

function createHost({ parentElement = null, exportRoots = [] } = {}) {
  const listeners = new Map();
  return {
    listeners,
    parentElement,
    addEventListener(type, handler) {
      listeners.set(type, [...(listeners.get(type) || []), handler]);
    },
    querySelectorAll(selector) {
      return selector === "[data-final-path-export]" ? exportRoots : [];
    },
  };
}

async function dispatchHandlers(host, type, event) {
  for (const handler of host.listeners.get(type) || []) {
    await handler(event);
  }
}

test("local Final Path card binding reuses the delegated export owner on its route ancestor", async () => {
  const fixture = createMenuFixture();
  const routeHost = createHost({ exportRoots: [fixture.exportRoot] });
  const refreshedCard = createHost({
    parentElement: routeHost,
    exportRoots: [fixture.exportRoot],
  });
  const store = createStore();

  bindFinalPathExport(routeHost, store);
  bindFinalPathExport(refreshedCard, store);

  await dispatchHandlers(refreshedCard, "click", fixture.toggleEvent);
  await dispatchHandlers(routeHost, "click", fixture.toggleEvent);

  assert.equal(fixture.menuNode.hidden, false);
  assert.equal(fixture.toggleNode["aria-expanded"], "true");
});

test("pointer-down outside the export root closes the menu immediately", async () => {
  const fixture = createMenuFixture();
  const host = createHost({ exportRoots: [fixture.exportRoot] });

  bindFinalPathExport(host, createStore());
  await dispatchHandlers(host, "click", fixture.toggleEvent);
  assert.equal(fixture.menuNode.hidden, false);

  await dispatchHandlers(host, "pointerdown", {
    target: {
      closest() {
        return null;
      },
    },
  });

  assert.equal(fixture.menuNode.hidden, true);
  assert.equal(fixture.toggleNode["aria-expanded"], "false");
});
