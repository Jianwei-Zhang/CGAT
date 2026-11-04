# Official tel / cen library v1

Curated on 2026-11-04. All records are centromere-related or telomere-like
sequence evidence, not proof of a functional locus or universal species coverage.
The running workflow never downloads library data. Future curation changes the
official `library/` only; user data belong in `local/library/`.

## Telomere motifs

Only short motif facts are included, with literature attribution in `tel.tsv`.
No TeloBase database export, annotations or sequence collection is redistributed.
The cited primary abstracts were checked through Europe PMC on the curation date.
The reported plant strand CCCTAAA is reverse-complement equivalent to TTTAGGG;
GPM scans both strands automatically.

`min_repeat=5` is GPM's sensitivity policy, not a threshold derived from those
papers and not sufficient on its own to claim a complete functional telomere.
GRT retains the 2,000-bp terminal search window and >=500-bp donor requirement.
Adding the TTAGG family expands the old default motif coverage intentionally.

## Centromere-related sequences

Sequences are pinned public INSDC records retrieved from ENA. `cen/sources.json`
records accession.version, the exact 1-based inclusive extraction range, length,
source sequence MD5, source-record SHA-256 and distributed FASTA SHA-256. The
sequence parsed from each retrieved EMBL record was checked against that record's
length and MD5 before extraction. Nothing is synthesized or called a consensus.

| Entry | Record | Extracted coordinates | bp | Sequence source |
| --- | --- | --- | ---: | --- |
| Arabidopsis CEN180 / At178 | EU359509.1 | 181–358 | 178 | Zhang et al. 2008, DOI:10.1105/tpc.107.057083 |
| Rice CentO / RCS2 | AF058902.1 | 160–314 | 155 | Dong et al. 1998, DOI:10.1073/pnas.95.14.8135 |
| Maize CentC-154b | AF078919.1 | 1–154 | 154 | Ananiev et al. 1998, DOI:10.1073/pnas.95.22.13073 |
| Human alpha-satellite alpha-R1-9 | X13647.1 | 1–171 | 171 | Jorgensen et al. 1986, DOI:10.1016/0022-2836(86)90227-5 |

The Arabidopsis and rice inputs are representative repeat-length windows inside
annotated tandem arrays, **not independently annotated monomer boundaries**.
The maize record is a genuine 154-bp variant, not a 156-bp consensus. The human
input represents one alpha-satellite subfamily, not every human chromosome.

Family-level biological evidence is separate from sequence identity/provenance:

- Arabidopsis: Zhang et al. 2008, DOI:10.1105/tpc.107.057083, and Naish et al.
  2021, DOI:10.1126/science.abi7489 (CENH3-associated CEN180 chromatin).
- Rice: Cheng et al. 2002, DOI:10.1105/tpc.003079 (CentO centromere localization,
  spindle attachment and misdivision mapping; not described here as CENH3 ChIP).
- Maize: Zhong et al. 2002, DOI:10.1105/tpc.006106 (CentC association with CENH3).
- Human: Altemose et al. 2022, DOI:10.1126/science.abl4178 (alpha-satellite arrays
  and CENP-A context). This does not establish that every alpha-satellite copy,
  or the particular historic clone above, is functional centromeric chromatin.

## Public-data terms and scope

The INSDC policy provides free access and exchange of public sequence records
without INSDC use restrictions or licensing fees. ENA records, rather than
copyrighted paper figures or article text, supply these sequences. This is not a
claim to resolve independent third-party patent or other rights; see the INSDC
policy and NCBI molecular-data disclaimer:

- https://www.insdc.org/policy/
- https://www.ebi.ac.uk/ena/browser/about/data-policies
- https://www.ncbi.nlm.nih.gov/home/about/policies/

To inspect an original sequence record, substitute the pinned accession.version
in `https://www.ebi.ac.uk/ena/browser/api/embl/<accession.version>`. For curation,
parse the complete record, check the recorded sequence MD5, take the recorded
inclusive range without changing bases, and compare `sequence_sha256` in the
manifest. The raw EMBL record hash captures the retrieved metadata snapshot;
metadata may change later without a sequence-version change.

## Acceptance boundary

This v1 curation verifies sequence identity and attribution, not detection
sensitivity/specificity. Real-genome MUMmer sensitivity, cross-species false
positives, runtime/memory, the provisional 200-bp merge gap and App rendering
remain subject to the user's unified review and tests before publication.
