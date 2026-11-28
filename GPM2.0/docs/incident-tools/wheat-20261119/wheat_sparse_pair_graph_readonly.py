"""Diagnostic exact sparse graph iteration: omit only impossible paired geometry.

All original links still go to qualify_pair_blocks, including competitors outside
proposed fragments. This only replaces a Cartesian placement-pair loop with
pairs reached by actual non-X CIGAR blocks, in original placement-pair order.
"""
import argparse,ast,inspect,json,pickle,subprocess,textwrap
from bisect import bisect_left,bisect_right
from collections import Counter
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from lgz_core import q0_paths as paths,q0_admission as adm
from wheat_selection_checkpoint import decode
from wheat_reference_funnel_readonly import write,digest
from wheat_single_group_replay_readonly import need
import wheat_local_chain_selection_readonly as selection


def placement_index(rows):
    ordered=sorted(enumerate(rows),key=lambda v:(v[1].interval.start,v[1].interval.end,v[0]));starts=[];ends=[];farthest=-1
    for _,p in ordered:starts.append(p.interval.start);farthest=max(farthest,p.interval.end);ends.append(farthest)
    return ordered,starts,ends


def overlaps(index,interval):
    rows,starts,ends=index
    for i,p in rows[bisect_right(ends,interval.start):bisect_left(starts,interval.end)]:
        if p.interval.intersection(interval) is not None:yield i,p


def incident_pairs(lefts,rights,links,stats=None):
    if not lefts or not rights:return ()
    li=placement_index(lefts);ri=placement_index(rights);found=set();a,b=lefts[0].source,rights[0].source
    for link in links:
        if (link.query_source,link.target_source)==(a,b):swap=False
        elif (link.query_source,link.target_source)==(b,a):swap=True
        else:raise ValueError('foreign source-pair link')
        for query,target in link.source_blocks():
            q,t=(target,query) if swap else (query,target)
            for i,left in overlaps(li,q):
                iv=left.interval.intersection(q);projected=adm._project(q,t,link.hit.strand,iv)
                for j,right in overlaps(ri,projected):
                    if (link.hit.strand=='+')==(left.orientation==right.orientation):found.add((i,j))
    if stats is not None:stats['source_pairs']+=1;stats['cartesian_placement_pairs']+=len(lefts)*len(rights);stats['actual_geometry_candidate_pairs']+=len(found)
    return tuple((lefts[i],rights[j]) for i,j in sorted(found))


def sparse_constructor(stats):
    source=textwrap.dedent(inspect.getsource(paths.PathGraph.__init__));tree=ast.parse(source);changed=0
    class Change(ast.NodeTransformer):
        def visit_For(self,node):
            nonlocal changed
            if isinstance(node.target,ast.Name) and node.target.id=='left' and ast.unparse(node.iter)=='by_source[a]':
                need(len(node.body)==1 and isinstance(node.body[0],ast.For) and ast.unparse(node.body[0].iter)=='by_source[b]','different graph loop')
                node.target=ast.Tuple(elts=[ast.Name(id='left',ctx=ast.Store()),ast.Name(id='right',ctx=ast.Store())],ctx=ast.Store());node.iter=ast.Call(func=ast.Name(id='diagnostic_pairs',ctx=ast.Load()),args=[node.iter,node.body[0].iter,ast.Name(id='links_for_pair',ctx=ast.Load())],keywords=[]);node.body=node.body[0].body;changed+=1;return node
            return self.generic_visit(node)
    tree=Change().visit(tree);need(changed==1,'missing graph Cartesian loop');ast.fix_missing_locations(tree);ns=dict(vars(paths));ns['diagnostic_pairs']=lambda a,b,links:incident_pairs(a,b,links,stats);exec(compile(tree,'<isolated-exact-sparse-graph>','exec'),ns)
    return ns['__init__'],sha256(source.encode()).hexdigest(),sha256(ast.dump(tree).encode()).hexdigest()


def run(base,owner):
    report=json.loads((owner/'blockers.json').read_text());raw=(owner/'frozen-1A-graph.pickle').read_bytes();need(sha256(raw).hexdigest()==report['graph_pickle_sha256'],'frozen graph changed');old=pickle.loads(raw);baseline=decode(json.loads((owner/'baseline-path.json').read_text()));stats=Counter();constructor,original_pin,new_pin=sparse_constructor(stats);links=[link for rows in old.links.values() for link in rows]
    with patch.object(paths.PathGraph,'__init__',constructor):
        new=paths.PathGraph(list(old.placements.values()),links,old.original,old.policy,first_request=True,progress=lambda s:print('SPARSE_BASELINE',s,flush=True))
        need(new.required==old.required and new.ambiguous_equivalence_ids==old.ambiguous_equivalence_ids,'sparse graph evidence changed');need(new.coverage.atoms==old.coverage.atoms and new.coverage.units==old.coverage.units and new.coverage.ambiguous_evidence_ids==old.coverage.ambiguous_evidence_ids,'sparse exact coverage model changed');need(new._score_candidate(baseline.nodes,baseline.joins)==baseline,'frozen winner changed under sparse construction')
        proof={'schema':'wheat_exact_sparse_pair_graph_proof_v1','frozen_graph_sha256':report['graph_pickle_sha256'],'original_constructor_sha256':original_pin,'sparse_constructor_ast_sha256':new_pin,'baseline_required_equal':True,'baseline_ambiguity_equal':True,'baseline_coverage_atoms_and_units_equal':True,'baseline_full_winner_equal':True,'baseline_pair_counts':dict(stats),'scientific_gate_changes':False};write(owner/'sparse-graph-baseline-proof.json',proof);print('SPARSE_BASELINE_PROVED',json.dumps(dict(stats)),flush=True);del new,links;stats.clear()
        original_load=selection.load_links
        def separate_links(base_path,owner_path,sources):
            stage=owner_path/'regional-evidence';stage.mkdir(mode=0o700,exist_ok=True)
            return original_load(base_path,stage,sources)
        with patch.object(selection,'load_links',separate_links):selection.run(base,owner,('regional',))
        proof['regional_pair_counts']=dict(stats);proof['regional_selection_report_sha256']=digest(owner/'candidate-selection-regional.json');write(owner/'sparse-graph-final-proof.json',proof);print('SPARSE_REGIONAL_DONE',json.dumps(dict(stats)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);a=p.parse_args();need(a.owner.resolve().parent==a.base.resolve() and a.owner.name.startswith('q0-local-chain-') and a.owner.stat().st_mode&0o077==0,'private owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external command forbidden')):run(a.base.resolve(),a.owner.resolve())
