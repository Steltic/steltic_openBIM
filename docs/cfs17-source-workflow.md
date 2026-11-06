# CFS17 unequal-span garage: source geometry and complete interfaces

The garage now uses the saved 50-foot and 36-foot spans, nineteen frames at
12-foot centres, three independent pairs of source channels, and the
HSS6x6x1/4 valley props. The source knee, ridge, valley and base groups sit
on the actual finite members. Valley cap plates, gussets and receiver lugs
form an explicit assembly; the saved pin-ended analysis remains unchanged.

Secondary framing follows the source snow zones, 15-inch Z laps, actual
end-wall posts, nested purlins, five vehicle doors and two accepted access
doors. Strut brackets, flange-brace cross plates, all three strap systems
and through-fastened ribbed cladding bind to their actual receivers. Roof
straps pass below purlins so the sheet bears directly on the framing.
Source sections, fastener counts, gauges and specified dimensions are
retained; unspecified outlines, offsets, packing and supplementary
attachments are recorded as accepted A inputs with no inherited capacity.
The hollow door headers have explicit sleeves around their bolts.

The valley prop's physical HSS ends at the cap underside. Its analysis
workline remains at the original valley node, with an explicit finite end
offset and a checked mapping to all three original col_I1 elements. The
source analysis EA/EI metadata is retained; selecting the saved final HSS
member does not assert a new stiffness or design calculation.

A mixed anchorage record gives separate selections for exterior channel
columns and interior HSS props. Exact source-clause selections now apply
those requirements at the real bases. The matching native CFS validator
requires the actual source HSS, two flanking columns, matching base joint,
unchanged clause text and located applications of both clauses. Exterior
bolts are retained at exterior bases rather than invented at the HSS base.

Source strength, fatigue, snow and other checks remain separate from
adopted local geometry. Door products, cladding product certification and
foundation concrete/anchor verification remain explicit delegated scope.
No design engine, drawing-derived capacity or external LLM is used.

Final validation results and PDF hashes are recorded separately after
native acceptance, IFC return comparison and visual review complete.
