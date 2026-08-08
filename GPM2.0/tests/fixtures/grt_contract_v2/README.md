# GRT contract v2 fixtures

`valid/gpm_server/` is the smallest complete package accepted by
`server/tools/grt_contract.py`. It deliberately contains:

- one primary source segment;
- one originally-unplaced donor promoted by an accepted Step1 event;
- one fixed ordinary donor set and one independent telomere donor set;
- canonical GRT evidence plus a display-pairwise evidence row;
- all q/checkpoint transitions through q4;
- a Final Path that reconstructs q4 exactly.

`invalid_cases.json` describes deterministic mutations applied to a temporary
copy of the valid package. The mutation format is intentionally language-neutral
so the same cases can be reused by the later Rust importer tests.

This fixture family only represents `gpm_grt_precomputed_v2`. The former v1
workflow and package schema are unsupported by design.
