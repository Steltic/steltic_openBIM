# Stage 3 — three physical-model review pilots

The designed structural scope is composed into three complete review packages, with delegated work, proposed set-out and missing locations explicitly recorded. **All three remain `needs_input`.** These are not construction drawings or fabrication releases.

Download [pilots.zip](pilots.zip), extract it, and open `index.html`. Each viewer works offline, including member/profile inspection, connection detail views, original calculation records and question export. The JSON package download needs its adjacent file, so extract the whole bundle.

| Pilot | Physical members | Connection occurrences | Coordination items |
| --- | ---: | ---: | ---: |
| HR Ex22 — six-storey hospital | 741 | 1,633 | 6 |
| CFS Ex16 — portal warehouse | 1,124 | 2,179 | 5 |
| CFS Ex8 — T-plan student housing | 12,404 | 25,102 | 7 |

A connection occurrence is a located attachment with its source design specification. It may have explicit parts, a referenced detail, or an unresolved detailing requirement. The count does not imply that every weld, screw, cut and bracket outline is geometrically resolved. All 430 source design records are preserved; every drawing-related record is assigned to a physical occurrence or a declared interface.

## What was modelled

**Hospital:** all six framing levels, gravity infills, local penthouse schedule, 35 column lines with 105 physical column pieces and splices 48 in above floors 2 and 4, 20 embedded moment-frame bases, RBS flange reductions, shear plates, continuity/doubler plates and source-specified stud/brace requirements. Fractional mappings connect physical splices to the original analysis elements. Architectural openings, penthouse occurrence approval, several detailing interfaces and conflicting embedded-base stud wording remain open.

**Warehouse:** all 23 frames and 92 primary pieces; built-up four-channel profiles; purlins, laps and nested end-bay reinforcement; side/end girts, eave struts, posts, door headers, straps and specified flange kickers. Both 14 × 16 ft overhead-door openings are clear. Knee/apex group patterns contain 3,036 bolts. Gold gusset plates are bolt-group envelopes, not approved cut polygons. Personnel-door locations, physical frame offsets and remaining bracket/base details require coordination.

**Housing:** the true T footprint, 88 braced bays, 352 strap diagonals, chord packs and rods, gravity/party-wall studs and tracks, bridging/anchors, floor joists and bearing stiffeners, rim tracks, collectors, blocking, squash packs and walkway joists. The roof uses five planes over the 10,304 sq ft footprint with a delegated valley/girder-truss zone. Truss internals and the walkway outer support system are not invented. Physical wall positions use the job's `line_plan_pos_ft`, rather than fitted tributary-analysis positions. Chord-pack spacing and floor-stack discrepancies remain explicit.

Completed calculation records take precedence over earlier briefs where the job explicitly documented a deviation. Other interpretations are presented as proposals. The original briefs and replay inputs are retained in the bundle.

## Review and validation

Eleven final images were visually checked: three whole-building views, three plans, three connection close-ups, a warehouse end-wall elevation and the housing roof/valley plan. The interactive viewers were checked for navigation, layers, occurrence search, source records and coordination questions. See the bundle's `visual_review.json` and `verification.json` for the checked scope and model hashes.

Regression checks cover finite geometry, profiles/orientations, support attachment stations, complete analysis interval mappings, source-record preservation, exact duplicate placements, building-specific layouts/counts, overhead-door clearance, roof footprint, plate handedness and material grades. Open review items independently prevent `ready` status. This is a geometry/data review, not a new capacity calculation or a general clash-free certification. Preview geometry omits rolled fillets, CFS bend radii and unresolved cut shapes.

The focused suites passed: openBIM 22 tests, HR 38 tests and CFS 38 tests. Each source-engine suite skips two tests belonging to the other engine. Render generation and installed-wheel CLI checks are separate. All 812 audited files across the 61 gold jobs were rehashed unchanged; Hub remains unchanged.

## Rebuild and review answers

```text
pip install -e ".[review,test]"
python -m zipfile -e tests/fixtures/stage3_replay_inputs.zip work/pilot-inputs
python tools/build_stage3.py --sources work/pilot-inputs --output work/pilots --render
python -m pytest -q
steltic-openbim validate work/pilots/hr22/bim_package.json
steltic-openbim questions work/pilots/hr22/bim_package.json --output work/questions.json
```

Validation returns exit code 2 for these intentional `needs_input` packages. The recipes refuse a different source revision. They use frozen catalogue dimensions and source-specific occurrence mappings; no OpenSees runtime, analysis or capacity design is used by the consumer.

`record-answers PACKAGE QUESTIONS ANSWERS --output OUTPUT` accepts an array of `{id, value, accepted: true, accepted_by}` objects. It checks source and model fingerprints and records answers for implementation. It does not alter geometry, close questions or change readiness. Rebuild the source-bound recipe and repeat the checks after implementing an accepted answer.

The workflow follows Hub's User-designed building `groups/items`, `key/default`, proposal and explicit acceptance pattern. There is no Hub dependency or API integration yet, and Hub's nonlinear model check is not run by this review tool.

Companion source-exporter changes are published for review in [HR PR #96](https://github.com/Steltic/steltic/pull/96) and [CFS PR #46](https://github.com/Steltic/steltic_cfs/pull/46). They add the shared contract extensions and local-input provenance; CFS also uses the explicit physical wall positions. The offline pilot bundle already contains the required corrected replay evidence and does not depend on those PRs being merged.

## Next implementation

Resolve or accept the proposed coordination set-out, with explicit responsibility for delegated assemblies. Record those decisions in the upstream job's physical declarations, then regenerate and check the package. Use the accepted pilots to implement reusable drawing views, annotations/schedules and IFC export. Extend coverage to the remaining buildings against the Stage 1/2 register; do not apply these three pinned recipes to unrelated jobs.
