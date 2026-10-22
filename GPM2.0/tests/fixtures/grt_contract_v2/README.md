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

## Four-dataset App smoke bundle

Build a disposable ZIP without changing the fixture (Python standard library):

```sh
python3 GPM2.0/tests/fixtures/grt_contract_v2/build_four_dataset_bundle.py /path/to/new/four-datasets.zip
```

The ZIP contains one primary dataset (`primary`) and three supports (`support`,
`support2`, `support3`). All three supports have FASTA/FAI and source/role metadata,
but no chromosome assignments. Their absence from a chromosome track is expected;
the project catalog and Assembly support selector must still retain all three.
The locked recipe explicitly binds all three supports. The output is deterministic
and existing output files are never overwritten. This tiny synthetic fixture is
not a biological correctness or large-package performance test.

For an actual Windows Debug App check, start a **test-owned** native instance with
a new `WEBVIEW2_USER_DATA_FOLDER`, the current frontend, and a dedicated loopback
CDP port (window `additionalBrowserArgs`: `--remote-debugging-port=18745`). Do not
attach to a user's running App/profile. With Windows Node 22+:

```powershell
& D:\tools\nodejs\node.exe GPM2.0\tests\fixtures\grt_contract_v2\four_dataset_native_smoke.mjs 18745 D:\QA\four-datasets.zip D:\QA\new-workspace D:\QA\evidence
```

The dependency-free CDP runner requires a previously nonexistent workspace and an
empty App session. It submits the normal import form through native Tauri (no
mocked data), asserts catalog roles, queries actual initializer data, switches all
three support options, reloads the page, and writes a JSON report and screenshots.
The runner does not launch or terminate any process; close only the test-owned App
after checking the evidence, leaving the user's App and dev server untouched.
