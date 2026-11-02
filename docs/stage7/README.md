# Second twenty buildings and 43-building review checkpoint

The next ten HR and ten CFS buildings have dimensioned A1 design drawings with assembled connections. Together with the three pilots and first twenty, the collection contains 43 buildings. This is the requested review checkpoint; no further buildings are included in this stage.

Each set includes grids, framing plans, sections, member marks, openings, source schedules and connection callouts. Each assembled joint variant has an elevation, a geometric cut section, an isometric, identified parts and fastener/weld interfaces. The member and connection indices locate every modelled occurrence and its applicable detail. Separate source variants retain their own records and dimensions.

## Selection

| HR case | Variety exercised |
|---|---|
| 14 | Hillside EBF, basement framing and differing base elevations |
| 16 | Three-wing school, stepped roofs, boxed columns and axis-specific SMF joints |
| 18 | Eight-level low-seismic frame, brace crossings and column transitions |
| 20 | Twelve-level discontinuous SCBF with transfer truss, slip interfaces and diaphragm transfer |
| 21 | Single-storey braced roof with joists and collectors |
| 24 | Ten-level mixed SMF X / SCBF Y, alternating corner and apex conditions |
| 25 | Twelve-level atrium building with a continuous transfer girder and collector edges |
| 30 | Composite floors, headed studs, camber and paired shear-plate interfaces |
| 31 | Industrial hall with offices, sloped roof and distinct column-cap/collector joints |
| 35 | Three-tier equipment platform, notched plan gussets and equipment ties |

| CFS case | Variety exercised |
|---|---|
| 2 | Strap-wall building with different strap and hold-down groups |
| 4 | Five-level steel-sheet wall building on a podium |
| 6 | Five-level L-plan wood-sheathed walls and close grid spacing |
| 9 | Five-over-two U-plan building with podium and wall interfaces |
| 10 | High-bay SBMF, independent gravity roof, separated office and catwalk |
| 12 | Eight-level cross-plan steel-sheet walls and multi-ply chords |
| 18 | SBMF hall with separated storage mezzanine and sliding restraint interfaces |
| 25 | Existing-building purlin/girt uplift retrofit with roof rods and post-top slides |
| 27 | Single-channel portal framing with torsional restraint details |
| 28 | Partially enclosed agricultural building with six-ply portal columns |

Exact source names, hashes and selection rationale are in [selection.json](selection.json).

## Source and adopted geometry

S means source design data. A means a user-authorized fictional answer, local fit, member addition, position or delegated interface. The complete adopted-answer and model-assumption registers accompany each set. HR/CFS source jobs and their design records are unchanged. No analysis, sizing, strength, drift, fatigue, foundation or supplier certification was rerun. Workline lengths are design dimensions; fabrication procedures and tolerances remain outside this stage.

The school and mixed-system building use corrected drawing titles consistent with their completed source designs; original source filenames remain intact. The applicability register preserves continuous-member instructions without inventing splices. Two source alternatives have no matching occurrence in the saved final model: the school's W14X176/W24X62 weak-axis alternative, and the transfer building's W14X398-over-W14X665 column-splice record. These remain explicit source-only records. Actual strong-axis joints and transfer-truss nodes are detailed from their applicable records.

The review also corrected apex/link-end dimension endpoints. CJP column splices show source division plates, internal diaphragms, doublers, fishplates and box transitions where specified, plus explicitly adopted temporary erection fit. Boxed school-column splices include their side plates and side-plate splice welds. These shared corrections are reissued for eight first-batch HR sets. Separated CFS wings have enlarged, dimensioned framing plans; close grid labels are staggered.

## Reproduce

Install `.[drawings]`, then run:

```powershell
python tools/generate_review_batch.py --confirm-fictional --author "User-authorized fictional review inputs" --output review --cases hr14 hr16 hr18 hr20 hr21 hr24 hr25 hr30 hr31 hr35 cfs2 cfs4 cfs6 cfs9 cfs10 cfs12 cfs18 cfs25 cfs27 cfs28
```

Omit `--cases` for all 43. Frozen inputs for forty additional cases are shipped in `review_data/inputs.zip`; the three original pilot sources remain in `docs/stage3/pilots.zip`. The renderer requires neither HR/CFS engines nor OpenSees. Exact package and answer hashes gate these authored review recipes, preventing them from silently supplying invented answers to ordinary jobs.

The Hub's existing information-request widget and CLI use the same renderer. Reopening a request restores provisional drawing behavior. Ordinary jobs can still draw with proposals and TBD dimensions; this reviewed fictional catalog is not yet a general automatic detailing engine or an IFC exporter.

## Verification

The additional 20 sets contain 3,753 sheets; the combined 43-building collection contains 8,892 sheets (21 HR and 22 CFS buildings). The final module suite passed 126 tests in 313.66 seconds. Four Hub drawing integration tests passed, including fictional adoption from each batch, revision handling and assembled downloads. The 0.6.0 wheel was inspected for all forty additional frozen cases and the new renderers.

[verification.json](verification.json) records final artifact hashes and counts. Automated checks cover source/model/state/PDF consistency, preserved design records, unique identifiers, positive member axes, exact occurrence-to-assembly mapping, valid callouts and dimension coverage. All 812 audited files across the 61 supplied source jobs remain unchanged.

[visual_review.json](visual_review.json) records the exact PDF hash, rendered page count, sampled contact-sheet pages and larger plan/joint samples. Every page was rendered. Selected plans, sections, schedules and connection families/subtypes were visually inspected, with larger samples and correction-specific checks. This is sampled visual review, not full-size inspection of every sheet or structural approval.

The local review indexes are checked for working file links and valid JavaScript. Browser preview of local files was blocked by browser policy; the PDF pages were inspected directly.
