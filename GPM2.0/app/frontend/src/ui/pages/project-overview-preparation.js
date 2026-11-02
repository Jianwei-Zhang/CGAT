import { PREVIEW_MODEL_VERSION } from "./project-preview-cache.js";
import { getProjectOverviewSources, getProjectPreviewCache } from "../../services/workflow-api.js";
import { previewMutationStamp } from "../../services/preview-content-events.js";
import { groupProjectOverviewSources } from "./project-overview-sources.js";

// A disposable import prewarm, not a persistent cache or an alternate source of
// truth. Consumption still follows the normal saved-view/LGZ/overlay loader.
const sessions = new WeakMap();
const keyFor = ({workspaceRoot,projectId}) => JSON.stringify([String(workspaceRoot||"").trim(),Number(projectId)]);
const now = () => globalThis.performance?.now?.() ?? Date.now();
function session(store) {
  if (!sessions.has(store)) sessions.set(store,{entries:new Map(),pending:new Map(),guards:new WeakMap()});
  return sessions.get(store);
}

export async function prepareProjectOverviewSources(store,args,deps={},options={}) {
  const start=(deps.now||now)(),state=session(store),key=keyFor(args),token={};
  const shouldContinue=options.shouldContinue||(()=>true);
  state.entries.delete(key);state.pending.set(key,token);
  const current=()=>state.pending.get(key)===token && shouldContinue();
  const stamp=previewMutationStamp(args);
  const getMetadata=deps.getProjectPreviewCache||getProjectPreviewCache;
  const metadataArgs=entry=>({...args,modelVersion:PREVIEW_MODEL_VERSION,
    expectedIdentity:entry?.identity||null,sinceRevision:entry?.revision??null});
  const valid=metadata=>metadata?.available === true && metadata.trackingVersion>=3
    && typeof metadata.identity==="string" && metadata.identity.length>0 && Number.isSafeInteger(metadata.revision) && metadata.revision>=0;
  const result=(ready,error="",sourceCount=0)=>({ready,error,sourceCount,elapsedMs:Math.max(0,(deps.now||now)()-start)});
  try {
    if (!current()) return result(false);
    const before=await getMetadata(metadataArgs(options.expectedPreview));
    if(!current())return result(false);
    if(!valid(before))return result(false,"Overview preparation validity is unavailable");
    const sources=await (deps.getProjectOverviewSources||getProjectOverviewSources)(args);
    if (!current() || previewMutationStamp(args)!==stamp) return result(false);
    groupProjectOverviewSources(sources); // Validate the authoritative contract.
    if (Number(sources.projectId)!==Number(args.projectId)) throw Error("Prepared overview belongs to a different project");
    const after=await getMetadata(metadataArgs(before));
    if(!current() || previewMutationStamp(args)!==stamp || !valid(after)
      || after.identity!==before.identity || after.revision!==before.revision)return result(false);
    state.entries.set(key,{stamp,sources,identity:after.identity,revision:after.revision,getMetadata});
    while(state.entries.size>3)state.entries.delete(state.entries.keys().next().value);
    return result(true,"",sources.ctgs.length);
  } catch(error) {
    return result(false,String(error?.message||error));
  } finally {
    if(state.pending.get(key)===token)state.pending.delete(key);
  }
}

export function hasPreparedOverviewSources(store,args) {
  return sessions.get(store)?.entries.has(keyFor(args)) || false;
}

export async function consumePreparedOverviewSources(store,args) {
  const state=sessions.get(store),key=keyFor(args),entry=state?.entries.get(key);
  if (!entry) return null;
  state.entries.delete(key);
  if(entry.stamp!==previewMutationStamp(args))return null;
  try {
    const metadata=await entry.getMetadata({...args,modelVersion:PREVIEW_MODEL_VERSION,
      expectedIdentity:entry.identity,sinceRevision:entry.revision});
    const valid=metadata?.available === true && metadata.trackingVersion>=3 && metadata.identity===entry.identity
      && metadata.revision===entry.revision && entry.stamp===previewMutationStamp(args);
    if(valid)state.guards.set(entry.sources,entry);
    return valid?entry.sources:null;
  }catch{return null;}
}


// A source prewarm must still be current after the ordinary saved-view/LGZ
// roundtrips. This also fences edits from another App/process, not just stamps.
export async function validatePreparedOverviewSources(store,args,sources) {
  const entry=sessions.get(store)?.guards.get(sources);
  if(!entry)return true;
  if(entry.stamp!==previewMutationStamp(args))return false;
  try{
    const metadata=await entry.getMetadata({...args,modelVersion:PREVIEW_MODEL_VERSION,
      expectedIdentity:entry.identity,sinceRevision:entry.revision});
    return metadata?.available === true && metadata.trackingVersion>=3 && metadata.identity===entry.identity
      && metadata.revision===entry.revision && entry.stamp===previewMutationStamp(args);
  }catch{return false;}
}
