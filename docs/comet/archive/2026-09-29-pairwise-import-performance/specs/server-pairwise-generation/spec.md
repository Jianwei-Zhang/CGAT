# Server pairwise generation

## Track-partition contract

A Server self-run represents alignments between different contigs assigned to the same chromosome partition and dataset track. Same-contig internal alignments are outside the current App pairwise evidence contract.

For each chromosome and dataset track, Server determines the selected contig count before scheduling alignment work:

- Fewer than two selected contigs: no `*_vs_self` task is scheduled and no self-run PAF is required.
- Two or more selected contigs: Server computes every required unordered pair of different contigs once.

The optimization does not remove cross-dataset runs or relationships between different contigs in primary or support datasets.

## Canonical artifacts

Server may use deterministic temporary identifiers or role-specific FASTA inputs internally, but the published `result.paf` contains original contig names. Query and target coordinate conventions, strand, match length, alignment length, MAPQ, optional tags, and CIGAR semantics remain compatible with existing consumers.

The canonical PAF is written atomically before hashes, checkpoints, evidence metadata, reports, Full packages, or Light packages consume it. Temporary inputs and identifiers are not delivered to the App.

## Compatibility

Existing minimap presets, biological thresholds, chromosome assignments, dataset ordering, and primary/support roles remain unchanged. Existing workspaces remain readable; newly prepared or rerun workspaces use the optimized self-run contract.

### Scenario: Skip a track partition with one contig

Given a chromosome partition in which a dataset track contains one selected contig, when Server prepares alignment tasks, then it does not schedule that track's `*_vs_self` task and the absence is treated as a valid no-pair condition.

### Scenario: Preserve auxiliary-track internal relationships

Given an auxiliary dataset track with multiple contigs in one chromosome partition, when Server runs its self alignment, then every required relationship between different contigs is present exactly once and no same-contig or reverse-duplicate pair is published.

### Scenario: Publish canonical names and evidence

Given Server uses temporary alignment identifiers internally, when the self-run completes, then the final PAF and every downstream hash, checkpoint, report, evidence reference, Full package, and Light package use the restored original contig names and canonical artifact.

### Scenario: Preserve cross-contig alignment semantics

Given the legacy self-run output and the optimized output for the same multi-contig fixture, when legacy same-contig and reverse-duplicate rows are normalized away, then the remaining cross-contig records are equivalent in names, coordinates, strand, MAPQ, alignment metrics, and CIGAR semantics.
