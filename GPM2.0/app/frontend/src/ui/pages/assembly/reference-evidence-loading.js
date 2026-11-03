import { referenceHitsUnloaded, hasDeferredReferenceHits } from "../../../services/workflow/reference-evidence.js";
import { currentAssemblyViewRequest } from "./assembly-view-request.js";

export function referenceSubviewNeedsRaw(summary) {
  if (summary?.mode === "2-contig") return summary.top?.role === "ref" && summary.bottom?.role === "ref";
  return false; // Composition and one-Ref pairs project the opposite CTG evidence.
}
export function missingSubviewReferenceEvidence(assembly) {
  return referenceSubviewNeedsRaw(assembly?.subview?.summary)
    ? (assembly.refTrackMembers || []).filter(referenceHitsUnloaded) : [];
}
const pending = new WeakMap();
const identity = member => [member.referenceChrId,member.segmentOrder,member.segmentStartBp,member.segmentEndBp].join(":");

export async function ensureSubviewReferenceEvidence(host, store, { load, render, mapError }) {
  const initial = store.getState(), missing = missingSubviewReferenceEvidence(initial.assembly);
  if (!missing.length) return true;
  const existing = pending.get(store);
  if (existing?.current()) return existing.promise;
  const missingSet=new Set(missing);
  const members = initial.assembly.refTrackMembers.map(member => missingSet.has(member)
    ? { ...member,referenceEvidence:{encoding:"reference-hits-unloaded",status:"loading"} } : member);
  const summary = initial.assembly.subview.summary;
  const view = currentAssemblyViewRequest(store);
  const request = {};
  let invalidated=false, published=false, unsubscribe;
  const sameScope = () => {
    const state=store.getState();
    return currentAssemblyViewRequest(store) === view
      && state.activeRoute === initial.activeRoute
      && state.session?.workspacePath === initial.session?.workspacePath && state.session?.projectId === initial.session?.projectId
      && state.assembly?.selectedChrName === initial.assembly.selectedChrName
      && state.assembly?.subview?.summary === summary;
  };
  const current=()=>!invalidated && pending.get(store)===request && sameScope()
    && store.getState().assembly?.refTrackMembers===members;
  let resolveRequest,rejectRequest;
  request.promise=new Promise((resolve,reject)=>{resolveRequest=resolve;rejectRequest=reject;});
  request.current = current; pending.set(store,request);
  // A new marker array must not mutate cached snapshots or previous store state.
  store.setState({assembly:{...initial.assembly,refTrackMembers:members}});
  unsubscribe=store.subscribe?.(()=>{if (!current()) invalidated=true;});
  const work = (async () => {
    try {
      const result = await load({ workspaceRoot:initial.session.workspacePath,projectId:initial.session.projectId,
        chrName:initial.assembly.selectedChrName,deferHits:true,geometryOnly:false });
      if (!current()) return false;
      const ready = new Map((result?.items || []).map(member => [identity(member),member]));
      if ((result?.items || []).length !== members.length || ready.size !== members.length
        || members.some(member => !ready.has(identity(member)) || referenceHitsUnloaded(ready.get(identity(member))))) {
        throw Error("Reference geometry changed while loading evidence; reload the chromosome");
      }
      const next = members.map(member => {
        const loaded = ready.get(identity(member));
        if (loaded.referenceEvidence ? !hasDeferredReferenceHits(loaded) : !Array.isArray(loaded.hits)) {
          throw Error("Reference evidence response is incomplete");
        }
        return { ...member, ...(loaded.referenceEvidence ? { referenceEvidence:loaded.referenceEvidence } : { hits:loaded.hits,referenceEvidence:undefined }) };
      });
      unsubscribe?.();published=true;
      store.setState({ assembly:{...store.getState().assembly,refTrackMembers:next} });
      return true;
    } catch (error) {
      if (!current()) return false;
      const message = mapError(error,store.getState());
      unsubscribe?.();published=true;
      store.setState({assembly:{...store.getState().assembly,refTrackMembers:members.map(member => referenceHitsUnloaded(member)
        ? {...member,referenceEvidence:{encoding:"reference-hits-unloaded",status:"error",error:message}} : member)}});
      return false;
    } finally {
      const owns=pending.get(store)===request;
      unsubscribe?.();
      if (owns) pending.delete(store);
      if (owns && published && !invalidated && sameScope()) render?.(host,store);
    }
  })();
  void work.then(resolveRequest,rejectRequest);
  render?.(host,store);
  return request.promise;
}
