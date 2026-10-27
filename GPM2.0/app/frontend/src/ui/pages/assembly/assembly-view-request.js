// Shared, non-persisted generation for all loads of an Assembly viewing scope.
// Scope names alone cannot reject a late response after A -> B -> A navigation.
const requests = new WeakMap();

export function beginAssemblyViewRequest(store) {
  const request = {};
  requests.set(store, request);
  return request;
}

export function currentAssemblyViewRequest(store) {
  return requests.get(store);
}
