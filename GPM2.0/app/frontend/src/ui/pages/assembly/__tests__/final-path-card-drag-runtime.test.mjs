import test from "node:test";
import assert from "node:assert/strict";

import { bindFinalPathCardDrag } from "../final-path-card-drag-runtime.js";

function createClassList() {
  const names = new Set();
  return {
    add(name) {
      names.add(name);
    },
    remove(name) {
      names.delete(name);
    },
    contains(name) {
      return names.has(name);
    },
  };
}

function createWindowStub() {
  const listeners = new Map();
  return {
    listeners,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    removeEventListener(type, handler) {
      if (listeners.get(type) === handler) {
        listeners.delete(type);
      }
    },
  };
}

function createFormField({
  tagName = "INPUT",
  value = "",
  checked = false,
  selectedIndex = -1,
  options = [],
} = {}) {
  return {
    tagName,
    value,
    checked,
    selectedIndex,
    options,
  };
}

function createStyleDeclaration(initialValues = {}) {
  const values = new Map(Object.entries(initialValues));
  return {
    setProperty(name, value) {
      values.set(name, value);
    },
    getPropertyValue(name) {
      return values.get(name) || "";
    },
  };
}

test("bindFinalPathCardDrag drags only the inner card body and resolves nearest after-placement by crossed top edge", async () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const windowStub = createWindowStub();
  const appendedNodes = [];
  let hitRow = null;
  const ghostNode = {
    style: {},
    classList: createClassList(),
    removed: false,
    remove() {
      this.removed = true;
    },
  };
  const documentStub = {
    body: {
      appendChild(node) {
        appendedNodes.push(node);
      },
    },
    elementFromPoint() {
      return hitRow;
    },
  };
  globalThis.window = windowStub;
  globalThis.document = documentStub;

  try {
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
          },
        };
      },
    };
    const cardList = {
      contains(node) {
        return node === sourceRow || node === middleRow || node === targetRow;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-row-id]") {
          return [sourceRow, middleRow, targetRow];
        }
        return [];
      },
    };
    const sourceCard = {
      getBoundingClientRect() {
        return {
          left: 100,
          top: 200,
          width: 720,
          height: 56,
        };
      },
      cloneNode() {
        return ghostNode;
      },
    };
    const sourceRow = {
      dataset: { finalPathRowId: "seg-1" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return sourceCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
      getBoundingClientRect() {
        return {
          top: 190,
          height: 76,
        };
      },
    };
    const middleCard = {
      getBoundingClientRect() {
        return {
          top: 300,
          bottom: 356,
        };
      },
    };
    const middleRow = {
      dataset: { finalPathRowId: "seg-2" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return middleCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
      getBoundingClientRect() {
        return {
          top: 290,
          height: 76,
        };
      },
    };
    const targetCard = {
      getBoundingClientRect() {
        return {
          top: 390,
          bottom: 446,
        };
      },
    };
    const targetRow = {
      dataset: { finalPathRowId: "seg-3" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return targetCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
      getBoundingClientRect() {
        return {
          top: 380,
          height: 76,
        };
      },
    };
    const handleNode = {
      dataset: { finalPathRowDragId: "seg-1" },
      closest(selector) {
        if (selector === "[data-final-path-row-id]") {
          return sourceRow;
        }
        return null;
      },
    };
    const pointerTarget = {
      closest(selector) {
        if (selector === "[data-final-path-row-drag-id]") {
          return handleNode;
        }
        return null;
      },
    };
    let movePayload = null;
    bindFinalPathCardDrag(host, store, {
      moveFinalPathRow(_host, _store, payload) {
        movePayload = payload;
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 120,
      clientY: 220,
      preventDefault() {},
      target: pointerTarget,
    });

    hitRow = targetRow;
    windowStub.listeners.get("pointermove")?.({
      clientX: 180,
      clientY: 420,
    });

    assert.equal(sourceRow.classList.contains("is-dragging"), true);
    assert.equal(middleRow.classList.contains("is-drop-after"), true);
    assert.equal(appendedNodes[0], ghostNode);
    assert.equal(ghostNode.classList.contains("is-drag-ghost"), true);
    assert.equal(ghostNode.style.width, "720px");

    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(movePayload, {
      sourceSegmentId: "seg-1",
      targetSegmentId: "seg-2",
      placement: "after",
    });
    assert.equal(ghostNode.removed, true);
    assert.equal(sourceRow.classList.contains("is-dragging"), false);
    assert.equal(middleRow.classList.contains("is-drop-after"), false);
  } finally {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  }
});

test("bindFinalPathCardDrag resolves nearest before-placement by crossed bottom edge", async () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const windowStub = createWindowStub();
  let hitRow = null;
  const documentStub = {
    body: {
      appendChild() {},
    },
    elementFromPoint() {
      return hitRow;
    },
  };
  globalThis.window = windowStub;
  globalThis.document = documentStub;

  try {
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
          },
        };
      },
    };
    const sourceCard = {
      getBoundingClientRect() {
        return {
          left: 100,
          top: 300,
          width: 720,
          height: 56,
        };
      },
      cloneNode() {
        return {
          style: {},
          classList: createClassList(),
          remove() {},
        };
      },
    };
    const topCard = {
      getBoundingClientRect() {
        return {
          top: 190,
          bottom: 246,
        };
      },
    };
    const bottomCard = {
      getBoundingClientRect() {
        return {
          top: 390,
          bottom: 446,
        };
      },
    };
    const cardList = {
      contains(node) {
        return node === topRow || node === sourceRow || node === bottomRow;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-row-id]") {
          return [topRow, sourceRow, bottomRow];
        }
        return [];
      },
    };
    const topRow = {
      dataset: { finalPathRowId: "seg-1" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return topCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const sourceRow = {
      dataset: { finalPathRowId: "seg-2" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return sourceCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const bottomRow = {
      dataset: { finalPathRowId: "seg-3" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return bottomCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const handleNode = {
      dataset: { finalPathRowDragId: "seg-2" },
      closest(selector) {
        if (selector === "[data-final-path-row-id]") {
          return sourceRow;
        }
        return null;
      },
    };
    const pointerTarget = {
      closest(selector) {
        if (selector === "[data-final-path-row-drag-id]") {
          return handleNode;
        }
        return null;
      },
    };
    let movePayload = null;
    bindFinalPathCardDrag(host, store, {
      moveFinalPathRow(_host, _store, payload) {
        movePayload = payload;
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 120,
      clientY: 320,
      preventDefault() {},
      target: pointerTarget,
    });

    hitRow = topRow;
    windowStub.listeners.get("pointermove")?.({
      clientX: 180,
      clientY: 220,
    });

    assert.equal(topRow.classList.contains("is-drop-before"), true);

    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(movePayload, {
      sourceSegmentId: "seg-2",
      targetSegmentId: "seg-1",
      placement: "before",
    });
  } finally {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  }
});

test("bindFinalPathCardDrag keeps live input and select values on the drag ghost in table mode", async () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const windowStub = createWindowStub();
  const appendedNodes = [];
  const sourceInput = createFormField({
    value: "hifiasm_Ctg2_edited",
  });
  const ghostInput = createFormField({
    value: "stale-name",
  });
  const sourceSelect = createFormField({
    tagName: "SELECT",
    value: "-",
    selectedIndex: 1,
    options: [
      { selected: false },
      { selected: true },
    ],
  });
  const ghostSelect = createFormField({
    tagName: "SELECT",
    value: "+",
    selectedIndex: 0,
    options: [
      { selected: true },
      { selected: false },
    ],
  });
  const ghostNode = {
    style: {},
    classList: createClassList(),
    remove() {},
    querySelectorAll(selector) {
      if (selector === "input, textarea, select") {
        return [ghostInput, ghostSelect];
      }
      return [];
    },
  };
  const sourceCard = {
    getBoundingClientRect() {
      return {
        left: 100,
        top: 120,
        width: 720,
        height: 56,
      };
    },
    cloneNode() {
      return ghostNode;
    },
    querySelectorAll(selector) {
      if (selector === "input, textarea, select") {
        return [sourceInput, sourceSelect];
      }
      return [];
    },
  };
  const documentStub = {
    body: {
      appendChild(node) {
        appendedNodes.push(node);
      },
    },
  };
  globalThis.window = windowStub;
  globalThis.document = documentStub;

  try {
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
          },
        };
      },
    };
    const cardList = {
      querySelectorAll(selector) {
        if (selector === "[data-final-path-row-id]") {
          return [sourceRow, targetRow];
        }
        return [];
      },
    };
    const sourceRow = {
      dataset: { finalPathRowId: "seg-1" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return sourceCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const targetRow = {
      dataset: { finalPathRowId: "seg-2" },
      classList: createClassList(),
      querySelector() {
        return {
          getBoundingClientRect() {
            return {
              top: 220,
              bottom: 276,
            };
          },
        };
      },
    };
    const handleNode = {
      dataset: { finalPathRowDragId: "seg-1" },
      closest(selector) {
        if (selector === "[data-final-path-row-id]") {
          return sourceRow;
        }
        return null;
      },
    };
    const pointerTarget = {
      closest(selector) {
        if (selector === "[data-final-path-row-drag-id]") {
          return handleNode;
        }
        return null;
      },
    };

    bindFinalPathCardDrag(host, store, {
      moveFinalPathRow() {},
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 120,
      clientY: 140,
      preventDefault() {},
      target: pointerTarget,
    });

    windowStub.listeners.get("pointermove")?.({
      clientX: 132,
      clientY: 164,
    });

    assert.equal(appendedNodes[0], ghostNode);
    assert.equal(ghostInput.value, "hifiasm_Ctg2_edited");
    assert.equal(ghostSelect.value, "-");
    assert.equal(ghostSelect.selectedIndex, 1);
    assert.deepEqual(
      ghostSelect.options.map((option) => option.selected),
      [false, true],
    );
  } finally {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  }
});

test("bindFinalPathCardDrag preserves final path table column layout on the drag ghost", async () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalGetComputedStyle = globalThis.getComputedStyle;
  const windowStub = createWindowStub();
  const tableBodyNode = {
    style: createStyleDeclaration({
      "--final-path-table-columns":
        "34px minmax(140px, 1.35fr) minmax(124px, 1fr) minmax(92px, 0.72fr) minmax(64px, 0.5fr) minmax(100px, 0.9fr) minmax(100px, 0.9fr) minmax(100px, 0.9fr) minmax(100px, 0.9fr) 34px",
    }),
  };
  const ghostNode = {
    style: createStyleDeclaration(),
    classList: createClassList(),
    remove() {},
  };
  const sourceCard = {
    getBoundingClientRect() {
      return {
        left: 100,
        top: 120,
        width: 720,
        height: 56,
      };
    },
    cloneNode() {
      return ghostNode;
    },
    closest(selector) {
      if (selector === ".final-path-card-table-body") {
        return tableBodyNode;
      }
      return null;
    },
  };
  const documentStub = {
    body: {
      appendChild() {},
    },
  };
  globalThis.window = windowStub;
  globalThis.document = documentStub;
  globalThis.getComputedStyle = (node) => ({
    getPropertyValue(name) {
      return node?.style?.getPropertyValue?.(name) || "";
    },
  });

  try {
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
          },
        };
      },
    };
    const cardList = {
      querySelectorAll(selector) {
        if (selector === "[data-final-path-row-id]") {
          return [sourceRow, targetRow];
        }
        return [];
      },
    };
    const sourceRow = {
      dataset: { finalPathRowId: "seg-1" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return sourceCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const targetRow = {
      dataset: { finalPathRowId: "seg-2" },
      classList: createClassList(),
      querySelector() {
        return {
          getBoundingClientRect() {
            return {
              top: 220,
              bottom: 276,
            };
          },
        };
      },
    };
    const handleNode = {
      dataset: { finalPathRowDragId: "seg-1" },
      closest(selector) {
        if (selector === "[data-final-path-row-id]") {
          return sourceRow;
        }
        return null;
      },
    };
    const pointerTarget = {
      closest(selector) {
        if (selector === "[data-final-path-row-drag-id]") {
          return handleNode;
        }
        return null;
      },
    };

    bindFinalPathCardDrag(host, store, {
      moveFinalPathRow() {},
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 120,
      clientY: 140,
      preventDefault() {},
      target: pointerTarget,
    });

    windowStub.listeners.get("pointermove")?.({
      clientX: 132,
      clientY: 164,
    });

    assert.equal(
      ghostNode.style.getPropertyValue("--final-path-table-columns"),
      "34px minmax(140px, 1.35fr) minmax(124px, 1fr) minmax(92px, 0.72fr) minmax(64px, 0.5fr) minmax(100px, 0.9fr) minmax(100px, 0.9fr) minmax(100px, 0.9fr) minmax(100px, 0.9fr) 34px",
    );
  } finally {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
    globalThis.getComputedStyle = originalGetComputedStyle;
  }
});

test("bindFinalPathCardDrag drops above the first row into the first position even before crossing its top edge", async () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const windowStub = createWindowStub();
  const documentStub = {
    body: {
      appendChild() {},
    },
  };
  globalThis.window = windowStub;
  globalThis.document = documentStub;

  try {
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
          },
        };
      },
    };
    const sourceCard = {
      getBoundingClientRect() {
        return {
          left: 100,
          top: 300,
          width: 720,
          height: 56,
        };
      },
      cloneNode() {
        return {
          style: {},
          classList: createClassList(),
          remove() {},
        };
      },
    };
    const topCard = {
      getBoundingClientRect() {
        return {
          top: 190,
          bottom: 246,
        };
      },
    };
    const bottomCard = {
      getBoundingClientRect() {
        return {
          top: 390,
          bottom: 446,
        };
      },
    };
    const cardList = {
      contains(node) {
        return node === topRow || node === sourceRow || node === bottomRow;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-row-id]") {
          return [topRow, sourceRow, bottomRow];
        }
        return [];
      },
    };
    const topRow = {
      dataset: { finalPathRowId: "seg-1" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return topCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const sourceRow = {
      dataset: { finalPathRowId: "seg-2" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return sourceCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const bottomRow = {
      dataset: { finalPathRowId: "seg-3" },
      classList: createClassList(),
      querySelector(selector) {
        if (selector === "[data-final-path-card-body]") {
          return bottomCard;
        }
        return null;
      },
      closest(selector) {
        if (selector === "[data-final-path-card-list]") {
          return cardList;
        }
        return null;
      },
    };
    const handleNode = {
      dataset: { finalPathRowDragId: "seg-2" },
      closest(selector) {
        if (selector === "[data-final-path-row-id]") {
          return sourceRow;
        }
        return null;
      },
    };
    const pointerTarget = {
      closest(selector) {
        if (selector === "[data-final-path-row-drag-id]") {
          return handleNode;
        }
        return null;
      },
    };
    let movePayload = null;
    bindFinalPathCardDrag(host, store, {
      moveFinalPathRow(_host, _store, payload) {
        movePayload = payload;
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 120,
      clientY: 320,
      preventDefault() {},
      target: pointerTarget,
    });

    windowStub.listeners.get("pointermove")?.({
      clientX: 180,
      clientY: 150,
    });

    assert.equal(topRow.classList.contains("is-drop-before"), true);

    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(movePayload, {
      sourceSegmentId: "seg-2",
      targetSegmentId: "seg-1",
      placement: "before",
    });
  } finally {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  }
});
