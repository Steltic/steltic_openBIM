# HR brace continuity and PDF scope corrections

HR1, HR15, HR23, HR29, HR34a and HR34b previously placed the upper
brace support strip at the top-of-steel workpoint even when the inclined
brace met the underside of the beam farther into the bay. The strip,
stiffeners and any source doubler now centre on that actual flange
intersection. Source worklines, weld lengths, plate thicknesses and design
records are retained. Finite brace ends also update the physical model,
so the assembled detail, native package and IFC describe the same geometry.

The continuous gusset contains the complete slotted-HSS attachment or BRB
cheek/pin attachment. BRB clevises follow the brace slope and meet an
explicit adopted supplier end cap. End-cap thickness/welds, clevis fit,
free-edge outline and other unspecified stations remain labelled A.
These fits do not acquire source capacities or supplier qualification.
The correction is scoped to the six reviewed cases; other case renderers
retain their existing checked geometry.

HR27 omits core-base/core-wall details and standalone core views from its
PDF. HR28 omits edge-bar and slab-edge details. The index, schedule links
and plan callouts exclude those sheets, while the complete physical
collections, original design records and already-verified IFC remain
unchanged. The PDF cover records the scope.

Validation includes all-occurrence native checks and a new IFC export,
import geometry/property/relationship comparison and graph-preserving
return for the six physical revisions. Both PDF-only revisions matched
their accepted physical collections exactly. Every PDF page passed the
sheet-index/text check; the representative sheets listed in the companion
JSON were manually inspected from Poppler renders. This is not a claim
that every PDF page received a manual check. Fourteen focused regression
tests cover continuous gussets, pin receivers, physical end offsets,
source worklines, unchanged source designs and existing datum behavior.

| Building | PDF pages | Visually inspected sheets |
|---|---:|---:|
| HR1 | 78 | 8 |
| HR15 | 535 | 12 |
| HR23 | 261 | 16 |
| HR29 | 397 | 21 |
| HR34A | 225 | 11 |
| HR34B | 189 | 11 |
| HR27 | 375 | 14 |
| HR28 | 251 | 8 |
