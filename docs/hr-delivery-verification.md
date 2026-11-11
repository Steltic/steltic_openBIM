# HR drawing and IFC delivery verification

The check covers the transfer from a completed USA HR job to the drawing PDF and IFC. HR's selected sections, materials, dimensions, connection types and explicit attachment requirements form the reference. openBIM completes unspecified fit and plate outlines against the actual members at each occurrence. This procedure uses the completed HR analysis and calculations as inputs.

## Run the check

For a saved job, use its original job directory, accepted native BIM package, decision archive and approved drawing model. Write each attempt to a new output directory.

```shell
python -m steel_engine.saved_handoff --job JOB --native ORIGINAL_BIM --decisions DECISIONS --output HANDOFF
python -m steltic_openbim.saved_delivery --handoff HANDOFF --original-native ORIGINAL_BIM --drawing-model DRAWING_MODEL --job-root JOB --output DELIVERY
```

The first command runs in the HR environment. The second runs in the openBIM environment and writes the artifacts and their detached verification evidence. A candidate-only render can be used to diagnose a failure. The final drawing-source export in the Hub runs the verification as part of the export.

For a new HR design revision, export its newly selected physical members, joints, attachments, approved architectural openings and source evidence. Use that revision's own job directory to verify its report. This command builds its framing plans, elevations and connection sheets directly from the new handoff.

```shell
python -m steltic_openbim.saved_delivery --handoff NEW_HANDOFF --native-revision --job-root NEW_JOB --output DELIVERY
```

A connection-only redesign can retain an approved drawing layout. Supply `--approved-layout DRAWING_MODEL --prior-native ORIGINAL_BIM` with `--native-revision`. The comparison checks the member worklines, joint locations, panel boundaries and opening polygons against the original. It records specifically revised crossing bars, newly added details and the retained sheet numbers in `retained_layout.json`.

## Required comparisons

| Comparison | Evidence that the check must read | Examples that must fail |
| --- | --- | --- |
| Saved HR design and report | Original job bytes, consistency result, selected connection rows, report appendix under each record's own heading, material table and member sections | Different grade or section, moved component description, stale calculation or original report |
| HR to openBIM | Exact record and field, owning member, story, end, applicability, accepted field-specific decision, selected value and unit | One bolt substituted for seven, collector detail applied to an unrelated beam end, pin used for a bolted BRB |
| Drawing PDF | Sheet title and number, actual text and vector operators after page transforms, crop, witness points, extension lines, ticks, projected geometry, part and weld legends | Correct label on a short dimension line, missing gusset, filled hole, displaced outline, altered weld size |
| IFC members and panels | Actual IFC units, composed placement, numeric mesh faces and connectivity, section dimensions, host boundary, opening voids and material associations | Correct section label on a thicker web, translated brace body, filled opening, wrong per-part grade |
| IFC connections | Actual placed template, constituent ranges, physical engagement with both receivers, attachment paths and selected geometry | Detached pin, screw missing a ply, edge weld extending past a plate, stacked copies of the same gusset |
| Brace terminations and crossings | Positive-volume brace intersections with bound receiving members, usable contact with the intended gusset, slot width, pin bore and lap geometry | Brace entering a column, empty gap at the plate, undersized slot, selected direct weld length exceeding the finite contact edge |
| Revision and scope | Original report, producer and artifact hashes, job identity, sheet register and declared PDF detail exclusions | Swapped job, changed PDF after verification, excluded detail reported as checked on paper |

Use each reported occurrence ID, source pointer, sheet and IFC source identity to reproduce a finding. Shared representation maps can reuse validated topology. Each mapped occurrence still needs its own placement and receiver binding checked.

## Geometry and tolerances

Use the units declared in the IFC and express physical comparisons in inches. For the native tessellated outputs, the coordinate tolerance is 0.0001 in. The brace solid-intersection screen reports positive common volume above 0.000001 in³. Opposing faces may meet at zero volume. An intended attachment also needs independent contact or engagement evidence.

In PDF space, the vector dimension and text-anchor tolerance is 0.025 pt. The connection projection check uses a 0.01 pt boundary allowance for coordinate serialization. Display dimensions follow the stated drawing resolution. Check the underlying model values and witness geometry before applying display rounding. Compare grades, counts, roles and job identities exactly.

At a gusset, retain each HR-selected thickness, material, pin, bolt, weld and clearance. Measure the overlap or bore and the finite edge available for each attachment. When HR leaves the contour open, openBIM may change the contour or cutback to fit. If the original selections cannot fit together, identify the records, the limiting dimension and the affected occurrences in the review output.

## Completion and regression

Read `delivery_certificate.json` from the same revision as `drawings.pdf` and `model.ifc`. A passing certificate binds those bytes to the checked drawing source and original HR job. Route locatable discrepancies to the producer that owns the incorrect field or geometry. Repeat export and readback after a correction.

Record the exact occurrence scope for requested differences between representations. The saved HR27 and HR28 drawing sets have explicit detail exclusions. Their IFC coverage and their PDF coverage are reported separately.

For a release sweep, retain one result per job, including failures. Compare original reports and saved design input hashes after regeneration. Build public download archives from the output hashes that passed the release check. Keep candidate files and their findings available for jobs under review.
