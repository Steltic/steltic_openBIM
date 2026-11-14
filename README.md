# steltic_openBIM

Version 0.8.108 delivers fresh native HR jobs that use the whole physical contract. A connection is located by its joint when it carries no `point` copy, box and cylinder connection parts are measured in the IFC like mesh parts, and a brace slot whose end is written to nine decimals no longer skews the member end. An unreadable column base is reported as its own finding beside the findings of the other connections. The CFS delivery is unchanged. [HR delivery verification](docs/hr-delivery-verification.md)

Version 0.8.107 adds the native CFS delivery: a completed Steltic CFS job that carries the engine's native physical model is delivered as one drawing PDF and one IFC with a ten-check certificate that the drawings, the IFC and the design report agree with one another and with the calculation records. Wall-path buildings, portal frames, open canopies, existing-shell component designs, platforms on posts and cold-formed steel special bolted moment frames are covered, and two structures behind a seismic joint are delivered as one composite project with five further checks on the binding and the joint. The HR delivery is unchanged and separate. [CFS delivery and self-check](docs/cfs-delivery-verification.md).

Version 0.8.39 corrects the registered gold-example connection geometry: source-selected brace crossings, exposed versus embedded bases, actual CFS strap receivers, member end releases, and located opening/floor attachments. It also retains outstanding findings when older pilot answers are adopted and compresses long drawing references without dropping any detail. These are physical-data and drawing corrections; full 61-building native acceptance and replacement PDF sets remain in progress. [Correction scope and audit](docs/drawing-review-corrections.md).

Version 0.8.32 keeps exported missing-data and geometry warnings visible on IFC import and reimport. A source panel completely consumed by its declared openings is retained as a labelled boundary reference, with no invented host surface, so it no longer blocks a provisional IFC return.

Drawing and IFC module for Steltic Hub: dimensioned engineering design drawings, IFC import for model review, and IFC export. Fabrication/shop output and IFC-to-structural-analysis conversion remain later work.

The historical [own-output audit](docs/own-outputs61/README.md) is superseded and excluded from current acceptance because the unfinished Hub/OpenRouter attempt is not reliable evidence. Current verification uses the original gold designs and explicit accepted engineer inputs; it makes no paid redesign calls. The old upstream fix list records that earlier checkpoint, not the current merge status.

## Current status

The [61-building gold IFC round-trip sweep](docs/gold-ifc61/README.md) passed for all 36 HR and 25 CFS buildings using local engine replay and saved designs, with no LLM calls, redesign or drawing runs. Every original IFC entity and every imported product’s geometry/data survived the exchange.

Version 0.8.31 verifies recorded HR/CFS source-file hashes before loading a new IFC source revision. Current physical-data findings remain visible alongside existing information requests and travel in the IFC as provisional source metadata. A valid IFC schema does not establish a complete source model. Existing accepted snapshots remain immutable and exportable.

Version 0.8.30 batches IFC geometry with a bounded native iterator while retaining every product's placement, opening cuts and fallback checks. Worker timeouts now terminate the complete owned process tree on Windows as well as other platforms. The existing model-size, triangle and time limits remain unchanged.

Version 0.8.29 preserves all saved HR/CFS design records in IFC, including anchorage and schedules without modelled solids, and retains complete connection-reference parameters. The import screen now states the existing 100,000-product processing limit correctly. [IFC workflow and limits](docs/ifc-workflow.md).

Version 0.8.1 adds an architectural IFC-to-HR brief handoff. Enter engineering requirements in IFC import, then download a source-referenced brief with the IFC grids, datums, floor/roof surfaces and opening locations for the existing HR design workflow. Three [fictional architectural video examples](docs/architect-video.md) include separately verified preliminary HR/OpenSees geometry builds.

Version 0.8.0 adds **Steltic import**, **IFC import** and **IFC export** tabs. IFC2x3, IFC4 and IFC4x3 imports retain their original files, ask scope/unit questions, and build an interactive 3D review with model-data findings. Export produces a validated IFC4 from the current drawing geometry, or retains an imported IFC with review notes. Known physical geometry, reference axes and unlocated connection metadata are distinguished explicitly. [Workflow, Revit exchange and limits](docs/ifc-workflow.md).

Version 0.7.1 checks occurrence geometry as well as analysis-ID coverage. Ordinary HR exports with grouped or missing physical occurrences can now produce a complete source-workline coordination set, with storey plans, grids, member marks, frame sections and non-blocking requests. Regenerating an existing job rechecks completeness while retaining answers and history. [Live-job recovery, limits and validation](docs/live-job-recovery.md).

Stage 8 produced the initial **61 fictional building sets (36 HR, 25 CFS)** with dimensioned A1 drawings and assembled connection details. The subsequent review identified geometry and source-selection defects; the correction audit above records the affected patterns. Final replacement sets remain pending the native completeness checks. [Initial final eighteen and reproduction](docs/stage8/README.md); [previous twenty](docs/stage7/README.md); [first 23](docs/stage6/README.md).

The shared Hub widget offers this development step only for the registered exact source packages, after explicit fictional-building confirmation. It never supplies fictional answers to ordinary jobs. `steltic-openbim design-test package.json --confirm-fictional --author "Test author" --output drawings` provides the same workflow from the CLI. Regeneration retains answers and revision history; reopening a request returns to provisional drawings. Source values are labelled S; authored fictional fit, layout and delegated geometry are labelled A. This does not rerun engineering or establish fabrication readiness.

Stage 4 starts the **provisional drawing workflow**: 54 A3 sheets across the HR hospital, CFS warehouse and CFS student housing. All 18 information requests have explicit proposals accepted for drawing by default. Proposed openings and unresolved interfaces appear as dashed symbols with `TBD - resolve query`; their dimensions stay hidden until quantitatively confirmed. [Workflow, example sets and validation](docs/stage4/README.md).

Hub integration mounts the same request widget inside User-designed building's Questions/Drawings flow and the standalone openBIM module. Confirmed opening answers regenerate a revisioned PDF set; notes alone retain TBD status. Source-engineering readiness and existing model/analysis checks stay separate. Structural/supplier decisions update geometry through a revised physical package.

The **Request register / answer queries** button opens the editable request form in the page. Raw data is available separately through **Download request data (JSON)**. Update/relaunch the openBIM module and refresh its tab to load the fix in an existing local Hub installation.

The [Stage 3 physical-model review pilots](docs/stage3/README.md) remain source evidence, with their dimensioned development recorded in [Stage 5](docs/stage5/README.md). Authored review recipes are bound to supplied source revisions; they are not a general converter for arbitrary buildings. Stage 4 supersedes Stage 3's drawing hold policy. Wider automatic connection detailing remains subsequent work.

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
