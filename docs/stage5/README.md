# Dimensioned design drawing pilots

The hospital, warehouse and student-housing sets now have dimensioned grids, member marks, sections, opening set-out and connection callouts. The user expressly authorized sensible invented answers because these are fictional test buildings. All 18 outstanding requests have adopted answers on G002 and in each `adopted_answers.json`.

[Download the three drawing sets and model indices](three_design_drawing_sets.zip). [Verification](verification.json).

## What is drawn

- Hospital: six framing plans, column-base grid, two physical sections, openings and their W18X40 frames, embedded-base stud arrangement, RBS/other connection details and source joint variants.
- Warehouse: frame/base grid, roof/bracing plan, portal/end-wall/side-wall views, personnel and overhead door schedules, channel/clear-span reconciliation, primary bracket and secondary connection details.
- Housing: three elevated floor plans, four wall-framing plans, roof truss/valley layout, building/wall/walkway sections, openings and their frames, walkway support/pad geometry and source connection variants.

Geometry is in inches; the PDF uses feet and fractional inches, with local details in inches. A1 landscape sheets state their actual print scales. Member marks group identical types/profiles/workline lengths/basis/joint references. `member_index.json` locates every individual instance; these lengths are not fabrication cut lengths.

`design_model.json` contains the supplemented drawing model, exact source IDs, trimmed members, adopted assumptions, per-instance connection references and representative detail parameters. `source_records.json` preserves the complete original engineering records. The source HR/CFS `bim_package.json` remains untouched and retains its original engineering-readiness status.

## Assumptions and scope

S denotes a source input. A denotes an authored fictional test input. Openings physically interrupt affected secondary members and receive supplementary headers/trimmers/jambs. They avoid the source braced bays. Floor datums and selected interfaces are reconciled explicitly; source dimensions/fastener counts remain in the printed variant schedules.

These are design drawing test sets, not construction or fabrication issues. The added opening frames, roof internals, walkway supports/pads/guards and changed connection layouts have no new capacity verification. The three scenarios are tied to the exact published Stage 3 package fingerprints. They do not authorize automatic assumptions for other buildings. Source-delegated work beyond the illustrated structural scope, such as complete foundations and architectural stair assemblies, remains outside this drawing-development release. IFC export and broader building-family support follow separately.

## Hub and reproducibility

The same widget works in Hub's Questions/Drawings page and in the standalone openBIM module. An eligible pilot exposes **Develop test design drawings** with a fictional-building checkbox and author field. Ordinary jobs retain non-blocking provisional requests and hidden TBD dimensions.

Adoption publishes a new revision atomically. Regeneration retains the adopted answers. Editing an opening retains A provenance and updates its geometry/register. Reopening any request returns the drawing set to provisional mode. Re-adopting the authored scenario resets its test answers explicitly; a changed physical source starts a fresh provisional state.

```powershell
pip install ".[hub]"
steltic-openbim design-test path/to/bim_package.json --confirm-fictional --author "Test author" --output drawings
python -m pytest -q
```

Acceptance tests use the published immutable source packages in `docs/stage3/pilots.zip`. They check source binding, explicit consent, opening interruptions, bracing clearance, datum consistency, mark/reference coverage, printed scales/dimensions, source variants, and revision/API behavior. The delivered PDFs are also rendered and visually checked page by page. The 61-building/812-file gold source audit is repeated before publication.
