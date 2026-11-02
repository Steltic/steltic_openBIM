# steltic_openBIM

Drawing and IFC module for Steltic Hub. The first release targets dimensioned engineering design drawings and IFC export. Fabrication/shop output and architectural IFC import follow later.

## Current status

Stage 4 starts the **provisional drawing workflow**: 54 A3 sheets across the HR hospital, CFS warehouse and CFS student housing. All 18 information requests have explicit proposals accepted for drawing by default. Proposed openings and unresolved interfaces appear as dashed symbols with `TBD - resolve query`; their dimensions stay hidden until quantitatively confirmed. [Workflow, example sets and validation](docs/stage4/README.md).

Hub integration mounts the same request widget inside User-designed building's Questions/Drawings flow and the standalone openBIM module. Confirmed opening answers regenerate a revisioned PDF set; notes alone retain TBD status. Source-engineering readiness and existing model/analysis checks stay separate. Structural/supplier decisions update geometry through a revised physical package.

The [Stage 3 physical-model review pilots](docs/stage3/README.md) remain the source evidence. Their recipes and authored proposal layouts are bound to the three supplied source revisions; they are not a general converter for the other 58 buildings. Stage 4 supersedes Stage 3's drawing hold policy. Wider automatic detailing and IFC export remain subsequent work.

Stage 2 implements **HR/CFS physical-data export, legacy-job replay and an engine-independent consumer**. All **61 supplied gold-standard buildings (36 HR, 25 CFS)** exported successfully, with all 812 audited source files unchanged. Their unresolved physical details remain explicitly flagged. New source-module design jobs require physical declarations before completion.

- [Stage 2 results, limitations and validation](docs/stage2/README.md)
- [All 61 replay packages](docs/stage2/bim_packages.zip)
- [Physical-data contract](contracts/BIM_EXPORT.md)
- [Coverage of every building](docs/stage2/data/building_coverage.csv)

The original Stage 1 audit remains available:

- [Audit findings, scope and next tasks](docs/stage1/README.md)
- [Review workbook](docs/stage1/steltic_openBIM_stage1_audit.xlsx)
- [Building coverage matrix](docs/stage1/data/coverage_matrix.csv)
- [Missing-data and follow-up register](docs/stage1/data/missing_data_register.csv)
- [Machine-readable records and validation](docs/stage1/data/)

The register distinguishes extracting existing information, locating physical occurrences, checking geometry, supplying additional dimensions, and respecting delegated scope. An open review item does not necessarily mean the source data is absent.

## Integration principle

Consume a versioned physical-data package emitted by HR/CFS during a new job. Replay legacy jobs without analysis or redesign, keeping the supplied calculation packages immutable and recording missing data explicitly. The Stage 2 exporters are merged into HR and CFS main through [HR PR #95](https://github.com/Steltic/steltic/pull/95) and [CFS PR #45](https://github.com/Steltic/steltic_cfs/pull/45). Stage 4 adds a companion Hub integration; HR/CFS are unchanged by this drawing work.

Install this repository with `pip install .`, then use `steltic-openbim validate path/to/bim_package.json`. The validator has no OpenSees or source-engine dependency. Consumers must recompute readiness; the package's stored status is informational.

Install `pip install ".[drawings]"` for `steltic-openbim draw path/to/bim_package.json --output drawings`. Install `pip install ".[hub]"` for the local API/UI and Hub module manifest. The drawing command accepts valid packages with open information requests, while invalid geometry is still rejected.

The audit scripts in [tools/stage1](tools/stage1/) operate on supplied files without running job configurations or design engines. They are audit utilities, not a production drawing parser.
