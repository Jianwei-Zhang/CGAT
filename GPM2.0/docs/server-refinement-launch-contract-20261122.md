# Refinement launch and resume contract

Date: 2026-11-22. Implements the approved public entrypoints, not a second scheduler.

- New `run.sh`/`prepare.sh` workspaces start in the numbered layout. Existing unmarked workspaces are not silently re-prepared or converted.
- `--hifi`, `--ont` and `--gapfill-tools` are downstream settings, not immutable LGZ preparation inputs. No typed refinement reads are converted into legacy `--reads` QC inputs.
- Reads supplied on a launch replace the saved typed-read selection as a whole; omitted technologies are empty. Omitting both flags reuses saved reads. Repeated/grouped flags preserve file order.
- Omitting tool selection reuses the saved choice; a new reads-backed task defaults to DEGAP. Explicit `none` disables refinement for this invocation and does not delete history or erase the saved choice.
- Stable configuration and each invocation request are separate, content-bound records under `.runtime/refinement/`. Settings are recorded before initial preparation so an interrupted launch can resume with only `-o`. Changing downstream settings cannot rewrite `metadata/prepare_options.tsv`, scientific freeze receipts or LGZ commands.
- The generated `refinement` plan unit runs after LGZ evidence finalization and before baseline packaging. It uses the same runner-owned process group and thread budget. It borrows the live parent's workspace lock only after checking PID/start identity, hostname and run ID; standalone calls acquire their own lock and spawn the same verified child boundary. Both paths forward interruption to the entire native process group and keep the lock until it stops.
- Individual native tools and their delivery publication remain failure-isolated. A failed refinement unit does not suppress validated successful tool deliveries or LGZ baseline packaging; the overall process still returns nonzero and does not claim full success.
- A zero-exit refinement unit additionally validates its current request/batch/publication receipts, the explicit LGZ baseline and content hashes of the overview/comparison reports. Exit code or directory presence alone is not completion.
- Completed valid LGZ-only workspaces can register downstream reads/tools without re-preparation. The normal LGZ/reference checkpoints remain authoritative and unchanged. Migration of genuinely old unmarked workspaces is an explicit separate operation.

Implementation checks remain targeted during development. The final A01–A18/native/environment matrix is not replaced by launch/config unit tests.

## Workspace entrypoints

For a newly prepared workspace, `--out` is the root of every scientific result and delivery, not the parent of scattered archive files:

```text
<out>/run_all.sh
<out>/05_final/00_lgz/                     # explicitly unrefined LGZ baseline
<out>/05_final/01_degap/                  # only after accepted DEGAP publication
<out>/06_report/report.html              # overview; links process, jobs, comparison and final sequence
<out>/06_report/01_lgz/report.html        # preserved LGZ process report
<out>/07_delivery/00_lgz/<full/light archives>
<out>/07_delivery/01_degap/<full/light archives>
<out>/.runtime/{prepared,commands,logs,metadata,run_all,refinement}/
```

The other numbered refinement directories are `02_tgsgapcloser`, `03_quartet`, and `04_lrgapcloser`; they are independent branches, not successive modifications of DEGAP output. No selected/successful refinement is implied by the presence of `00_lgz`.

```bash
# New run: typed reads enable default DEGAP after LGZ.
bash server/run.sh --ref reference.fa --ds assembly.fa --out /work/cgat_server --hifi hifi.fq.gz
# Completed numbered LGZ-only workspace: append refinement without re-preparation.
bash /work/cgat_server/run_all.sh --hifi hifi.fq.gz --ont ont.fq.gz
# Selected comparison branches, each starting from the same LGZ baseline.
bash /work/cgat_server/run_all.sh --gapfill-tools degap,tgsgapcloser,quartet,lrgapcloser
# Disable refinement for this invocation only; saved choice/history remain.
bash /work/cgat_server/run_all.sh --gapfill-tools none
```

These are the implemented launch contracts, not a claim of four-tool native or cross-architecture acceptance. A direct `prepare.sh --gapfill-tools none` records a disabled configuration, since preparation itself is not an execution invocation. Existing unmarked legacy workspaces still need the pending explicit migration adapter; do not run `prepare.sh` over them.
