# steltic_openBIM

Drawing and IFC module planned for Steltic Hub. The first release targets dimensioned engineering design drawings and IFC export. Fabrication/shop output and architectural IFC import follow later.

## Current status

Stage 2 implements **HR/CFS physical-data export, legacy-job replay and an engine-independent consumer**. All **61 supplied gold-standard buildings (36 HR, 25 CFS)** exported successfully, with all 812 audited source files unchanged. Their unresolved physical details remain explicitly flagged. New source-module design jobs require physical declarations before completion.

- [Stage 2 results, limitations and validation](docs/stage2/README.md)
- [All 61 replay packages](docs/stage2/bim_packages.zip)
- [Physical-data contract](contracts/BIM_EXPORT.md)
- [Coverage of every building](docs/stage2/data/building_coverage.csv)

The drawing renderer, IFC export and Hub integration follow this data stage. The original Stage 1 audit remains available:

- [Audit findings, scope and next tasks](docs/stage1/README.md)
- [Review workbook](docs/stage1/steltic_openBIM_stage1_audit.xlsx)
- [Building coverage matrix](docs/stage1/data/coverage_matrix.csv)
- [Missing-data and follow-up register](docs/stage1/data/missing_data_register.csv)
- [Machine-readable records and validation](docs/stage1/data/)

The register distinguishes extracting existing information, locating physical occurrences, checking geometry, supplying additional dimensions, and respecting delegated scope. An open review item does not necessarily mean the source data is absent.

## Integration principle

Consume a versioned physical-data package emitted by HR/CFS during a new job. Replay legacy jobs without analysis or redesign, keeping the supplied calculation packages immutable and recording missing data explicitly. The Stage 2 exporters are merged into HR and CFS main through [HR PR #95](https://github.com/Steltic/steltic/pull/95) and [CFS PR #45](https://github.com/Steltic/steltic_cfs/pull/45). Hub remains unchanged.

Install this repository with `pip install .`, then use `steltic-openbim validate path/to/bim_package.json`. The validator has no OpenSees or source-engine dependency. Consumers must recompute readiness; the package's stored status is informational.

The audit scripts in [tools/stage1](tools/stage1/) operate on supplied files without running job configurations or design engines. They are audit utilities, not a production drawing parser.
