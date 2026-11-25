"""Use the entire original competition set; shortlist only links that could emit a paired block."""
from bisect import bisect_left,bisect_right
from collections import Counter
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from unittest.mock import patch
from weakref import WeakKeyDictionary
from lgz_core import q0_paths as paths
from pilot_exact_group_runs import axes,clipped


class Axis:
    def __init__(self, rows, col):
        self.rows=sorted(rows,key=lambda v:v[col]);self.starts=[v[col] for v in self.rows];end=0;self.prefix=[]
        for v in self.rows:
            end=max(end,v[col+1]);self.prefix.append(end)

    def span(self, iv):return bisect_right(self.prefix,iv.start),bisect_left(self.starts,iv.end)


class Panel:
    def __init__(self, evidence, left, right, excluded):
        self.links=tuple(v for v in evidence if v.hit.evidence_id not in excluded);self.axes=None
        rows=[]
        for i,v in enumerate(self.links):
            h=v.hit;x=h.query.start+v.query_offset;z=h.query.end+v.query_offset;y=h.target.start+v.target_offset;w=h.target.end+v.target_offset
            if (v.query_source,v.target_source)==(left,right):rows.append((x,z,y,w,i))
            if (v.target_source,v.query_source)==(left,right):rows.append((y,w,x,z,i))
        self.left=Axis(rows,0);self.right=Axis(rows,2)

    def candidates(self,l,r):
        a,b=self.left.span(l.interval);c,d=self.right.span(r.interval)
        axis,lo,hi=(self.left,a,b) if b-a<=d-c else (self.right,c,d)
        ids=set();x,z=l.interval.start,l.interval.end;y,w=r.interval.start,r.interval.end;forward=l.orientation==r.orientation
        for i in range(lo,hi):
            u,v,p,q,j=axis.rows[i];h=self.links[j].hit
            if x<v and u<z and y<q and p<w and (h.strand=="+")==forward:ids.add(j)
        return tuple(self.links[i] for i in sorted(ids))


@contextmanager
def sparse_graph():
    # This pilot uses an immutable PathGraph. The only exclusion transition in its constructor
    # assigns a NEW set, and clears the normal placement-block cache before subsequent lookups.
    graphs=WeakKeyDictionary();context=ContextVar("whole_source_pair",default=None);stats=Counter()
    def full_axes(links,a,b,m):
        active=context.get()
        if active is None:return axes(links,a,b,m)
        panel,left,right,minimum=active
        if (left,right,minimum)!=(a,b,m):raise RuntimeError("wrong competition frame")
        if panel.axes is None:panel.axes=axes(panel.links,a,b,m);stats["whole_axis_builds"]+=1
        return panel.axes
    def blocks(graph,l,r):
        k=l.placement_id,r.placement_id
        if k in graph._blocks:return graph._blocks[k]
        ids=graph.ambiguous_equivalence_ids;a,b=l.source,r.source;minimum=graph.policy.minimum_anchor_bp
        entry=graphs.get(graph);pair=(a,b)
        if entry is None or entry[0] is not ids or entry[1]!=pair:
            panel=Panel(graph.links.get(tuple(sorted(pair)),()),a,b,ids); graphs[graph]=ids,pair,panel
        else:panel=entry[2]
        candidates=panel.candidates(l,r);stats["potential_link_visits"]+=len(panel.links);stats["candidate_link_visits"]+=len(candidates)
        if candidates:
            token=context.set((panel,a,b,minimum))
            try:ans=paths.qualify_pair_blocks(l,r,candidates,graph.policy)
            finally:context.reset(token)
        else:ans=()
        graph._blocks[k]=ans;return ans
    with ExitStack() as s:
        s.enter_context(patch.object(paths,"pair_blocks",clipped));s.enter_context(patch.object(paths,"_competing_axes",full_axes))
        s.enter_context(patch.object(paths.PathGraph,"homologous_blocks",blocks));yield stats
