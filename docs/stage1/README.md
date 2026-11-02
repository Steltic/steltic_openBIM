# Stage 1 — coverage and missing-data audit

Audit date: **2 November 2026**. Baseline: the supplied files under `C:\Users\mikea\drawings`. Acceptance scope: dimensioned engineering design drawings and IFC export; fabrication detail and architectural IFC import are deferred.

All 61 buildings have a coverage row and building-specific follow-up entries. Existing outputs provide substantial design information, but do not yet form a complete, located physical drawing model. Keep HR and CFS unchanged: first extract their existing data, then maintain reviewed drawing supplements outside those source packages.

## Deliverables and counts

| Module | Buildings | Connection records | Additional assembly / schedule records |
| --- | ---: | ---: | ---: |
| HR | 36 | 1,746 | 0 indexed separately |
| CFS | 25 | 332 | 2,785 |
| Total | **61** | **2,078** | **2,785** |

These are **source-record counts, not physical joint quantities**. Records can represent typical groups, a whole line or several stories. The connection index retains three explicitly waived records and 30 no-splice design notes. A no-splice note may contain other joint information, so it must not be discarded as a whole-record exclusion. CFS supporting tables can overlap the same physical system. HR non-connection tables were inspected as evidence but were not expanded into a second record index.

The [workbook](steltic_openBIM_stage1_audit.xlsx) contains six sheets:

- **Overview:** counts, definitions and first decisions.
- **Buildings:** all 61 buildings, geometry/profile/detail availability, source folder and follow-up IDs.
- **Missing data:** 386 follow-ups, evidence, recommended action, suggested resolver, and editable review status/resolution.
- **Families:** source-record coverage by an audit classification.
- **Connections:** all 2,078 connection records with source locators.
- **CFS assemblies:** all 2,785 selected supporting records.

Workbook excerpts are shortened for review. CSV/JSON retain longer evidence, exact source locators and affected-record keys. The original files remain the full authority. Workbook status edits do not rewrite the JSON baseline or resolve source geometry automatically.

| Register category | Items | Interpretation |
| --- | ---: | --- |
| Extract existing | 142 | Normalize or interpret information already present. |
| Resolve mapping | 61 | Associate design records with physical members, ends, levels and joints. |
| Verify geometry | 149 | Check linked evidence before concluding a parameter is absent. |
| Supplier / delegated | 26 | Obtain external data or preserve the stated scope boundary. |
| Supplement required | 2 | Reviewed examples need additional dimensions or a placement decision. |
| Scope decision | 4 | Choose representation of existing, host or excluded parts. |
| Verify source | 1 | Establish producer revision if configuration replay is needed. |
| Drawing decision | 1 | Establish common sheet and annotation conventions. |
| Total | **386** | Includes three shared items and 383 building-specific items. |

The two supplement entries are **not a claim that only two missing details remain**. The 149 geometry reviews and 26 external/delegated dependencies can reveal further supplements. Counts describe tasks, not individual missing dimensions. Resolver roles are suggestions, not assigned owners.

## What the existing outputs provide

**HR:** all 36 jobs include configuration, literal OpenSees/static model scripts, a viewer, a filled calculation package, member schedule, connection demands and a consistency result. All **27,683** analysis element tags match across the OpenSees model, viewer and member schedule. Connection dimensions and materials are largely in `components` prose; every HR connection record was indexed. Analysis nodes and element tags provide a strong starting point, but physical support faces, plate placement, actual splice elevations and occurrence-to-detail assignments still need resolution.

Physical reconstruction needs explicit handling for special cases. HR-9 SPSW strip-model diagonals represent wall action; they must not become physical braces. HR-27 composite wall/rigid-zone idealizations need physical wall assemblies. BRB core-area labels do not define casing geometry. Custom or built-up section names need source geometry, not substitution with arbitrary catalogue profiles.

**CFS:** all 25 jobs include configuration, filled calculation package, viewer and consistency results. No standalone `model_opensees.py` was supplied for these jobs. Fifteen wall-path viewers are schematic; ten use replicated portal geometry. The wall viewer explicitly distributes segments schematically, so viewer placement alone cannot establish real openings, wall extents or attachment locations. The portal viewer also has limits for secondary/end-wall framing.

The 332 CFS `connections[]` entries are only part of the drawing evidence. The index also includes anchorage, hold-downs, collectors, diaphragms, schedules, bases, chords, frames, framing, gravity framing, headers, joists, wall lines, studs, materials, segment framing and braced layouts. For example, **CFS-8 already supplies explicit braced-bay coordinate ranges for seven lines**; these need extraction and checking, not a request to invent new positions. Grouped wall records elsewhere still need occurrence expansion and source reconciliation.

**Source checks:** all 61 recorded consistency results are PASS, and the recorded package hashes match the supplied files. Those engineering consistency results were inherited, not rerun; they do not establish drawing completeness. Current repository revisions were inspected, but are not proof of which engine commit produced the supplied jobs.

## First supplement and scope decisions

| Register reference | Required resolution |
| --- | --- |
| `HR-22-12` | The roof shear-plate record supplies plate, bolt, edge and weld dimensions. Agree the plate's vertical datum and the beam-gap reference. The brief's prototype centered the plate on the flat web and derived a gap; preserve the designed dimensions while making those placement assumptions explicit. |
| `CFS-1-12` | The roof/header clip selections give material thickness or screw quantities but not the complete clip outline and screw layout. Locate an applicable project detail or supply a reviewed dimensioned clip detail. |
| BRB and other delegated entries | Extract existing end-detail data, then establish supplier casing/envelope and end-interface geometry, or retain a clearly identified design envelope and delegated reference. |
| Podium, existing-building, host and slab interfaces | Preserve source boundaries. Obtain the external package if those parts must be fully represented; otherwise identify the interface/context representation. Do not silently treat it as fully designed. |
| `ALL-03` | Set sheet sizes, scales, dimension precision, grid labels, title block and detail numbering once for openBIM. |

Each building's specific geometry case and next action are in the matrix. Stepped plans, split levels, transfer framing, trusses, wall openings, cranes, mezzanines, sloping portals and retrofit interfaces are retained as separate review cases rather than assumed to share rectangular-frame geometry.

## Recommended tasks before implementation

1. **Resolve source evidence.** Work through extraction and geometry-review entries, starting with the cited package fields and referenced schedules. Close a check only with an exact source or reviewed supplement; do not interpret a missing keyword as missing engineering data.
2. **Agree physical identity and location rules.** Define physical member/assembly/connection IDs and map source records to member ends, support faces, grid/line, story, orientation and handedness. Report ambiguous or unmatched occurrences. Keep analysis-only objects distinguishable from physical objects.
3. **Prepare an openBIM supplement contract.** Each supplement should identify building, source file hash, source record/JSON pointer, physical occurrence or explicit group scope, property and value, units, reference axes/datum, basis, reviewer and revision. Keep unknown values explicit. A changed source hash must trigger review of an attached supplement.
4. **Resolve scope and drawing conventions.** Decide the existing/podium/supplier boundaries and the shared sheet standard. Design drawings may reference delegated details; a physical IFC export still needs an agreed representation for them.
5. **Agree a staged implementation acceptance set.** Include ordinary HR framing, moment/braced and BRB systems, SPSW/composite-wall idealizations, wall-based CFS with openings, portals and a retrofit/interface case. Expand acceptance to all 61 rows and every connection family before claiming complete building coverage. Check physical occurrence coverage and dimension consistency, not only output-file creation.

The default approach needs **no HR/CFS changes**. If static output extraction cannot resolve a case, first add an openBIM-owned adapter or reviewed supplement. Configuration replay, if later needed, must use an identified source revision in the corresponding isolated engine environment. The inspected Hub architecture keeps HR and CFS in separate environments because they share top-level Python package names. Hub registration remains later work.

## Method, evidence and limitations

The audit inventories every supplied job, statically parses configuration syntax, reads literal model calls, reads viewer `DATA`, indexes every connection row and selected CFS supporting tables, and adds reviewed per-building notes. Source configurations, generated Python models, solvers and design engines were **not executed**.

The record index contains exact JSON pointers and a SHA-256 fingerprint of each full source row. Family labels are review aids based on type/ID wording; they do not approve a connection template or replace the original description. Fields named `mentions` report lexical matches, not a numerical geometry parser. Numerical field-path lists are discovery aids, not proof of complete geometry.

Register evidence references are relative to the building folder in `coverage_matrix`. `#/...` is a JSON pointer; `cfg.py:L...` is a source line; `viewer_3d.html#DATA/...` references embedded viewer data. `ALL-*` entries are shared requirements. Empty affected-record lists indicate a building-level or shared requirement; specific record lists are retained in JSON/CSV.

The independent [validation result](data/audit_validation.json) confirms counts, IDs, source pointers, per-record hashes, CSV/JSON agreement, family totals and source-file preservation. The original **812-file, 197,184,958-byte** manifest matches the final source scan. HR, CFS and Hub inspection checkouts are clean. Reference-library extracts in `rag/` and generated `figs/` are excluded from the manifest; complete job folders and reference-library text are not copied into this repository.

The exported [workbook validation](data/workbook_validation.json) independently reads the XLSX and verifies cached totals, all building/register/record IDs, source locators, scope labels, filters, frozen headers and status dropdowns. No Excel error cells were found. Rendered samples of every sheet were visually reviewed.

This is an availability and traceability audit, not a structural adequacy review or exhaustive numerical reconstruction of every detail. It does not certify any drawing for construction.

Inspected repositories (these are inspection revisions, not established producer revisions):

- [HR `f880ef4`](https://github.com/Steltic/steltic/tree/f880ef4396e620d1a24a355c19e9237b304570d9), especially `steel_engine/design_pipeline.py` and generated-output contracts.
- [CFS `2e93c55`](https://github.com/Steltic/steltic_cfs/tree/2e93c55fcf8ced44a3bbb211f61d48a14b300ad3), especially `steel_engine/cfs_pipeline.py` and `steel_engine/cfs_viewer3d.py`.
- [Hub `601b7da`](https://github.com/Steltic/steltic_hub/tree/601b7dac4bac459290675a1d3d856a2b7641fc9a), README environment and module-manifest architecture.

## Reproduce the data audit

From the openBIM repository root, with Python 3.10 or later and the same input folder layout:

```powershell
python tools/stage1/inspect_sources.py --root C:\Users\mikea\drawings --work-dir work/stage1
python tools/stage1/build_audit.py --work-dir work/stage1 --review-notes tools/stage1/review_notes.json
python tools/stage1/validate_audit.py --root C:\Users\mikea\drawings --work-dir work/stage1 --review-notes tools/stage1/review_notes.json
```

The first command creates a fresh initial manifest. Preserve that snapshot while doing an audit; do not regenerate it to hide source changes. Files are written only under the requested work directory. The scripts intentionally assert this 61-building baseline; future corpora require a reviewed update to the counts, notes and inspection revisions. JSON/CSV generation uses the Python standard library.

The optional `--repo-root` argument to validation accepts a parent containing inspection clones named `steltic`, `steltic_cfs`, and `steltic_hub` and checks their revisions and clean status. The committed validation includes those checks.

`build_workbook.mjs` uses the bundled `@oai/artifact-tool` authoring runtime. Where that dependency is available, run:

```powershell
node tools/stage1/build_workbook.mjs work/stage1/steltic_openBIM_stage1_audit.xlsx work/stage1/data/workbook_data.json
python tools/stage1/validate_workbook.py work/stage1/steltic_openBIM_stage1_audit.xlsx --data work/stage1/data
```

It creates a recalculated workbook and review renders under `work/stage1`. The checked-in workbook is a convenience view of the CSV/JSON baseline, not an additional engineering authority.

Runtime note: this Windows authoring runtime returned exit code 1 after reporting successful export, rendering all samples and reaching `COMPLETE`, without reporting an exception. The subsequent independent XLSX validation passed. Preserve this distinction when reproducing the workbook; a successful file validation does not establish that the authoring runtime exits cleanly.
