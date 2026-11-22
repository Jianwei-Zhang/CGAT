"""Regional execution of the legacy candidate-chromosome request set.

Query selection remains unchanged. Large-input mapper scope changes explicitly:
actual source footprints are united across chromosomes, completed native source
matrices and observed unsplit source pairs are reused, and only reference-local
unknown relationships are mapped. These are not exhaustive all-source searches.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .common import stable_id
from .q0_catalog import _IntervalUnion, DISCOVERY_REFERENCE_IDENTITY
from .q0_neighbor_requests import known_neighbors
from .q0_query_windows import WindowPolicy, plan_query_windows, TargetWindow
from .q0_regional_mapping import BASE_FLAGS, MAX_TARGET_BASES, prepare_regional_mapping
from .q0_frontier_scope import window_touches_frontier
from .q0_sources import Interval, Q0EvidenceError
from .q0_regional_execution import ParentRequest, RegionalExecutor, plan_request, completed_result
from .q0_cigar_policy import WEAK_GLOBAL_SEED_POLICY, weak_global_seed_scope

CANDIDATE_POLICY = {
    "version": 2, "weak_unroutable_global_profile": WEAK_GLOBAL_SEED_POLICY, "core_bases": 100000, "context_bases": 10000, "query_selection": "exact_legacy_missing_neighbor_and_expanded_split",
    "query_context": "union_qualified_M_equal_reference_footprints_across_requested_chromosomes",
    "reference_identity": DISCOVERY_REFERENCE_IDENTITY, "minimum_query_footprint_bases": 100,
    "weak_only_alternatives": "keep_input_evidence_without_new_expansion_if_source_has_qualified_anchors",
    "targets": "unobserved_reference_local_candidate_parts",
    "reuse": "observed_unsplit_source_pairs_and_complete_native_part_matrices",
    "native_matrix_direction": "completed_unordered_relationship_not_both_direction_exhaustiveness",
    "missing_reference_target": "batch_small_unroutable_sources_as_native_queries_once",
    "native_seed_reuse": "complete_matrices_before_regional_planning_not_per_large_parent",
    "whole_source_equivalence": False,
}


def _bits(indices):
    result = 0
    for index in indices:
        result |= 1 << index
    return result


def _indices(mask):
    while mask:
        lowest = mask & -mask
        yield lowest.bit_length()-1
        mask ^= lowest


def candidate_window_targets(index, key, query, chromosomes, selection):
    """Plan one window from metadata/index only, never from the parent's DNA heap."""
    regions = index.regions(key,Interval(query.start,query.end),anchor_context=0,reference_context=10000)
    regions = {chromosome: intervals for chromosome,intervals in regions.items() if chromosome in chromosomes}
    if not regions: return [], "query_window_without_qualified_reference"
    rows = index.targets(regions,context=10000,exclude=[key],selection=selection)
    if sum(interval.length for values in rows.values() for interval in values) > MAX_TARGET_BASES:
        return [], "regional_target_budget"
    return [TargetWindow(pid,index.parts[pid].interval.length,i.start,i.end)
            for pid,values in rows.items() for i in values], None


class CompletedNativeScopes:
    """Complete raw matrices; approximate scopes exclude short-part relationships."""
    def __init__(self, root, catalog, index, complete_tasks, tool, preset):
        self.root,self.tool,self.preset = root,tool,preset
        self.catalog,self.index = catalog,index
        self.ids,self.ranks = index.part_order,index.part_ranks
        self.scopes = []
        self.scope_task_ids = []
        self.approximate_scope_task_ids = []
        self._scope_seen = set()
        self.add_complete_tasks(complete_tasks)

    def add_complete_tasks(self, complete_tasks):
        from .q0_preparation import json_file, artifact_path
        # Callers supply only already validated complete tasks. Check their
        # immutable specification again, without rehashing all native FASTAs.
        # All receipt output hashes are checked at final manifest publication.
        for task in complete_tasks:
            if task["kind"] == "regional_discovery" or task["task_id"] in self._scope_seen:
                continue
            relative = f'grt/evidence/q0_prepare/tasks/{task["task_id"]}'
            if task["receipt"] != relative+"/success.json" or task["paf"] != relative+"/result.paf":
                raise Q0EvidenceError("complete native scope path differs")
            receipt = json_file(artifact_path(self.root,task["receipt"]))
            spec = receipt.get("spec")
            outputs = receipt.get("outputs")
            required = {relative+"/"+name for name in ("query.fa","target.fa","result.paf","command.json")}
            if (not isinstance(spec,dict) or not isinstance(outputs,list) or len(outputs)!=4
                    or any(not isinstance(row,dict) or not isinstance(row.get("path"),str)
                           or not isinstance(row.get("sha256"),str) or len(row["sha256"])!=64
                           or type(row.get("size")) is not int or row["size"]<0 for row in outputs)
                    or {row["path"] for row in outputs} != required):
                raise Q0EvidenceError("complete native scope has an incomplete receipt")
            if (receipt.get("status") != "success" or spec.get("schema") != "lgz_q0_mapping_v1"
                    or stable_id("q0-map",spec) != task["task_id"]
                    or spec["tool"] != self.tool or spec["preset"] != self.preset
                    or spec["query_ids"] != task["query_ids"] or spec["target_ids"] != task["target_ids"]
                    or spec["members"] != [[key,self.catalog.parts[key].sequence_sha256]
                                           for key in sorted(set(task["query_ids"]+task["target_ids"]))]):
                raise Q0EvidenceError("complete native scope identity differs")
            queries,targets=task['query_ids'],task['target_ids']
            flags=spec.get('alignment_flags')
            if flags!=BASE_FLAGS:
                if (flags!=[*BASE_FLAGS,'-m',str(WEAK_GLOBAL_SEED_POLICY['minimum_chain_score'])]
                        or task['kind']!='candidate_unroutable_seed'):
                    raise Q0EvidenceError('complete matrix has an unsupported scientific profile')
                queries,targets=weak_global_seed_scope(self.catalog.parts,self.catalog.reference_routable_parts,
                    queries,targets,reference_bases=sum(self.index.reference_lengths.values()),preset=self.preset)
                if not queries or not targets:
                    raise Q0EvidenceError('approximate global seed is outside its limited scientific scope')
                self.approximate_scope_task_ids.append(task['task_id'])
            self.scopes.append((self.mask(queries),self.mask(targets)))
            self.scope_task_ids.append(task["task_id"])
            self._scope_seen.add(task["task_id"])

    def mask(self, keys):
        try:
            return _bits(self.ranks[key] for key in keys)
        except KeyError as exc:
            raise Q0EvidenceError("candidate scope contains an unknown part") from exc

    def keys(self, mask):
        return [self.ids[i] for i in _indices(mask)]

    def remaining_targets(self, key, requested, *, include_approximate=True):
        own = 1 << self.ranks[key]
        remaining = requested & ~own
        for (queries, targets),task_id in zip(self.scopes,self.scope_task_ids):
            if not include_approximate and task_id in self.approximate_scope_task_ids:continue
            if queries & own: remaining &= ~targets
            if targets & own: remaining &= ~queries
        return remaining


    def next_missing_seed(self, query_ids, target_ids):
        """Batch missing matrix edges without repeating the full global seed.

        Small query members may be included in the target batching key, so the
        short-target remainder does not fragment into one task per source.
        Never add a large normal query merely to equalize batching keys.
        """
        query_ids=tuple(sorted(set(query_ids)));requested=self.mask(target_ids)
        missing_by_query={key:self.remaining_targets(key,requested) for key in query_ids}
        small=self.mask(key for key,missing in missing_by_query.items()
                        if missing and self.catalog.parts[key].interval.length<=1_000_000)
        needed=0
        for missing in missing_by_query.values():needed |= missing
        peers=small & needed
        groups={}
        for key,missing in missing_by_query.items():
            if not missing:continue
            own=1 << self.ranks[key]
            target_mask=missing | peers
            # Preserve the original whole-matrix key when none of this query's
            # requested relationships were completed; -D still suppresses self.
            if small & own and missing==(requested & ~own):target_mask |= own
            groups.setdefault(target_mask,[]).append(key)
        if not groups:return None
        targets=max(groups,key=lambda mask:(mask.bit_count()*len(groups[mask]),mask.bit_count(),tuple(groups[mask])))
        queries,target_ids=groups[targets],self.keys(targets)
        floor=WEAK_GLOBAL_SEED_POLICY['minimum_part_bases']
        reverse=(min(self.catalog.parts[key].interval.length for key in queries)>=floor
                 and max(self.catalog.parts[key].interval.length for key in target_ids)<floor)
        return {'kind':'candidate_unroutable_seed','query_ids':target_ids if reverse else queries,
                'target_ids':queries if reverse else target_ids,
                'native_short_targets_as_queries':reverse,
                'reason':'complete_unroutable_relationships_once_before_regional_candidates'}


class CandidatePlan(CompletedNativeScopes):
    def __init__(self, root, catalog, index, requests, observed, complete_tasks, tool, preset):
        super().__init__(root,catalog,index,complete_tasks,tool,preset)
        if catalog.reference_routable_parts is None or catalog.reference_routable_footprints is None:
            raise Q0EvidenceError("candidate routing lacks qualified reference-part inventory")
        self.routable = self.mask(catalog.reference_routable_parts)
        self.source_parts = defaultdict(list)
        for key, part in catalog.parts.items():
            self.source_parts[part.source].append(key)
        self.neighbors = known_neighbors(observed)
        self.query_chromosomes = defaultdict(set)
        self.targets = {}
        for request in requests:
            chromosome = request["chromosome"]
            if request["kind"] != "candidate_chr" or chromosome in self.targets:
                raise Q0EvidenceError("invalid candidate request inventory")
            self.targets[chromosome] = self.mask(request["target_ids"])
            for key in request["query_ids"]:
                if key not in self.ranks: raise Q0EvidenceError("unknown candidate query")
                self.query_chromosomes[key].add(chromosome)
        self.cores = {}
        for (key,chromosome),intervals in catalog.reference_routable_footprints.items():
            if chromosome not in self.query_chromosomes.get(key, ()):
                continue
            part = catalog.parts[key]
            union = self.cores.setdefault(key, _IntervalUnion())
            for interval in intervals:
                if not part.interval.contains(interval):
                    raise Q0EvidenceError("candidate footprint exceeds original source part")
                union.append(Interval(interval.start-part.interval.start,interval.end-part.interval.start))

    def eligible(self, key):
        requested = 0
        for chromosome in self.query_chromosomes[key]: requested |= self.targets[chromosome]
        own = 1 << self.ranks[key]
        requested &= ~own
        remaining = self.remaining_targets(key,requested)
        source = self.catalog.parts[key].source
        # An original whole-source hit does not certify each newly split part.
        if len(self.source_parts[source]) == 1:
            for neighbor in self.neighbors.get(source, ()):
                parts = self.source_parts.get(neighbor, ())
                if len(parts) == 1:
                    remaining &= ~(1 << self.ranks[parts[0]])
        return requested, remaining

    def next_unroutable_seed(self):
        """Orient missing unindexed relations from the small unroutable side.

        Recompute after each complete matrix so the next batch does not repeat
        newly covered pairs. Do not fragment these small-query batches by
        isolated observed hits; complete native matrices remain authoritative.
        """
        used = self.mask(self.query_chromosomes)
        for mask in self.targets.values(): used |= mask
        return self.next_missing_seed(self.keys(used & ~self.routable),self.keys(used))

    def windows(self, key):
        length = self.catalog.parts[key].interval.length
        return plan_query_windows({key:length},{key:tuple(self.cores.get(key,()))},
                    policy=WindowPolicy(core_bases=100000,context_bases=10000,trigger_query_bases=1,trigger_longest_bases=1)) or ()

    def planning_request(self, key, eligible):
        """Owner retains eligibility decisions; workers receive no DNA/graph."""
        own = 1 << self.ranks[key]
        if not self.routable & own:
            return ParentRequest("candidate", key, ready=([], eligible, "query_without_qualified_reference"))
        if key not in self.cores:
            return ParentRequest("candidate", key, ready=([], eligible & ~self.routable,
                                                           "weak_reference_only_alternatives_not_expanded"))
        fallback = eligible & ~self.routable
        regional = eligible & self.routable
        if not regional:
            return ParentRequest("candidate", key, ready=([], fallback,
                                    "target_without_qualified_reference" if fallback else None))
        return ParentRequest("candidate", key, tuple(self.windows(key)),
                             tuple(sorted(self.query_chromosomes[key])), regional, fallback, eligible)

    def plan_parent(self, key, eligible):
        """Exact regional plans plus an explicit native-fallback target mask."""
        return plan_request(self.planning_request(key, eligible), self.index)


def prepare_candidates(root, catalog, index, requests, observed, complete_tasks, tool, *, reference_lengths, preset, threads, skip_self=False, planner=None, regional_frontier=None):
    if type(threads) is not int or threads < 1:
        raise Q0EvidenceError("candidate thread budget must be positive")
    if planner is None:
        planner = CandidatePlan(root,catalog,index,requests,observed,complete_tasks,tool,preset)
    elif planner.catalog is not catalog or planner.index is not index or planner.root != root or planner.tool != tool or planner.preset != preset:
        raise Q0EvidenceError("candidate planner belongs to another preparation")
    if planner.next_unroutable_seed() is not None:
        raise Q0EvidenceError("unroutable native source matrices must complete before regional candidates")
    execution = RegionalExecutor(index, threads)
    mapper_threads = execution.budget.mapper_threads; workers = execution.budget.mapper_workers
    print(f"LGZ q0 regional execution: phase=candidate planners={execution.budget.planner_workers} "
          f"mappers={workers} mapper_threads={mapper_threads} total_threads={threads} "
          "dispatch=completion_order result_order=original", flush=True)
    tasks, pending, fallback = [], {}, {}
    parent_order = {}
    report = {"policy":CANDIDATE_POLICY,"requested_parents":len(planner.query_chromosomes),
              "completed_native_scope_task_ids":planner.scope_task_ids,
              "approximate_scope_task_ids":planner.approximate_scope_task_ids,"requested_part_pairs":0,
              "reused_part_pairs":0,"regional_windows":0,"fallback_parents":0,"weak_only_parents_not_expanded":0,"weak_only_parent_ids":[],
              "maximum_workers":workers,"mapper_threads":mapper_threads,
              "frontier_scope": regional_frontier is not None, "frontier_omitted_windows": 0}
    def consume(): tasks.append(completed_result(pending))
    def requests():
        for key in sorted(planner.query_chromosomes):
            requested,eligible = planner.eligible(key)
            report["requested_part_pairs"] += requested.bit_count()
            report["reused_part_pairs"] += (requested & ~eligible).bit_count()
            if eligible:
                yield planner.planning_request(key, eligible)
    with execution, ThreadPoolExecutor(max_workers=workers,thread_name_prefix="q0-candidate") as pool:
        for number, (parent_number, request, (planned,native,reason)) in enumerate(execution.completed(requests()), 1):
            key = request.segment_id
            parent_order[key] = parent_number
            if reason == "weak_reference_only_alternatives_not_expanded":
                report["weak_only_parents_not_expanded"] += 1
                report["weak_only_parent_ids"].append(key)
            if native:
                # A large normal query must NOT be added to this target set
                # merely to make a batching key: indexing it is costly even -D.
                targets = tuple(planner.keys(native))
                item = fallback.setdefault(targets,{"kind":"candidate_chr","query_ids":[],"target_ids":list(targets),"regional_fallback":[]})
                item["query_ids"].append(key);item["regional_fallback"].append({"query":key,"reason":reason})
                report["fallback_parents"] += 1
            for window_number, (query, targets) in enumerate(planned):
                if skip_self and any(catalog.parts[t.segment_id].source.dataset == catalog.parts[query.segment_id].source.dataset for t in targets):
                    raise Q0EvidenceError("--skip-self conflicts with required regional candidate comparisons")
                if regional_frontier is not None and not window_touches_frontier(query, targets, catalog.parts, regional_frontier):
                    report["frontier_omitted_windows"] += 1
                    continue
                report["regional_windows"] += 1
                if len(pending) >= workers: consume()
                future = pool.submit(prepare_regional_mapping,root,catalog,query,targets,tool,
                                     reference_bases=sum(reference_lengths.values()),preset=preset,threads=mapper_threads)
                pending[future] = (parent_number, window_number)
                if threads == 1: consume()  # Owner planning cannot overlap the one granted mapper CPU.
            if number%100 == 0:
                print(f"LGZ q0 candidate regions: eligible_parents_completed={number} requested_parents={report['requested_parents']} completed={len(tasks)} fallback={report['fallback_parents']}",flush=True)
        while pending: consume()
    report.update(execution.report)
    report["completed_regional_tasks"] = len(tasks)
    report["weak_only_parent_ids"].sort(key=parent_order.__getitem__)
    native_groups = list(fallback.values())
    for item in native_groups:
        item["query_ids"].sort(key=parent_order.__getitem__)
        item["regional_fallback"].sort(key=lambda row:parent_order[row["query"]])
    native_groups.sort(key=lambda item:min(parent_order[key] for key in item["query_ids"]))
    return [task for _ordinal, task in sorted(tasks, key=lambda row:row[0])], native_groups, report
