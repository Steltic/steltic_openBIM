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
completion certificate. As of this checkpoint, 31 HR cases have individual native
ready results and corresponding IFC export/import/return passes. No CFS case has
completed the full native gate. The final pinned 61-case sweep, matching full PDF
sets, reproduction register and PDF-only ZIP remain outstanding. Website changes
are outside this release and await the user's review.

Machine-readable pattern results are in `drawing-review-patterns.json`. They
retain original source-model hashes and individual case counts. The local test
workspace retains detailed occurrence and IFC evidence; it is not bundled as
production job data.

## Follow-up geometry checks (0.8.40)

HR28's source corner-bar requirement now has located same-size corner bars and
66 in laps, with actual bent-bar solids. Its six long-edge and three short-edge
bars remain separate, and accepted layering avoids intersecting reinforcement.
The additional corner fit and anchorage scope remain explicitly unverified for
capacity. Roof column terminal points refer to their actual top-chord joints.
The corrected case passed native completeness and IFC return checks, including
10,642 products, 14,222 relationships and all 216,456 original IFC entities.

Mixed ordinary/braced track corners preserve the scheduled braced track and
existing vertical offsets. Floor details attach to the real channel plies of
built-up joists/trimmers and use individual flange packers. Receiver selection
prefers framing over both track tiers; a truss seat cannot substitute a nearby
opening trimmer for its own truss. Actual sheet thicknesses determine screw grip.
The delegated CFS11/13/14 roof chords have their centroids above the bearing
surface; their supplier capacity and final roof-cover geometry remain separately
required. These changes do not close the outstanding CFS completeness findings.

## Return walls and parallel floor/roof attachments (0.8.41)

The boundary routine now retains both sides of a re-entrant perimeter, so the
ordinary wall framing on a notch return is not omitted. CFS11/13/14 ordinary roof
walls use the actual roof bearing level instead of deducting a floor-framing
zone. Physical track web centrelines are offset by half the actual web thickness
to keep their outside bearing faces on the recorded workpoints. Original member
axes, sections and the accepted offset history remain available.

Floor/roof details now distinguish transverse and parallel members, including
both real chords of an open-web truss and each channel ply of a built-up chord.
Short gaps at cut track ends use explicit formed returns attached to real webs;
they do not imply direct flange overlap or verified bearing capacity. Interior
roof-wall interfaces use the chord actually crossing or following the wall.
On 48 in framing grids, the receiver search and track extract include the next
member actually over the track, instead of connecting an unsupported nearer
member outside the cut end. The local return-clip reach limit stays unchanged.

Where a fictional roof wall or corridor bearing line misses the adopted framing
grid, additional matching drag trusses/corridor joists are explicit A proposals.
The source wall axes and regular framing grids stay unchanged. Each addition is
listed in the model's change register; added wall loads, supplier transfer and
connection capacity remain separately required.

Drawing sections cut across parallel members to show their actual plies. Long
component labels stay within their view, and repeated identical notes are
shown once. Focused regression fixtures check real screw/bolt contact, mirrored
corners, both truss chords, notch boundaries and label extents. The CFS11 roof
seat and CFS13 return detail were rendered and visually checked.

These are source geometry and accepted fit corrections. Supplier/capacity
approvals and the remaining native completeness findings are still required;
this release does not declare the CFS examples or the full 61-case sweep ready.

## Cut truss members beside openings (0.8.42)

Opening cutbacks follow a sloping member's own axis. Node details retain the
actual remaining member length, roll and receiver identity; a short piece cannot
reuse a longer node's screw layout. Where the usual fictional six-screw group
does not fit, the smaller group and its outstanding supplier/engineer capacity
check are explicit A proposals. This does not alter checked gold selections.

Section cuts retain intermediate vertices on web/flange caps and preserve gaps
in concave faces. Focused tests check both member end orders, every screw's
contact with the real sheets, separate short/long node variants and empty gaps.
The full regression run passed 580 tests and exposed one CFS8 section station
beyond a short chord. Sections now pass through the actual screw group; that
failed case and four focused geometry tests passed after correction. The final
dimension refinement passed all four focused tests. CFS2 passed all 2,801
variants and 76,958 installed occurrences. A short-node sheet was rendered and
visually checked. Native completeness remains a separate, unfinished gate.

## Parallel wall grid stations and roof applicability (0.8.43)

In CFS3 and CFS12, an actual parallel wall can fall between the regular floor or
roof framing stations. Additional matching trusses/joists on those wall axes are
explicit A proposals, recorded with wall-member IDs, framing prefixes, level and
station. Existing wall axes and regular framing remain. Added loads, bearing and
supplier/attachment capacity are still unverified. Actual-sheet contact is
checked at the formerly unbound CFS3 and CFS12 wall heads.

At CFS13 low-roof heads with no wall above, the explicitly labelled bottom-track
anchor/inter-storey strap schedule is retained as context. Its base/floor
selections remain on their actual occurrences. A missing receiver or an
unlabelled schedule does not qualify for this treatment. Eight applicability
tests include the actual NE low-roof and foundation occurrences. Native source
assembly mappings remain outstanding; no complete-case acceptance is asserted.

CFS3 passed all 3,278 variants and 80,128 installed occurrences; CFS12 passed
all 5,259 variants and 63,308 occurrences. Two actual wall/contact regressions
and 14 affected schedule/applicability tests passed. Native assembly entry for
the large cases continues separately; physical fit alone does not make them ready.

## Full-width plate-wall bases and repeated weld labels (0.8.44)

HR9's plate-wall base now uses its actual full-width wall profile and source
1 x 12 in embed plate. Each 28 ft panel has all 112 headed studs at four per
foot. The 3/8 x 4 in fishplate, two 1/4 in shop fillets and both 3/16 in field
lap edges retain their source records. The 2 in bottom clearance, fishplate
datum and 5 in stud length are explicit A fit proposals; foundation
and local capacity verification remain outstanding. The source workline is
retained while the physical plate and panel boundary record the bottom cut.

The full-width base passes receiver fit. Five separate HR9 plate-edge/splice
variants remain unresolved, so this does not establish whole-building readiness.
Twenty affected source, geometry and annotation tests passed. The actual base
sheet was rendered and visually checked.

Repeated identical weld specifications now share the same callout range used
by the parts legend. Every individual weld stroke and exported weld is retained.
This prevents a 112-stud row from creating 112 leaders extending outside the
elevation into adjacent views. The enlarged section retains the real wall,
fishplate, embed plate and stud location.

## Source stud rows and explicit bottom-track splices (0.8.45)

The HR9 base component summary says four headed studs per foot. Its detailed
capacity check specifies **two rows at 6 in pitch**. Both rows are now preserved,
with the same 112 studs across each 28 ft panel. The 3 in edge margins and 5 in
stud length remain explicit A proposals; the row count and pitch are S.

CFS2 had 108 unconnected coincident bottom-track joints between its continuous
wall bays. Each now has an explicit A proposal: a 1/8 in butt gap, two external
54 mil flange straps and three No.12 screws into each track on each face.
Actual sections, web bearing datums and original workpoints are retained.
Existing selected connections are not replaced. These fits do not assert a
checked collector, shear-wall transfer or anchorage capacity.

All 2,996 CFS2 detail variants and 77,066 installed occurrences passed receiver
fit. All 108 new splice details passed actual-sheet screw-contact tests. Both
the splice and revised HR9 base sheets were rendered and visually checked.
The full openBIM regression suite passed all 595 tests. The subsequent CFS2
native export exceeded the harness's 600-second worker limit and must be
retried independently; no new native completeness result is claimed.
Native source mapping and other remaining completeness findings are tracked
separately; this release is not a complete-case or all-61 acceptance claim.
