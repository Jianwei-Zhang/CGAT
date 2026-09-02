export function createProjectViewMutationCoordinator() {
  let generation = 0;
  let tail = Promise.resolve();

  return {
    enqueue(task) {
      if (typeof task !== "function") {
        throw new TypeError("project-view mutation task must be a function");
      }
      const taskGeneration = generation;
      const run = async () => {
        const isCurrent = () => taskGeneration === generation;
        if (!isCurrent()) {
          return { skipped: true };
        }
        return task(isCurrent);
      };
      const result = tail.then(run, run);
      tail = result.catch(() => undefined);
      return result;
    },
    invalidate() {
      generation += 1;
      tail = Promise.resolve();
    },
    get generation() {
      return generation;
    },
  };
}
