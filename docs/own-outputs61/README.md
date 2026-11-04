# Own-output audit of all 61 buildings

Completed/partial updated-producer jobs: own saved outputs and read-only native re-export only. No supplements or legacy gold substitution.

Audit status: complete. 26 primary saved packages; 35 absent. Recorded runs: {'done': 7, 'error': 39, 'paused': 6, 'not_started': 9}.

Saved-job acceptance: **2/61**. Original native completion gates: 2/61. These counts require actual saved source evidence; an old done flag is insufficient.

Native own-input re-export: {'exported': 27, 'failed': 1, 'unavailable': 33}. Re-exported IFC exchange: {'passed': 27, 'blocked_source': 1, 'unavailable': 33}. 4 primary re-exports pass both source-completeness and independent architectural checks; this does not make their original producer runs complete.

Every product's full geometry/data and every original STEP entity are compared. Primary re-export comparisons cover 148,696 products and 2,090,030 entities. Earlier controls (6 runs) are recorded separately and do not increase the 61-case count.

openBIM 0.8.32 is merged in [PR #41](https://github.com/Steltic/steltic_openBIM/pull/41) and [PR #42](https://github.com/Steltic/steltic_openBIM/pull/42). HR, CFS and Hub are unchanged; see [the review-only fix list](upstream-fix-list.md). No LLM calls, redesign, analysis solves, drawing generation or physical supplements were used.

| Case | Building | Saved run | Saved package / native gate | Own-input re-export | IFC exchange | Independent input check | Outcome |
|---|---|---|---|---|---|---|---|
| cfs1 | ShearWall | done | present / fail | ready | passed | passed | reexport_checks_passed_producer_not_complete |
| cfs17 | CFS portal | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs29 | Strap-braced mezzanine | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr1 | SCBF | done | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr16 | SMF (completed source design) | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr31 | R3 gable warehouse | done | present / pass | ready | passed | passed | saved_job_passed |
| cfs16 | Portal warehouse | paused | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs2 | Strap-braced walls | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr4 | BRBF | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr8 | EBF | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs18 | Portal with mezzanine | paused | present / fail | ready | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs6 | WSP walls | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr11 | BRBF | paused | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr13 | OCBF | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs26 | Cantilever-column canopy | done | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs3 | Steel-sheet walls | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr12 | SMF | done | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr9 | SPSW | error | absent / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs19 | CFS portal / monorail | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs7 | Steel-sheet walls | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr21 | OCBF | done | present / pass | ready | passed | passed | saved_job_passed |
| hr33 | IMF / OCBF crane bay | error | present / fail | ready | passed | passed | reexport_checks_passed_producer_not_complete |
| cfs27 | Single-channel portal | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs8 | Strap walls / T plan | error | present / fail | failed | blocked_source | not_tested | invalid_source |
| hr22 | Hospital / SMF | paused | present / fail | ready | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr25 | SMF | done | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs28 | Agricultural portal | error | present / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| cfs4 | SBSW | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr24 | SMF X / SCBF Y (completed source design) | error | absent / fail | needs_input | passed | needs_resolution | transport_passed_source_needs_resolution |
| hr3 | BracedMoment | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs30 | Propped CFS portal | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs9 | Podium wall building | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr10 | Dual SMF + SCBF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr14 | EBF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs10 | SBMF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs25 | Purlin/girt retrofit | paused | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr27 | CC-PSW/CF + SMF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr28 | STMF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs11 | Gypsum shear walls | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs13 | Type II WSP walls | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr30 | Composite SCBF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr32 | Existing + addition | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs12 | Steel-sheet walls | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs14 | Strap X + WSP Y | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr18 | R3 not specifically detailed | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr35 | Ch15 equipment platform | paused | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs15 | WSP | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| cfs5 | StrapBraced | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr17 | SCBF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr20 | SCBF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr2 | SMF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr5 | SMF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr6 | SCBF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr7a | SMF | error | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr15 | Dual | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr19 | SMF | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr23 | Dual | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr26 | Dual | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr29 | Dual | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr34a | Twin | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |
| hr34b | Twin | not_started | absent / fail | unavailable | unavailable | not_tested | no_own_package |

## Limits

- All 61 identities are audited; missing or invalid job outputs cannot become successful IFC round trips.
- A local own-input re-export is recovery evidence, not proof that the saved production job automatically exported complete data.
- The previous gold sweep used physical supplements and is not counted here.
- Original producer revisions were not recorded. Existing source/engine hashes are preserved; replay exporter revisions are recorded separately.
- Geometry/data checks and IFC transport do not recheck structural capacity, fabrication fit, engineering approval or native Revit operation.
- Input comparisons flag unexplained differences for review. Architectural finished surfaces, physical reference planes/thickness and legitimately added structural panels need explicit correspondence; a difference is not automatically a structural defect.
- The production openBIM API was tested in isolated local projects; the Hub embedded dependency remains unchanged pending review.

## Evidence and reproduction

[Audit scripts](../../tools/own_output_sweep/README.md), [source integrity](integrity.json), [final import-readiness verification](import_readiness_verification.json), and [regression results](test_results.json).

Every case has a local source audit, native replay verdict, saved/replayed exchange result and, where possible, an independent architectural comparison. Original and returned IFCs plus hash-bound API review models remain in `outputs/own_outputs_61` in the verification workspace. Large model files and private job contents are not included in this documentation commit.

Consumer fixes were applied incrementally: source freshness/completeness in 0.8.31, then import finding retention and the fully voided-panel fix in 0.8.32. Each exchange records exact consumer code hashes. HR11's earlier failed attempts are preserved; both variants passed after its fix. The geometry review algorithm is unchanged between these versions. The final import-readiness parser was checked on every successful source/returned IFC pair.

The production openBIM router and worker processes were exercised in isolated local FastAPI projects. The running Hub's pinned consumer was not changed. This is not a claim that the currently installed embedded Hub module already contains these fixes.
