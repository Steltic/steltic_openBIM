# All 61 supplied buildings

The final fifteen HR and three CFS buildings complete the supplied collection: **36 HR and 25 CFS design drawing sets**. The final batch adds 4,037 A1 sheets, bringing the collection to **12,929 sheets**. Each set contains grids, member marks, plans, sections, opening schedules and assembled connection details with elevation, cut section, isometric, parts, fasteners and weld/interface callouts.

## Final batch

| Cases | Distinct conditions developed |
|---|---|
| HR 1, 6 | Five/six-level SCBF; embedded bases, brace apexes, pins and column transitions |
| HR 2, 5, 7a | Nine/ten/seven-level SMF; end/interior joints, gravity joints and level-specific source variants |
| HR 3 | Braced/moment building; continuous cellar columns and explicit adopted footing datum |
| HR 4 | Three-level BRBF and library stack-zone infill |
| HR 15 | Twenty-level wedding-cake footprint, terrace framing and terminating columns |
| HR 17 | Offset core, asymmetric upper floor, diaphragm and collector transfer |
| HR 19 | Continuous 90 ft plate girder, column pickups, sliding seats and separate stud/hairpin collars |
| HR 23, 29 | Near-fault emergency building and twenty-level performance-based source design |
| HR 26 | Slender eighteen-level dual frame and source roof damper supports |
| HR 34a, 34b | Two towers, common podium and separate upper floors with a source 19 in clear joint |
| CFS 1 | Four-level shear walls, shorter corridor joists and source header clips |
| CFS 5 | Six-level strap walls, individual physical bays, end-only hold-downs on continuous runs |
| CFS 15 | Six/four-level stepped hotel, lower gabled roof, drag/blocking interfaces, corridor slip clips and terrace guards |

Exact source names and hashes are retained in [selection.json](selection.json).

## Source and adopted answers

**S** identifies original source design data; **A** identifies user-authorized fictional answers, local fit, missing positions or delegated geometry. Source grades, sections, fastener counts and special connection conditions remain traceable. The original jobs and calculation records are unchanged; no design engine or OpenSees analysis is run by the drawing workflow.

The HR 19 sliding-bearing envelope, collar-stud size/set-out and hairpin fit remain explicit authored geometry where the source does not specify them. The twin towers retain the source joint width and supplier movement requirements; their local coordinate systems remain separate. CFS roof-truss internals, blocking-panel outlines, vertical-slot travel and local clips are authored supplier coordination geometry. Original capacity, foundation, seismic and supplier verification requirements still apply. These are dimensioned design review sets, not fabrication instructions or a construction issue.

All final-batch source connection schedules are linked to physical members or assembled details. Continuous-member instructions do not create extra splices. The earlier batches retain their recorded applicability exceptions; their delivered PDFs are preserved in the combined archive.

## Editable request register

The primary **Request register / answer queries** action opens the editable form in the drawing page and expands the first unresolved request. **Download request data (JSON)** is a separate export. The fix was merged first in [openBIM PR 6](https://github.com/Steltic/steltic_openBIM/pull/6) and [Hub PR 12](https://github.com/Steltic/steltic_hub/pull/12).

Update/relaunch openBIM and refresh its tab in an existing local Hub installation. Update User-designed building too when using its embedded drawing page. Existing answers and revisions are retained. Ordinary jobs still use accepted provisional proposals with TBD dimensions until quantitatively resolved; the fictional review recipes are available only for exact registered source hashes with explicit fictional-building confirmation.

## Reproduce

Install `.[drawings]`, then run:

```powershell
python tools/generate_review_batch.py --confirm-fictional --author "User-authorized fictional review inputs" --output review --cases hr1 hr2 hr3 hr4 hr5 hr6 hr7a hr15 hr17 hr19 hr23 hr26 hr29 hr34a hr34b cfs1 cfs5 cfs15
```

Omit `--cases` for all 61. Fifty-eight frozen additional cases ship in `review_data/inputs.zip`; the original three pilot sources remain in `docs/stage3/pilots.zip`. The installed CLI and Hub widget expose the same exact-source recipes. This completed review catalog is not a general automatic detailing engine for arbitrary buildings; IFC export remains subsequent work.

## Verification and delivery

[verification.json](verification.json) records PDF/model/source/answer hashes, member counts, connection coverage and source applicability. All 812 audited files across the original 61 jobs are unchanged.

[visual_review.json](visual_review.json) records exact PDF hashes and the inspection extent. Every final page is rendered at 900 px. Selected plans, sections, schedules and connection families/subtypes are checked on contact sheets, with a larger plan and complex-joint sample per building and extra checks for the new transfer and roof interfaces. This is sampled visual inspection, not full-size inspection of every page or structural approval.

The combined delivery ZIP contains **exactly 61 PDFs**, one complete set per building, with no JSON, model files or wheel inside. The drawing module wheel is provided separately. Archive CRC, every contained PDF hash, page counts, offline-index links and JavaScript syntax are checked in the delivery record.

[delivery_verification.json](delivery_verification.json) records the 222,937,299-byte PDF archive, the separate 0.7.0 wheel and their SHA-256 hashes. Validation passed: 157 openBIM tests, 21 focused final-case/assembly checks and 5 Hub drawing integration tests, including HR 19 adoption and regeneration. Final annotation adjustments were checked by regenerating and rendering the affected sets and inspecting the changed samples.
