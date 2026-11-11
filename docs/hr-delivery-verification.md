# HR drawing and IFC delivery verification

The check covers the transfer from a completed USA HR job to the drawing PDF and IFC. HR's selected sections, materials, dimensions, connection types and explicit attachment requirements form the reference. openBIM completes unspecified fit and plate outlines against the actual members at each occurrence. This procedure uses the completed HR analysis and calculations as inputs.

## Run the check

For a saved job, use its original job directory, accepted native BIM package, decision archive and approved drawing model. Write each attempt to a new output directory.

```shell
python -m steel_engine.saved_handoff --job JOB --native ORIGINAL_BIM --decisions DECISIONS --output HANDOFF
python -m steltic_openbim.saved_delivery --handoff HANDOFF --original-native ORIGINAL_BIM --drawing-model DRAWING_MODEL --job-root JOB --output DELIVERY
```

The first command runs in the HR environment. The second runs in the openBIM environment and writes the artifacts and their detached verification evidence. A candidate-only render can be used to diagnose a failure. The final drawing-source export in the Hub runs the verification as part of the export.

For a newly completed or authorized redesigned HR job, use its own issued report, numerical evidence and sealed physical package. Generate the openBIM pair with `python -m steltic_openbim.saved_delivery --native-revision --handoff NEW_NATIVE --job-root NEW_JOB --output DELIVERY`. For a connection-only revision, pass `--approved-layout ORIGINAL_DRAWING_MODEL --prior-native ORIGINAL_NATIVE` to carry the checked opening and sheet layout forward. A revised brace arrangement requires new framing views and a direct comparison with the captured analysis geometry.

## Required comparisons

| Comparison | Evidence that the check must read | Examples that must fail |
| --- | --- | --- |
| Saved HR design and report | Original job bytes, consistency result, selected connection rows, report appendix under each record's own heading, material table and member sections | Different grade or section, moved component description, stale calculation or original report |
| HR to openBIM | Exact record and field, owning member, story, end, applicability, accepted field-specific decision, selected value and unit | One bolt substituted for seven, collector detail applied to an unrelated beam end, pin used for a bolted BRB |
| Drawing PDF | Sheet title and number, actual text and vector operators after page transforms, crop, dimension witnesses and ticks, member axes on plans, clipped section edges, native connection projections, part and weld legends | Correct label on a short dimension line, a chevron in place of a single diagonal, missing gusset, filled hole, displaced outline, altered weld size |
| IFC members and panels | Actual IFC units, composed placement, numeric mesh faces and connectivity, section dimensions, host boundary, opening voids and material associations | Correct section label on a thicker web, translated brace body, filled opening, wrong per-part grade |
| IFC connections | Actual placed template, constituent ranges, physical engagement with both receivers, attachment paths and selected geometry | Detached pin, screw missing a ply, edge weld extending past a plate, stacked copies of the same gusset |
| Brace terminations and crossings | Positive-volume brace intersections with bound receiving members, usable contact with the intended gusset, slot width, pin bore and lap geometry | Brace entering a column, empty gap at the plate, undersized slot, selected direct weld length exceeding the finite contact edge |
| Revision and scope | Original report, producer and artifact hashes, job identity, sheet register and declared PDF detail exclusions | Swapped job, changed PDF after verification, excluded detail reported as checked on paper |

Use each reported occurrence ID, source pointer, sheet and IFC source identity to reproduce a finding. Shared representation maps can reuse validated topology. Each mapped occurrence still needs its own placement and receiver binding checked.

## Geometry and tolerances

Use the units declared in the IFC and express physical comparisons in inches. For the native tessellated outputs, the coordinate tolerance is 0.0001 in. The brace solid-intersection screen reports positive common volume above 0.000001 in³. Opposing faces may meet at zero volume. An intended attachment also needs independent contact or engagement evidence.

In PDF space, the vector dimension and text-anchor tolerance is 0.025 pt. The connection projection check uses a 0.01 pt boundary allowance for coordinate serialization. Display dimensions follow the stated drawing resolution. Check the underlying model values and witness geometry before applying display rounding. Compare grades, counts, roles and job identities exactly.

At a gusset, retain each HR-selected thickness, material, pin, bolt, weld and clearance. Measure the overlap or bore and the finite edge available for each attachment. When HR leaves the contour open, openBIM may change the contour or cutback to fit. If the original selections cannot fit together, identify the records, the limiting dimension and the affected occurrences in the review output.

For a selected straight fold line, take the brace workline from the joint into the brace. Measure from the foremost restrained gusset attachment to the nearest actual brace-end station along that workline. Compare the result with the selected multiple of measured plate thickness. Identify the finite column, base or beam welds that restrain the particular plate. Apply a free-edge or beam-only selection to its own end. The dimensional convention follows [ANSI/AISC 341-22, Commentary Figure C-F2.18(a)](https://www.aisc.org/globalassets/aisc/publications/standards/a341-22w.pdf).

For a reinforced slot with a length specified on each side of the cut, locate the inner tip of the actual slot and measure each weld segment from that tip. For a plated flat-bar crossing, locate the two uninterrupted bars and the plate at the selected workpoint. Check the actual front and back contact, bar assignment to each specified face, plate thickness, outline, grade and any selected in-plane orientation. Match each selected longitudinal fillet to a distinct IFC curve on its own bar edge and finite plate face. Check its length, size, consumable and station. Preserve individual crossing measurements in the certificate.

Measure an explicitly directional base-plate set-out in the located column frame, including both outer flange offsets, pitches and both edges in each direction. Compare each selected plate grade against its actual constituent material. A schedule covering several thickness-dependent grades needs a grade choice for each affected part.

Retain the numerical precision of the HR design. Where the archived calculation routine independently rounds two related dimensions for its report, reproduce the original numerical set-out and check each displayed dimension at its printed resolution. Record the source of the exact calculation inputs. A nominal edge allowance used to choose plate stock, a required minimum and the actual rod-to-edge distances after the stock was rounded up have different meanings. Keep them distinct in the design record. Measure specified through-holes from the actual plate section around each actual rod shaft.

Where HR specifies fillets on both gusset faces, locate one finite run on each face. Measure the full selected length on each side, including any segments on contiguous receiving members. At a slotted brace, measure an explicitly selected effective transfer width at the joint-side end of the welds. Compare the width with the actual available plate on the two sides of the workline and include adjacent material only where HR credits it. For an openBIM-fitted free outline, compare its material with the finite support edges, the slot weld extents, the adopted edge allowance and the selected transfer width.

Examine gussets across connection occurrences as well as within each assembly. If two arms share one plate, identify its one physical owner, trace the attachment paths from both arms and measure the complete plate. Separate actual plates occupying positive common volume are a finding. Link that finding to both connections and their detail sheets.

## Completion and regression

Read `delivery_certificate.json` from the same revision as `drawings.pdf` and `model.ifc`. A passing certificate binds those bytes to the checked drawing source and original HR job. Route locatable discrepancies to the producer that owns the incorrect field or geometry. Repeat export and readback after a correction.

Record the exact occurrence scope for requested differences between representations. The saved HR27 and HR28 drawing sets have explicit detail exclusions. Their IFC coverage and their PDF coverage are reported separately.

At a double-gusset transfer-truss joint, preserve through columns and compare the actual terminal cuts with the located receiving members. Trace each scheduled flange-tip fillet over its full length on the contact faces of both solids. Where HR selects a Whitmore width, measure the available centred plate section at the joint-side end of the weld group. Check the applicability of each support detail against its member section and workpoint.

For a supplier bolted BRB, identify the steel yielding core inside its casing. Read its material, constant cross-sectional area and continuous yielding length from the actual IFC. Compare the length with the HR ratio applied to that member's workpoint length. Locate each exposed core projection on the internal core end face and verify clearance to the casing throughout the represented region. Carry the HR supplier qualification and deformation requirements onto the drawings. NIST GCR 15-917-34, sections 2 and 3, describes the separate axial core and restraining mechanism and the constant-area yielding region. [NIST, *Seismic Design of Steel Buckling-Restrained Braced Frames*](https://www.govinfo.gov/content/pkg/GOVPUB-C13-f8c40a9c76d92e80947e8a05ec3b2e35/pdf/GOVPUB-C13-f8c40a9c76d92e80947e8a05ec3b2e35.pdf)

For a release sweep, retain one result per job, including failures. Compare original reports and saved design input hashes after regeneration. Build public download archives from the output hashes that passed the release check. Keep candidate files and their findings available for jobs under review.
