# Recovery validation progress — 2026-10-30

**In progress: not yet merge/delivery acceptance.** The user lifted the earlier
implementation-only test hold. These are real executions, not deferred test
definitions. Formal recovered-output publication is still closed at this checkpoint.

## Completed checks

- 326 tests passed, no skips, with the exact pinned binary, a built companion and
  the independent unmodified-source oracle explicitly enabled. Fixed stale
  guidance mocks, the native-oracle HAVE_KALLOC build definition, and a real
  resume guard bug that treated the executable and option values as workspace
  files. Reused the main-branch plan/input provenance test correction.
- All 9 native controls match ordered core/CIGAR, NM/nn/ms/cm/s1/s2/tp/rl/zd
  contracts; repeated with the legacy-ABI companion. AS is not reconstructed or
  compared. This is not an arbitrary whole-query DP equivalence certificate.
- 20 additional fixed-seed 160 kb stress controls match the same contract,
  including reverse orientation, near repeats/duplicates, boundary SNPs and indels.
- All 10 GRT/Final Path fixture comparisons pass scientific projection and path
  checks, including actual accepted forward/reverse donor repairs. Generated
  run/trace metadata are intentionally not claimed byte-identical.
- A real 270,000,000 bp reference and mixed complete forward/reverse long,
  ordinary and N-only queries trigger the exact original SIGABRT, independently
  reproduce it on both long singletons, and complete the actual selective
  50 Mb/100 kb recovery path. Long geometry/CIGAR/statistics, private MAPQ 60,
  public unknown MAPQ 255, ordinary native bytes and all four cells match the
  analytic simple-identity contract. Only the redundant first-part root is reused.
- The portable companion is compiled against an explicit 2.17 sysroot, with
  static zlib and its unmodified license/header retained. Its measured maximum
  GLIBC symbol requirement is 2.14, with no RPATH or libz dependency. Forty
  native producer/selector protocols are byte-identical on the host and in an
  actual isolated CentOS 7 / glibc 2.17 container, including long numeric states.

Pinned minimap2: `2.31-r1302`, SHA-256
`b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`.
Unmodified upstream library commit:
`3c28777e7e2dcc90f825de1b9f17a89cca7d4452`.
No installed minimap2 source or binary was modified or replaced.

## Remaining acceptance work

- Actual default multipart (>8 Gb) integration; a one-thread bounded local
  control is in progress. Two-thread attempts under an explicit 12 GiB
  address-space cap stopped before the target assertion: one logged insufficient
  memory and another exited SIGSEGV without attribution. These non-target
  failures correctly did not enter recovery and are not passing receipts.
- Complete the per-result publication/confidence admission contract, followed
  by real packaged run.sh success, non-target failure, cancellation, resume,
  checkpoint/no-clobber and rollback acceptance. Do not merely flip a flag.
- Freeze/retest the final source and actual customer artifact; verify main-branch
  merge compatibility and required quality gates. No master/Release update yet.
- Customer original FASTA/PAF were not supplied. Customer logs already establish
  independent single-record reproduction, but not the exact overflowing original
  operation or acceptance of the repaired complete customer workflow.

## Retained evidence

Raw local evidence is retained under
`/tmp/cgat-merge-readiness-20261030-2uXTWv/`. The reports carry their tested source,
input, command, tool and helper identities. Later source changes must not be
misattributed to these checkpoint receipts.

| Evidence | SHA-256 |
| --- | --- |
| `unit-legacy.log` | `6364c62d14d36b656345a96be91ef34b0a5f9145493480f0db1f72ecee45790b` |
| `native-controls/native-controls.json` | `a0572632b2101ae0662bab021a32845b2589c9dd1999597511f9471a08bd29ab` |
| `legacy-native-controls/native-controls.json` | `f21854d696aa9fd7e1b84c9c3a878b6ecd893d8eb8ace23303c340656bd93450` |
| `real-long/long-identity.json` | `6be994263dc6e5ba6afabc92bd15a97cb70913b292cd03d36cd52d7c389feea8` |
| `grt-controls-fixed-env/comparison.json` | `ae92a48177ffedcc62a4537619940153f3d8a37960fe24815f84c6aa1cb4f31c` |
| `stress/summary.json` | `9d07cd593711dbc4f995204fe447861a0f139dd383fa9c25cb19a831ae4eb18d` |
| `legacy-runtime.json` | `49fbbebb8851dcc50d13617c94ac6165e95ff0fa3576ae9b3027e73813eaee17` |
