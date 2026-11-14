# CFS drawing and IFC delivery, with its self-check

A completed Steltic CFS job that carries a native physical model (the engine's `cfs_physical` builder, `physical_design` version 1) is delivered directly from that model: one drawing PDF, one IFC, and a certificate that the two agree with each other and with the design report. Nothing is redesigned, re-analysed or inferred; a value that is not in the calculation package is not drawn.

This path is separate from the HR delivery (`saved_delivery`, [hr-delivery-verification.md](hr-delivery-verification.md)). A package whose module is not `CFS` is refused, and no HR module imports the CFS delivery.

## Run it

```shell
python -m steltic_openbim.cfs_delivery --job-root JOB --output DELIVERY
```

`JOB` holds `report.html`, `design/calc_package_cfs.json` and the READY `design/bim_package.json` exported after the builder ran. The command writes `drawings.pdf`, `model.ifc`, `delivery_certificate.json` and the source and manifests they were made from, and exits non-zero unless every check passes. `--candidate-only` renders without the check, to diagnose a failure.

## What is drawn

Wall-path buildings: general notes and design basis, a framing plan for every level (wall lines, braced or sheathed segments, joist zones, posts and beams), an elevation of every wall line and post line, wall, tie-down, anchorage, stud, collector, diaphragm, framing and connection schedules, and a detail sheet for every assembly template. Portal-path buildings: base and bracing plan, roof framing plan, one elevation per frame type, side-wall and interior-line elevations, member, connection, anchorage, secondary and bracing schedules, and the typical details. Frame types include built-up channel portals, open canopies on box columns, existing shells shown as context, and cold-formed steel special bolted moment frames with hollow columns, bolted joints and beam splices.

## The ten checks

| Check | Compares | Example that must fail |
| --- | --- | --- |
| `source_binding` | Package readiness; fingerprints of the package, the drawings and the IFC; hashes of the job files the package was exported from; every design record against the job's calculation package | The calculation package edited after export; the IFC edited after delivery |
| `report_matches_design_records` | Every schedule record: the value printed in `report.html` against the record carried by the package | A demand/capacity ratio changed in the report only |
| `pdf_sheet_register` | Sheet numbers and titles read from each PDF page against the drawing register | A missing or re-ordered sheet |
| `pdf_schedules_match_design_records` | Every schedule row read from the PDF against the record it names and against the report value | A strap width on the schedule that differs from the record |
| `pdf_dimensions_match_model` | Level elevations, story heights, line spacings, segment set-out and frame dimensions read from the PDF against the model geometry | A wall line drawn 6 in. off |
| `ifc_members_match_model` | Every member: one IFC product, section label, material, and length, depth and width measured from its IFC mesh | A material renamed in the IFC; a member with the wrong profile |
| `ifc_panels_levels_grids_match_model` | Sheathing panels, storeys, grids and openings | A storey elevation changed |
| `ifc_connections_match_model` | Every located connection assembly: product, template, placement at its joint, design records | An assembly detached from its joint |
| `ifc_design_records_match_report` | Demand/capacity ratio and capacity of the records embedded in IFC products against the report rows | A record in the IFC that the report does not print |
| `drawings_match_ifc` | Counts printed on the drawings (member schedule, elevations, braced-bay types, detail occurrences) against the products counted in the IFC | A schedule that says 58 columns over a model with 57 |

Printed values must be identical strings at the printed resolution; read-back geometry is held to 0.02 in. The certificate states its scope: agreement of the delivered drawings, IFC and report with one another and with the calculation records. It is not a structural design check.

## Composite projects

Two structures behind a seismic joint are two CFS jobs bound by the engine's `cfs_composite` (`PROJECT/design/composite.json`: parts, plan set-out, interface). One command delivers the project:

```shell
python -m steltic_openbim.cfs_composite --job-root PROJECT --jobs-dir JOBS --output DELIVERY
```

Each part is delivered and certified on its own under `parts/<id>/`. The project `drawings.pdf` is a project sheet G-000 (composition, key plan, clear gaps, sheet index) followed by every sheet of every part, stamped with its part and project page. The project `model.ifc` is one IfcProject with one building per part at its set-out; every product carries the property set `Steltic_Composite` naming its part.

The composite certificate adds five checks. They do not repeat the part checks; they show that binding changed nothing and that the joint in the report is the joint in the model.

| Check | Compares | Example that must fail |
| --- | --- | --- |
| `parts_certified` | Every part certificate passed, for the very report, calculation package and physical package the project report was built from | A part report edited after binding |
| `report_contains_parts` | The project report holds every part report in full, the composition table and the clear-gap table | A part dropped from the project report |
| `drawings_contain_parts` | Every part sheet in the project set unchanged, stamped, and listed in the sheet index | A sheet missing from the project set |
| `model_contains_parts` | Every part product once in the project IFC: class, properties, materials, and position moved by exactly the part origin; nothing else added; one IfcProject; unique GlobalIds | A part placed at a different origin from the one declared; a product removed |
| `interface_matches_model` | Clear gaps measured between the parts in the model against the gaps stated in the report (to a quarter inch) and against the separation the interface record requires | Parts that overlap; a stated 18 in. gap over a modelled 12 in.; a gap below the required separation |

`tests/test_cfs_native_delivery.py` delivers a two-part project (special bolted moment frame shop with a free-standing strap-braced mezzanine) and then damages one artifact at a time; each damage must fail on the check that owns it.
