# Assembled connections and varied building review

The three original pilots and ten additional HR plus ten additional CFS buildings now have dimensioned A1 design sets with assembled joints. Each exact geometry/source variant has an elevation, cut section, isometric view, component identifiers, fastener and weld/interface callouts, and dimensions. Plan callouts and the member/connection indices map occurrences to their detail sheets.

Source data (S) is preserved. The user authorized sensible fictional answers (A) for missing locations, fit, support context and delegated geometry. Workline dimensions are not fabrication cut lengths. No strength, drift, fatigue, supplier, foundation or code checks were rerun. Source conditions requiring those checks remain in the drawings and JSON records.

## Coverage

- Original pilots: HR22 hospital; CFS16 warehouse; CFS8 T-plan housing.
- HR: 8 EBF, 9 SPSW, 10 dual SMF/SCBF, 11 BRBF, 12 chamfer/setback SMF, 13 split-level OCBF, 27 composite core, 28 STMF, 32 existing-building addition and 33 crane bay.
- CFS: 3 podium bearing walls, 7 Z-plan steel-sheet walls, 11 coastal gypsum walls, 13 perforated walls, 14 mixed split-level, 17 unequal two-span portal, 19 monorail, 26 canopy, 29 mezzanine and 30 cold storage.

[Selection](selection.json), [automated artifact verification](verification.json), and [visual review extent](visual_review.json) are retained here. Source connection schedules without a separately located joint remain explicit in each generated `source_applicability.json`; they are not counted as assembled joints. These include continuous-member/no-splice instructions and source alternatives or requirements without located occurrences.

## Reproduce

Install the drawing extra and run from the repository:

```powershell
python -m pip install ".[drawings]"
python tools/generate_review_batch.py --confirm-fictional --author "User-authorized fictional review inputs" --output review --cases hr22 cfs16 cfs8 hr8 hr9 hr10 hr11 hr12 hr13 hr27 hr28 hr32 hr33 cfs3 cfs7 cfs11 cfs13 cfs14 cfs17 cfs19 cfs26 cfs29 cfs30
```

Use `--cases hr8 cfs17` for a subset. Original pilot packages are in `docs/stage3/pilots.zip`; frozen source/configuration/calculation/viewer packages for both additional batches are in `src/steltic_openbim/review_data/inputs.zip`. Omitting `--cases` now generates all 43. The generator needs neither source engine nor OpenSees. Exact source and answer hashes gate the authored recipes; ordinary jobs cannot silently acquire fictional answers.

Each folder contains the PDF, physical model, assembled geometry, member index, immutable source records, adopted answers and revisioned decision state. The shared Hub request widget and CLI use the same model and renderer. JSON assembly downloads retain full notes where a PDF annotation must be shortened.

## Validation

Every PDF page was rendered. Selected plans, sections, schedules and each connection family/subtype were visually inspected on contact sheets; a large plan and complex-joint sample was inspected per building. Review records identify the sampled pages and exact PDF hash. This is sampled visual review, not full-size inspection of every sheet or structural approval.

Automated checks cover model/source/PDF hashes, unique member and sheet identifiers, positive-length axes, occurrence-to-detail mapping, dimension coverage, preserved source records and explicit fictional-answer confirmation. All 812 audited files across the 61 original jobs remain unchanged. The module suite passed 90 tests; the Hub drawing integration passed three tests. Regression tests cover assembly fit, source variants, irregular footprints, story-specific connections, provisional-query behavior and API gating. The 0.5.0 wheel includes frozen case data and renderers. All 278 links in the local review index resolve; browser preview of that local HTML file was blocked by browser policy.

## Reissue with the second batch

[Stage 7](../stage7/README.md) completes the next ten HR and ten CFS buildings, bringing the collection to 43. Its shared corrections reissue HR8, HR9, HR10, HR11, HR12, HR13, HR27 and HR28: CJP splices show source transition components and explicit temporary erection fit, and apex/link-end dimension endpoints follow the welded interface. Unprovided fit is marked A. The verification and visual-review records here identify the reissued PDFs and retain their prior reviewed hashes. The original 23 sets still contain 5,139 sheets; the initial 0.5.0 test counts above describe the earlier checkpoint. Current regression results are recorded in Stage 7.
