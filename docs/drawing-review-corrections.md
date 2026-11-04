# Gold-example drawing corrections

The review covered all 61 original drawing models. The original calculations,
accepted answers and PDFs remain immutable inputs. Corrections produce new
models and review extracts. They do not establish new structural capacity or
fabrication approval.

## Reported patterns

| Original sheet/pattern | Cause and corrected behavior | Audit extent |
| --- | --- | --- |
| HR9 C071, duplicate RBS scoops | A local beam-end extract inherited the remote end's RBS. Retain the applicable end only; each flange has one continuous reduction on each side at that end. The shared renderer correction was merged separately in PR44. | 457 original variants across 17 HR cases |
| HR6 C001, apparent boxed reinforcement | The base parser confused an exposed base with an embedded reinforced shaft. HR6 retains the selected plate, four anchors and cruciform shear lug. Delegated concrete anchor reinforcement remains an explicit source requirement. | 10 original variants across seven HR cases: eight genuine embedded-shaft selections retained; false boxes removed from HR1 and HR6 |
| CFS19 C003, six-piece track | A generic fallback reused the six-channel column profile as a horizontal track. Bind to the actual column and strap. No horizontal track is selected at this occurrence; the receiving plate and its unstated attachment set-out are labelled A. | 16 original variants across eight CFS cases |
| Tubular X-brace crossings | Analysis lines do not define a buildable crossing. Where selected, keep one diagonal continuous and physically split the other, with actual slots, plate and weld interfaces. Retain source selections and label unspecified fit as A. HR33's crossing is an accepted fictional proposal, not a verified source connection. | Located crossing tests for HR3, HR18, HR21, HR30 and HR33 |

Square/rectangular and circular hollow-section braces can use different
engineered crossing arrangements. A centre plate is not a universal requirement.
Continuous braces in separate planes also have a different physical detail and
restraint assumption. A missing detail cannot be inferred to mean an unconnected
crossing. The model must carry the selected arrangement explicitly.

## Additional corrections in this batch

Located receivers, their section orientations and their actual physical ends
replace generic stand-ins in affected review recipes. Corrections cover wall
stud/track screws, straps and hold-down rods; roof and floor bearings; cut opening
members and their supports; HR local reinforcement, splices, releases and bracing.
Source member selections, original analysis identities and changed geometry
remain separately traceable.

At cut CFS track ends, flange screws cannot be placed beyond the receiving
track. Explicit A return clips now connect through the real joist web and track
web where there is no flange overlap. The stepped CFS15 roof also distinguishes
the truss chord centroid from its bearing surface and selects trusses over the
actual track run. These fitted connections retain their unverified capacity
status. Long parts registers continue on numbered sheets instead of clipping
their final rows or dropping notes.

HR30's HSS strut and 45-degree kicker now attach to the actual adjacent beam ten
feet away. Its four source braced-bay strut checks map to the correct X/Y bays and
floor/roof scope. End plates, gussets, bolts and weld fit not given by the gold
design remain A proposals without new capacity calculations.

CFS7 now retains its own staggered-bar grids, source stud tiers, six-foot corridor
joist direction and separate wood/gypsum layers. This is a partial source-model
correction. Its collector, rim/squash and panel-edge requirements remain subject
to the native completeness gate; this release does not declare that case complete.

Older pilot answers resolve only the questions they were written for. New
validator findings remain pending. The regression suite checks that adoption
keeps those packages provisional. Historical dimensioned-rendering tests use
explicit isolated rendering fixtures and do not constitute native acceptance.

## Acceptance boundary

The pattern audit is a targeted drawing correction check, not an all-building
completion certificate. As of this checkpoint, 30 HR cases have individual native
ready results and corresponding IFC export/import/return passes. No CFS case has
completed the full native gate. The final pinned 61-case sweep, matching full PDF
sets, reproduction register and PDF-only ZIP remain outstanding. Website changes
are outside this release and await the user's review.

Machine-readable pattern results are in `drawing-review-patterns.json`. They
retain original source-model hashes and individual case counts. The local test
workspace retains detailed occurrence and IFC evidence; it is not bundled as
production job data.
