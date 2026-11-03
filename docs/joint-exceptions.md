# Joint occurrence coverage


## Explicit joint exceptions for new jobs (openBIM 0.8.25)

When `require_connection_parts` is true, a joint without its own connection must
have an explicit `joint_dispositions[].kind`. A reason or representative detail
alone no longer establishes occurrence coverage. Keep the explanatory `reason`.

- `free_end`: one physical member end, with no support attachments.
- `continuous_member`: two opposing collinear physical ends meeting at the joint,
  or one interior attachment on an uninterrupted member with no other member
  ends. A connected branch, column base, splice or cutback gap is not a continuous
  subdivision merely because its note says so.
- `bearing_interface`: a real hardware-free interface, with `design_record_ids`
  for its completed bearing/load-path checks and `supporting_entity_ids` for the
  actual supporting members or panels. Do not use this to omit screws, clips,
  welds or hold-downs required by the design.
- `shared_connection`: `connection_ids` identify existing located assemblies
  serving this joint. Reuse actual assembly references instead of duplicating
  hardware. A typical detail elsewhere is not a shared local assembly.

For example, an actual free tip can use
`{"joint_id":"tip","kind":"free_end","reason":"Unloaded cantilever tip"}`.
A genuinely shared seat can use
`{"joint_id":"beam-end","kind":"shared_connection","connection_ids":["seat-at-B2"],"reason":"This seat serves both coincident member-end joints"}`.

These are conservative topology, reference and absence checks, not engineering
capacity or fabrication-fit approval. Use real selected components and locations
for every repeated connection family; do not relabel an error to pass a check.
Reason-only legacy declarations remain readable for jobs without the located-part
requirement. Upgrade producers and consumer together for these optional v1 fields.
Panel and opening vertices must follow a simple perimeter, including gable peaks;
self-intersection/backtracking blocks readiness before IFC export.


Selected connection components are also checked in required jobs (openBIM 0.8.26):
explicit bolt, screw, anchor and weld selections in connection/anchorage/base
records need corresponding located part categories. A plate alone does not
represent its selected anchors or welds. Solids or explicit reference groups
are acceptable at design coordination level; retain actual counts, sizes and
locations from the checked design. This limited absence screen does not verify
quantities, contact, capacity or fabrication detail. Generic code citations do
not create new component selections. Do not relabel unrelated solids to pass.
