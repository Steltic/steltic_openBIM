# All 61 gold buildings: IFC round-trip verification

**61/61 passed: 36 HR and 25 CFS.** The sweep compared 459,920 modelled products and 6,264,849 original IFC entity declarations, retaining all 11,164 saved design records. No LLM provider, redesign, analysis solve or drawing engine was used.

The tested path was: local HR/CFS model-only replay of the gold job → saved physical model and design records → source IFC → actual Hub IFC import/build → IFC export → returned-IFC import/build → complete comparison.

All 61 replayed analysis node/element datasets and saved design records matched the original gold exports. Existing adopted fictional coordination supplements were bound to their exact source packages and retained with provenance; they were not regenerated or silently promoted to source-engine declarations.

The native replays comprised 36 HR models, 10 CFS frame models and 15 CFS wall-line physical-declaration exports. Wall-line gold sources have no frame node/element dataset and did not require a spring solve.

Every original STEP declaration survived unchanged, including geometry, units, placements, grids, storeys, materials, properties and relations. Only review metadata was added. Every product’s complete review record matched after reimport: world vertices, faces/lines, bounds, storey, section, material and properties. All objects built successfully, with zero unrendered objects, zero scope exclusions and zero schema errors. No objects were sampled.

The final audit also verified 373 gold input files and all 61 adopted physical-model files remained unchanged.

## Fixes and versions

- [openBIM PR #38](https://github.com/Steltic/steltic_openBIM/pull/38), version 0.8.29: retain the complete saved design-record register, including anchorage and schedules without solids; preserve every declared connection-reference field; correct the import screen’s existing product-limit label. All 54 IFC regression checks passed.
- [Hub PR #45](https://github.com/Steltic/steltic_hub/pull/45): pin the embedded openBIM consumer to the same fix.
- [openBIM PR #39](https://github.com/Steltic/steltic_openBIM/pull/39), version 0.8.30, and [Hub PR #46](https://github.com/Steltic/steltic_hub/pull/46): batch native geometry without losing products or reducing detail; terminate the complete owned worker tree on timeout. All 57 IFC regressions passed.
- HR replay: `343e0ad6cca528ecb30d07408224dca3597451c6`. CFS replay: `dfaae462f246cd0d694bf6f828f1f90ac7b4f9b5`. These repositories were unchanged during this sweep.
- The source exporter matches openBIM `a8f16e147f05f4432085ab6cd215bab6397dfae8` and is unchanged in 0.8.30. Before the geometry update, the running Hub import/build/imported-export code was verified identical to that commit. [Initial code-equivalence evidence](runtime_code_equivalence.json).
- The first 47 passing cases also received a complete source-review regression with the new geometry path: every review record was identical. The remaining cases used 0.8.30 in the actual Hub. [Full geometry-upgrade regression evidence](geometry_upgrade_summary.json). The largest case’s [earlier slow build](cfs2/interrupted_attempt.json) was interrupted without changing its source or last published revision, then retried with the fix.

## Scope

This verifies the requested transport of these saved gold models through openBIM. Existing source findings remain visible, including missing material labels, coincident geometry or other recorded data/geometry issues. Connection designs without placed hardware remain complete design records and declared references; local drawing-detail templates are not assigned invented global placements. A passing exchange does not establish new engineering design, fabrication readiness, independently authored architectural-model conversion, browser performance at every model size, or native Revit acceptance.

The two largest cases contain 81,622 and 78,135 products. They were not built concurrently with one another; smaller cases shared spare capacity. Every object was included, within the existing 100 MB / 100,000-product / six-million-triangle limits.

## Evidence and reproduction

[Machine-readable summary](summary.json), [native model equality](analysis_replay_audit.json), and [audit scripts and instructions](../../tools/gold_ifc_sweep/README.md). Full source/returned IFCs, hash-bound API reviews, native replays and the HTML report are retained locally in `outputs/workflow_gold_61` in the verification workspace. Large IFC binaries are not included in this documentation commit.

| Building | Module | Products compared | Design records retained | Result |
|---|---|---:|---:|---|
| CFS1 | CFS | 9,456 | 258 | [Passed](cfs1/result.json) |
| CFS2 | CFS | 81,622 | 386 | [Passed](cfs2/result.json) |
| CFS3 | CFS | 78,135 | 553 | [Passed](cfs3/result.json) |
| CFS4 | CFS | 9,129 | 175 | [Passed](cfs4/result.json) |
| CFS5 | CFS | 17,076 | 380 | [Passed](cfs5/result.json) |
| CFS6 | CFS | 23,314 | 463 | [Passed](cfs6/result.json) |
| CFS7 | CFS | 31,264 | 860 | [Passed](cfs7/result.json) |
| CFS8 | CFS | 15,416 | 228 | [Passed](cfs8/result.json) |
| CFS9 | CFS | 25,384 | 331 | [Passed](cfs9/result.json) |
| CFS10 | CFS | 3,065 | 146 | [Passed](cfs10/result.json) |
| CFS11 | CFS | 8,981 | 481 | [Passed](cfs11/result.json) |
| CFS12 | CFS | 33,994 | 750 | [Passed](cfs12/result.json) |
| CFS13 | CFS | 8,080 | 448 | [Passed](cfs13/result.json) |
| CFS14 | CFS | 7,016 | 367 | [Passed](cfs14/result.json) |
| CFS15 | CFS | 21,482 | 795 | [Passed](cfs15/result.json) |
| CFS16 | CFS | 4,830 | 149 | [Passed](cfs16/result.json) |
| CFS17 | CFS | 2,083 | 183 | [Passed](cfs17/result.json) |
| CFS18 | CFS | 3,701 | 140 | [Passed](cfs18/result.json) |
| CFS19 | CFS | 457 | 208 | [Passed](cfs19/result.json) |
| CFS25 | CFS | 382 | 39 | [Passed](cfs25/result.json) |
| CFS26 | CFS | 97 | 212 | [Passed](cfs26/result.json) |
| CFS27 | CFS | 1,025 | 173 | [Passed](cfs27/result.json) |
| CFS28 | CFS | 580 | 187 | [Passed](cfs28/result.json) |
| CFS29 | CFS | 349 | 71 | [Passed](cfs29/result.json) |
| CFS30 | CFS | 1,464 | 253 | [Passed](cfs30/result.json) |
| HR1 | HR | 643 | 43 | [Passed](hr1/result.json) |
| HR2 | HR | 1,635 | 57 | [Passed](hr2/result.json) |
| HR3 | HR | 1,267 | 65 | [Passed](hr3/result.json) |
| HR4 | HR | 555 | 43 | [Passed](hr4/result.json) |
| HR5 | HR | 1,818 | 58 | [Passed](hr5/result.json) |
| HR6 | HR | 1,014 | 51 | [Passed](hr6/result.json) |
| HR7A | HR | 1,717 | 55 | [Passed](hr7a/result.json) |
| HR8 | HR | 1,518 | 79 | [Passed](hr8/result.json) |
| HR9 | HR | 1,897 | 93 | [Passed](hr9/result.json) |
| HR10 | HR | 2,738 | 181 | [Passed](hr10/result.json) |
| HR11 | HR | 2,593 | 130 | [Passed](hr11/result.json) |
| HR12 | HR | 2,114 | 138 | [Passed](hr12/result.json) |
| HR13 | HR | 1,346 | 59 | [Passed](hr13/result.json) |
| HR14 | HR | 2,165 | 83 | [Passed](hr14/result.json) |
| HR15 | HR | 3,384 | 177 | [Passed](hr15/result.json) |
| HR16 | HR | 305 | 68 | [Passed](hr16/result.json) |
| HR17 | HR | 1,618 | 100 | [Passed](hr17/result.json) |
| HR18 | HR | 1,260 | 48 | [Passed](hr18/result.json) |
| HR19 | HR | 1,073 | 121 | [Passed](hr19/result.json) |
| HR20 | HR | 1,948 | 113 | [Passed](hr20/result.json) |
| HR21 | HR | 7,045 | 25 | [Passed](hr21/result.json) |
| HR22 | HR | 6,370 | 53 | [Passed](hr22/result.json) |
| HR23 | HR | 1,439 | 109 | [Passed](hr23/result.json) |
| HR24 | HR | 1,453 | 93 | [Passed](hr24/result.json) |
| HR25 | HR | 2,032 | 93 | [Passed](hr25/result.json) |
| HR26 | HR | 1,233 | 84 | [Passed](hr26/result.json) |
| HR27 | HR | 2,540 | 156 | [Passed](hr27/result.json) |
| HR28 | HR | 4,040 | 67 | [Passed](hr28/result.json) |
| HR29 | HR | 2,688 | 140 | [Passed](hr29/result.json) |
| HR30 | HR | 1,388 | 61 | [Passed](hr30/result.json) |
| HR31 | HR | 1,309 | 20 | [Passed](hr31/result.json) |
| HR32 | HR | 531 | 28 | [Passed](hr32/result.json) |
| HR33 | HR | 4,415 | 22 | [Passed](hr33/result.json) |
| HR34A | HR | 1,262 | 97 | [Passed](hr34a/result.json) |
| HR34B | HR | 944 | 83 | [Passed](hr34b/result.json) |
| HR35 | HR | 241 | 35 | [Passed](hr35/result.json) |
