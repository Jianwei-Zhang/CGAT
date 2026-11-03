// An optional optimization over a complete, revision-fenced in-session input.
// Never reconstruct provenance from display names or a partial disk snapshot.
import {affectedPreviewChromosomes} from "./project-preview-cache.js";
const id=value=>Number.isSafeInteger(value)&&value>0;
const ids=values=>Array.isArray(values)&&values.every(id)&&new Set(values).size===values.length;
export function planPreviewSourceDelta(inputs,payload,dirtyNames) {
 if(!inputs||!Array.isArray(inputs.ctgs)||!Array.isArray(payload?.dependencies)||!Array.isArray(payload?.cards))return null;
 const affected=affectedPreviewChromosomes(dirtyNames,payload.cards,payload.pathParents);
 if(!affected?.size || !inputs.ctgs.every(ctg=>id(ctg.assemblyCtgId)&&id(ctg.originSourceSeqId)))return null;
 const dependencies=payload.dependencies.filter(item=>affected.has(item.chrName));
 if(dependencies.length!==affected.size || dependencies.some(item=>!Array.isArray(item.ctgIds)||!Array.isArray(item.sourceNames)))return null;
 const dependentIds=new Set(dependencies.flatMap(item=>item.ctgIds)),sourceIds=new Set(),datasetIds=new Set();
 for(const ctg of inputs.ctgs)if(dependentIds.has(ctg.assemblyCtgId)||affected.has(ctg.assignedChrName)||(ctg.coAssignedChrNames||[]).some(name=>affected.has(name)))sourceIds.add(ctg.originSourceSeqId);
 for(const source of dependencies.flatMap(item=>item.sourceNames)) {
  // Original-source names may acquire a different candidate after a rename.
  // Refresh their entire dataset conservatively, not only old named matches.
  const candidates=[...inputs.ctgs.filter(ctg=>ctg.datasetName===source.datasetName).map(ctg=>ctg.datasetId),
   ...(inputs.datasets||[]).filter(ds=>[ds.name,ds.label].includes(source.datasetName)).map(ds=>ds.datasetId)].filter(id);
  if(!candidates.length)return null;for(const value of candidates)datasetIds.add(value);
 }
 return {dirtyChrNames:[...affected],sourceSeqIds:[...sourceIds].sort((a,b)=>a-b),datasetIds:[...datasetIds].sort((a,b)=>a-b)};
}
export function mergePreviewSourceDelta(previous,result,scope) {
 const delta=result?.delta;
 if(delta?.encoding!=="preview-source-delta-v1" || !ids(delta.sourceSeqIds)||!ids(delta.orderedCtgIds)||!Array.isArray(result.items))return null;
 const groups=new Set(delta.sourceSeqIds);
 if(scope.sourceSeqIds.some(value=>!groups.has(value)))return null;
 const merged=new Map(),seen=new Set();
 for(const ctg of previous) {if(!id(ctg.assemblyCtgId)||!id(ctg.originSourceSeqId)||seen.has(ctg.assemblyCtgId))return null;seen.add(ctg.assemblyCtgId);if(!groups.has(ctg.originSourceSeqId))merged.set(ctg.assemblyCtgId,ctg);}
 seen.clear();
 for(const ctg of result.items) {if(!id(ctg.assemblyCtgId)||!groups.has(ctg.originSourceSeqId)||seen.has(ctg.assemblyCtgId)||merged.has(ctg.assemblyCtgId))return null;seen.add(ctg.assemblyCtgId);merged.set(ctg.assemblyCtgId,ctg);}
 if(merged.size!==delta.orderedCtgIds.length || delta.orderedCtgIds.some(value=>!merged.has(value)))return null;
 return delta.orderedCtgIds.map(value=>merged.get(value));
}
