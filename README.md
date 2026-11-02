# steltic_openBIM

Drawing and IFC module planned for Steltic Hub. The first release targets dimensioned engineering design drawings and IFC export. Fabrication/shop output and architectural IFC import follow later.

## Current status

Stage 1 is a source-data audit of all **61 supplied gold-standard buildings: 36 HR and 25 CFS**. No drawing engine, IFC exporter or Hub integration has been implemented.

- [Audit findings, scope and next tasks](docs/stage1/README.md)
- [Review workbook](docs/stage1/steltic_openBIM_stage1_audit.xlsx)
- [Building coverage matrix](docs/stage1/data/coverage_matrix.csv)
- [Missing-data and follow-up register](docs/stage1/data/missing_data_register.csv)
- [Machine-readable records and validation](docs/stage1/data/)

The register distinguishes extracting existing information, locating physical occurrences, checking geometry, supplying additional dimensions, and respecting delegated scope. An open review item does not necessarily mean the source data is absent.

## Integration principle

Read existing HR/CFS outputs and keep drawing-specific supplements in this repository or an openBIM project workspace. Keep the supplied calculation packages immutable. Stage 1 changed neither upstream module nor Hub.

The audit scripts in [tools/stage1](tools/stage1/) operate on supplied files without running job configurations or design engines. They are audit utilities, not a production drawing parser.
