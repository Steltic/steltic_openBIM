# Provisional drawing workflow

Information requests no longer stop drawing production. Every request has an explicit proposal accepted for provisional drawing; acceptance does not approve its numerical dimensions. Source framing remains immutable, and no analysis or redesign runs.

Download [the three drawing sets and registers](three_drawing_sets.zip) and open `index.html`. The hospital has 18 sheets, warehouse 13 and housing 23: 54 A3 sheets covering basis/requests, base and level plans, roofs, elevations, every placed connection family, member/connection schedules and opening/zone schedules. All 18 requests remain open in the issued examples. Source-defined warehouse overhead doors retain their known dimensions; proposed personnel doors, windows, shafts and interfaces carry TBD entries.

## Hub interaction

1. In User-designed building, open **Questions** or **Drawings / info**. The separate openBIM module offers the same widget. Select an exported HR/CFS job or upload its `bim_package.json`.
2. Drawings are available immediately after import. Expand an information request to see its proposal, source basis and provisional status.
3. Add information with a reviewer name and source note. This creates a new drawing revision and keeps unresolved dimensions TBD.
4. For opening locations, enter the complete confirmed layout: plane, level, X/Y/base Z, width and height in feet. **Review proposed values** exposes illustrative coordinates for editing; it does not confirm them. Rows may be added or excluded; an empty layout requires explicit confirmation.
5. **Resolve locations and update drawings** saves the confirmed geometry and regenerates the PDF, including the numeric opening schedule. Reopen restores TBD. **Regenerate drawing set** preserves source/answers while publishing a new revision.

Other decisions, including framing offsets, engineering details and supplier geometry, are recorded here and applied by the design agent/supplier to the physical package. Importing a changed package resets its proposals; previous answers and PDFs remain in history. Arbitrary text is not interpreted as confirmed geometry.

The two Hub entry points share `{data_dir}/modules_data/steltic_openbim/sessions/local/jobs`. Per-project thread and file locks prevent competing pages/processes from overwriting each other's answers. Revision and source-hash checks reject stale submissions. A new PDF and register are completed before one atomic pointer publishes the revision; failed rendering leaves the previous revision current. The standalone module uses Hub's local request guard.

## Scope and limits

This is the first coordination drawing workflow, not the finished design-drawing/fabrication release. Plans use physical worklines; schedule lengths and unresolved connection set-out remain TBD. Proposed openings are separate overlays: confirming their coordinates does not cut members, design headers or certify framing around them. Roof internals and other delegated scope remain identified. Physical readiness remains `needs_input` where applicable, and the existing HR build/nonlinear confirmation gates are unchanged.

The renderer consumes a valid physical contract independently of HR/CFS. The three illustrative opening/interface layouts are authored pilot proposals. General proposal generation and detailing for all 61 buildings, richer dimension chains/marking/sections and IFC export are subsequent work. Invalid source geometry still fails validation; an information request cannot mask it.

## Install and API

```console
pip install ".[hub]"
steltic-openbim draw path/to/bim_package.json --output drawings
python -m uvicorn steltic_openbim.drawing_server:app --host 127.0.0.1 --port 8405
```

`OPENBIM_JOBS` selects the revision store; `HR_JOBS` and `CFS_JOBS` select read-only source job roots. The root page accepts `?project=ProjectName`. Hub consumes `steltic_module.json`; the companion Hub change pins this package to its tested commit.

Routes: `GET /api/drawings/sources`; `GET /api/project/{p}/drawings`; `POST .../import`, `.../upload`, `.../answers`, `.../regenerate`; `GET .../history` and `.../file/{filename}`. Answers require current `revision`, `source_model_sha256`, request `id`, `author`, `note` and an action (`information`, `resolve_openings`, `reopen`). Confirmed opening layouts require finite, positive dimensions and valid levels. Only PDFs/manifests/registers are downloadable through these routes.

## Validation

- 34 openBIM tests, including quantity masking, confirmed updates, immutable source, invalid/stale answers, failed-render rollback, shared-store concurrency, revision history, malformed uploads and local request guards.
- 30 focused Hub checks covering existing intake/questions/model gates, the drawing integration and catalog.
- All 54 PDF pages rendered and visually inspected; selected plans, elevations, connection views and schedules checked at full image resolution. Browser verification used the actual User-designed building page and an isolated test project; no test answer is applied to the issued pilot sets.
- All 812 audited files across the 61 gold jobs rehashed unchanged. No source engine changes or analysis runs in this stage.

Broader Hub tests are not wholly green: three failures were reproduced on unchanged main (two Windows native-crash exit-code fixtures and one path-error wording assertion). The legacy package-staging test also showed timing-dependent failures in its unchanged equal-size/mtime shortcut. These findings are recorded in the bundled `verification.json`; the drawing change does not modify that runner.
