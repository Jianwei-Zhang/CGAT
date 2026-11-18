# Frozen q0 package-3 delivery fixture

`frozen_server.json` stores the exact UTF-8 bytes of the files needed by the full Server validator. Both Python and Windows-native Rust tests materialize the same files; Rust tests do not need an aligner, Python, or a regenerated q0.

The controlled source is `dna(2000)` from `test_q0_admission.py`, with a reverse reference placement on `chr1` and **no coarse chr assignment**. It was produced with the actual q0 publisher, Step1, Step2, Step3, telomere finalization and evidence packaging at Server revision `e201e2f`. Pre-q0 PAF geometry is explicitly synthetic; later stages used installed MUMmer4/minimap2. This is an import/contract fixture, not a biological accuracy benchmark.

It exercises a retained q0-only promoted source, an empty assignment table, no display comparison peer, and no invented accepted repair event. Source sequence, frozen availability, q0 evidence, q-stage files and checkpoint hashes remain intact. Historical tool paths/code fingerprints are facts in the frozen fixture, not executables to invoke or a requirement to have the identical installed selector.

To freeze a newly produced **controlled test** workspace, from `GPM2.0`:

```sh
PYTHONPATH=server/tests:. python3 -m server.tests.q0_delivery_fixture \
  --server-dir /path/to/controlled/gpm_server \
  --output tests/fixtures/grt_contract_v3/frozen_server.json \
  --provenance 'Describe the exact controlled input, generation revision, and real versus synthetic tools'
```

The freezer validates the original workspace and a relocated materialized copy before writing. Do not repair checksum strings, fabricate assignments/events, or include customer data to make a fixture pass. Preserve historical fixtures when adding new schema coverage.


Additional shared fixtures:

- `frozen_bridge_server.json`: reverse three-dataset bridge on chr1, with the coarse `c` display direction deliberately `+` while its retained slice is `-`; chr2 retains a scaffold's actual 137-N adjacency. Raw pre-q0 geometry is controlled and later stages ran real tools. Display order indices are derived from the supplied coarse assignments, not used to rank q0.
- `frozen_app_full.json` / `frozen_app_no_fasta.json`: actual schema-3 App projections of `frozen_server.json`. They intentionally omit q0/donor/raw audit artifacts, as required by the minimal App contract. The source/reference locators describe the supplied FASTA records; no assignment, ordering member or repair event is fabricated to populate an otherwise empty table.

The two App snapshots are also compared byte-for-byte with fresh projections by the Python test; Windows Rust validates/imports the same files. The no-FASTA test verifies metadata and source-coordinate integrity, not absent sequence bytes.


`frozen_direct_server.json` is the current schema-4 Server fixture. Its controlled
reverse-source input matches `frozen_server.json`. The current q0 publisher and
real MUMmer4/minimap2 Step1/Step2/Step3/evidence producers generate q0/q1/q2/q3;
there are no q0r1/q0f/q4 artifacts. Final q3 DNA equals historical q4 DNA.
Python and Windows Rust both validate it and reject mixed-version transitions.
Historical schema-2/3 fixtures remain unchanged. Stable Final Path `q4_*` fields
refer to the final artifact; schema 4 binds their path value to `grt/q/q3.fa`.

The retained-source historical reader tests use
`../grt_contract_v2/retained_source_bundle.json`, frozen from the validated
pre-renumbering builder at b79bcbefd757cc122bc5c661fc8574337af510db. Current
algorithms no longer manufacture old-numbered stage output for those tests.
