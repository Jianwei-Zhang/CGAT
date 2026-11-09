export function createStore(initialState) {
  let state = structuredClone(initialState);
  const listeners = new Set();
  const transforms = new Set();

  function getState() {
    return state;
  }

  function setState(partial) {
    let next = { ...state, ...partial };
    for (const transform of transforms) next = transform(state, next);
    state = next;
    for (const listener of listeners) {
      listener(state);
    }
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    getState,
    setState,
    subscribe,
    addStateTransform(transform) {
      transforms.add(transform);
      return () => transforms.delete(transform);
    },
  };
}
