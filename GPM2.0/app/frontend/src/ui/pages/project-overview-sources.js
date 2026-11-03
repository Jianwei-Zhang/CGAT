// Share the existing projectExport state between Path Overview and Overview.
// Membership is authoritative backend data, not a datasetId approximation.
export function groupProjectOverviewSources(sources) {
  if (!Array.isArray(sources?.chromosomes) || !Array.isArray(sources?.ctgs)
      || !Array.isArray(sources?.primaryCtgIds)) {
    throw new TypeError("Invalid project overview source payload");
  }
  const names = sources.chromosomes.map(chr => String(chr?.chrName || "").trim()).filter(Boolean);
  const ctgsByChr = Object.fromEntries(names.map(name => [name, []]));
  const primaryIds = new Set(sources.primaryCtgIds.map(Number));
  for (const ctg of sources.ctgs) {
    const name = String(ctg?.assignedChrName || "");
    if (Object.hasOwn(ctgsByChr, name)) ctgsByChr[name].push(ctg);
  }
  const primaryCtgsByChr = Object.fromEntries(names.map(name => [name,
    ctgsByChr[name].filter(ctg => primaryIds.has(Number(ctg.assemblyCtgId)))]));
  return { ctgsByChr, primaryCtgsByChr };
}
