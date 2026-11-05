# CFS5 floor and roof diaphragm representation

The CFS5 example formerly rounded its floor finish to 2 inches and its roof
sheathing to 3/4 inch. The physical model now retains the specified 23/32-inch
Structural I floor panels, separate 1.5-inch gypsum underlayment, and
19/32-inch roof panels. Finish elevations are retained. The adopted floor-wall
bearing datum moves down 7/32 inch to fit the actual 10-inch joists and layers.
West-edge joist flanges face into the floor footprint.

Blocked sheathing edges now have 13,248 explicit blocks, finite end clips and
No.10 panel screws at no more than 6 inches. The source fixes the sheathing,
blocked condition and edge screw schedule. The 96 by 48-inch sheet grid,
matching-depth 54 mil blocks, clip geometry and receiving screws are A fit
proposals. Boundary blocking respects the actual parapet clearances. These
local fits and sheet-edge offsets do not create new capacity checks.

Four source roof bottom-flange strap rows are represented at 6.8 feet along
the 13.5-foot spans, with one No.10 screw per joist. Same-section solid blocks
are provided at no more than 12 feet across. Source two-screw blocking ends
are retained; the folded clips, receiving screws and strap/block retention
screws remain explicit A proposals. Actual roof joists in the specified
parapet drift zones carry the original drift check and its exact gravity-table
duplicate. Source numerical design records are unchanged.

Braced-wall layout links require every named storey, bay length and bay count
to match the source. A test changing one bay by one inch must leave that
source record unresolved. The ordinary floor gravity-table aliases are linked
only after checking their numeric/design fields against the saved framing
records.

Validation: ten focused floor, fastener-contact, steel-overlap, roof-restraint
and parapet tests passed. A separate fit audit passed all 3,573 detail variants.
Nineteen connection previews were visually inspected, including both clip
ends, floor/roof panel fixings, the reversed west-edge joist and bottom straps.
Collector straps and drag-plate attachments remain a separate pending task;
this change does not claim complete CFS5 native or IFC acceptance.
