# Gold-building IFC round-trip verification

These audit tools reuse the 61 saved gold designs and their previously adopted physical models. They run local HR/CFS model-only replay, source IFC export, the actual Hub IFC import/build/export endpoints, a second import/build of the returned IFC, and complete comparisons. They never invoke an LLM provider, structural redesign, analysis solve or drawing engine.

## Inputs and environment

Set `STELTIC_SWEEP_WORKSPACE` to the existing verification workspace. It must contain:

- `outputs/workflow_61/sweep_plan.json`, with the 61 source/model mappings;
- the saved physical models and source packages named by that plan, including the corresponding immutable `state.json` files;
- the checked-out HR, CFS and openBIM repositories under `work/repos/`;
- the existing HR and CFS Python environments under `work/envs/hr/` and `work/envs/cfs/`.

Use the HR verification environment to run these scripts. It includes IfcOpenShell, HTTPX, NumPy and filelock. The native CFS model-only replay uses its own environment. Gold inputs default to the original local `drawings/jobs` and `drawings/gold_cfs_jobs_2026-10-31/jobs_cfs` directories; `STELTIC_HR_GOLD_ROOT` and `STELTIC_CFS_GOLD_ROOT` can override those roots.

Run the local Hub with openBIM installed. `STELTIC_SWEEP_HUB_URL` defaults to `http://127.0.0.1:8300`. Projects use the `GoldRoundTrip_` prefix. These scripts do not call the native HR/CFS paid job endpoints or change provider settings.

## Run

```text
python tools/gold_ifc_sweep/gold_native.py
python tools/gold_ifc_sweep/run_gold_sweep.py
python tools/gold_ifc_sweep/report_gold.py --final
```

The first two commands accept optional case IDs such as `hr1 cfs26`. The full summary requires all 61 cases. Results go to `outputs/workflow_gold_61` in the workspace. Smaller round trips run two at a time; larger ones run individually. Every review selects all objects with the source-declared units.

## Acceptance

1. Model-only native replay succeeds with analysis disabled. Original source-file hashes, saved design records and analysis node/element datasets match the gold evidence.
2. The saved physical model is bound to its exact original package. Its previously adopted fictional inputs remain explicitly attributed; no new geometry is inferred.
3. Source IFC export validates, retains all physical-model occurrences and the complete design-record register, and preserves full connection references where no hardware was placed.
4. Actual Hub source and returned-file reviews build every object, with zero unrendered objects and zero scope exclusions. Downloaded originals and review models are hash-bound to their committed API revisions.
5. Every original IFC STEP declaration survives unchanged. This includes geometry, placements, units, grids, levels, materials, properties and relations. Only review-property entities may be appended.
6. Every product's complete review record matches after reimport, including world vertices, faces/lines, bounds, storey, section, material and properties. There is no sampling or tolerance-based acceptance of changed geometry.
7. The final report checks the gold inputs and adopted models again for mutation.

Export reuse requires the same exporter, snapshot inputs and IFC bytes. Hub evidence is reused only for the identical source IFC, and comparisons run again. A failed stage retains its log and is not counted as a pass.

Passing this audit verifies transport of these saved gold models. Source findings remain visible. It does not claim fresh engineering design, fabricated hardware where none was modelled, independent architectural IFC conversion, browser performance at every model size, or native Revit acceptance.
