# Stage 2 — physical-data export and legacy-job replay

Implemented on 2 November 2026. All **61 supplied jobs export successfully** and
pass independent schema, semantic, source-fingerprint and source-record checks.
All **812 original audited files are unchanged** (197,184,958 bytes; the original
audit excludes RAG extracts and figures). Hub has not been changed.

All legacy exports correctly remain **`needs_input`**. None is presented as a
complete physical model or an approved drawing. The new exporters recover evidence
and make omissions explicit. New design jobs now have to record the missing
physical decisions during the job before completion can pass.

- [All 61 building results](data/building_coverage.csv) / [JSON](data/building_coverage.json)
- [Remaining findings and affected entity IDs](data/remaining_findings.json)
- [Validation and source-preservation results](data/validation.json)
- [Aggregate replay results](data/replay_summary.json)
- [Complete 61-package replay bundle](bim_packages.zip)
- [Physical-data contract and commands](../../contracts/BIM_EXPORT.md)
- [JSON schema](../../contracts/bim_package.schema.json)

## What is now available

| Evidence recovered | HR | CFS |
| --- | ---: | ---: |
| Buildings | 36 | 25 |
| Analysis elements captured | 27,683 | 3,029 |
| Physical member candidates | 27,363 | 665 |
| Located wall-panel candidates | 0 | 88 |
| Explicitly separated rigid analysis entities | 320 | 0 |
| Original connection design records preserved | 1,746 | 332 |
| All original tabular design records preserved | 2,928 | 8,236 |
| Invalid or failed exports | 0 | 0 |

The 11,164 design records include every top-level list of objects, not just the
tables selected in the Stage 1 audit. Original record values are verified against
their source JSON pointers. Narrative and other context are retained separately.
The 2,078 connection records are design checks/groups; they are not an invented
count of actual connection occurrences.

**HR:** 15 configurations rebuild through the native builder and match their saved
models for element tags, connectivity, coordinates, element properties/options,
and transforms/orientations/offsets. The other 21 configurations import a missing
`stk_ext` helper from their original environment. Their saved literal OpenSees
model commands are replayed instead, with metadata recovered from the saved
viewer/schedule. That fallback does not execute arbitrary saved Python, an eigen
self-check or a design analysis; it does not claim to reconstruct the unavailable
configuration helper. Rigid entities in the gold set are excluded from steel candidates.

**CFS:** 10 portal/component jobs build the native frame and use all declared frame
stations. Candidate members consolidate straight analysis segments. Frame station
count has no viewer cap. Fifteen wall jobs retain their original line/segment and
design evidence without drawing the equivalent spring model as steel. CFS8 has
explicit bay ranges, yielding 88 located panel candidates. Fourteen wall jobs
still need actual along-line segment positions. Existing-shell component scope is
kept explicit.

## Remaining work falls into five data tasks

1. **Confirm physical members and assemblies.** Declare the actual section shape,
   built-up arrangement, grade, roll/cardinal point, cutbacks and offsets. Map
   source member/schedule rows to these entities. Analysis axes and equivalent
   stiffness properties alone do not establish these decisions.
2. **Place connection occurrences.** Map the retained design groups to real
   joints/member ends, with positioned design parts or controlled detail IDs.
   Record non-applicable and delegated cases with reasons and responsibility.
3. **Complete secondary framing, panels and openings.** Supply their actual set-out,
   including missing CFS segment ranges and physical replacements for wall strips.
   Declare the basis for complete coverage of the full building/scope.
4. **Recover the HR helper dependency where full configuration replay is needed.**
   Twenty-one saved-model fallbacks preserve their evidence but remain flagged.
5. **Resolve controlled external details and existing/delegated interfaces.**
   Supplier internals and existing-shell responsibility cannot be inferred from a
   structural analysis model. V1 stores references; a future renderer must resolve
   those resources before issuing a drawing.

These are data-authoring requirements. The replay engine does not need to rerun
design to collect geometry and join existing checks. It also cannot invent design
decisions that the legacy job never saved. Gold source jobs were not edited to
make the readiness flag pass.

## Changes in each repository

HR and CFS now share `bim_contract.py` and `bim_package.schema.json` byte for byte.
Each has a native geometry adapter, an isolated replay CLI, batch replay, source
hashes, deterministic/atomic export and source-freshness checks. Analysis/design
entry points are disabled during trusted replay, and timeouts stop the owned
worker process tree. Replay is process isolation, not an untrusted-code sandbox.

New design jobs create a required BIM-output marker. Their workflow records
`cfg['bim']` and the completed calculation package's `bim` block. After structural
consistency passes, the export is generated automatically; its separate readiness
gate must pass before completion. Existing jobs and the HR build-only workflow
keep their prior completion rules. CFS adds an optional physical segment-position
property without changing its wall analysis.

openBIM now has an installable, engine-independent consumer and validator. It
does not import HR/CFS or OpenSees. `load_package` rejects incomplete packages by
default; callers can explicitly open valid `needs_input` evidence for inspection.
Invalid packages are always rejected. Optional source-root checking detects stale
files. A stored `ready` label is never trusted by itself.

```text
pip install .
steltic-openbim validate path/to/bim_package.json --source-root path/to/source/job
```

`ready` means the v1 data contract passes. It does not certify structural capacity,
fabrication completeness, clash-free placement or an issued drawing. No drawing
renderer, IFC exporter, IFC import or Hub wiring has been built in this stage.

## Verification

- HR exporter/completion checks: **59 passed, 2 adapter-specific skips**.
- Existing HR build-only compatibility suite: **24 passed**. Its local API test
  needed an unrestricted loopback socket on this Windows host; it passed there.
- CFS exporter, completion and wall-load checks: **70 passed, 2 adapter-specific skips**.
- Independent openBIM consumer: **7 passed**.
- **160 tests passed** overall. One existing Starlette/httpx deprecation warning
  occurred in the HR API test. All three Python wheels built and installed
  successfully; installed HR/CFS replay and openBIM validation each passed a
  complete synthetic-package smoke check outside the source checkout.
- All 61 final packages independently validated; every exported design row and
  source/engine fingerprint matched. No original audited source file was added,
  removed or changed. No source job was solved or redesigned during replay.

The tests include complete synthetic declarations, missing/contradictory geometry,
unmapped records, source freshness, joint placement, forbidden analysis calls,
timeout/no-publication, batch continuation, literal saved-model fallback, an HR
orientation mismatch, and 40 CFS frames with knee-brace section mapping.

## Reproduce the audit

Run each source module's `python -m steltic.bim_export batch` in its own environment,
with an external output directory. Then run
`tools/stage2/build_replay_report.py --help` in this repository for the source,
export, engine and baseline-manifest arguments. The report script executes no job
Python. The original source manifest is in `docs/stage1/data/source_manifest.json`.

Replay commits: HR `00c51bd`, CFS `b96a36c`. Each package embeds the full replay
revision and file hashes. Historical producer revisions remain unknown rather
than being replaced with the current replay revision.

Source-module changes were merged into main on 2 November 2026:
[HR PR #95](https://github.com/Steltic/steltic/pull/95), merge commit `38f47c0`, and
[CFS PR #45](https://github.com/Steltic/steltic_cfs/pull/45), merge commit `78fd41a`.
Both merged file trees match the tested replay commits exactly. Use the updated
main branches to enable the exporters. The replay bundle retains its original
pre-merge report; the exported data and validation results are unchanged.
