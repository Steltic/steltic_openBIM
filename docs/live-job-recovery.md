# Live HR job occurrence recovery

Version 0.7.1 fixes an export failure in which one representative member could claim hundreds of separate analysis elements through `analysis_ids`. The previous contract verified that every ID appeared once, but did not compare the claimed elements with the physical axis. A section group at one coordinate could therefore pass as a complete building. Missing storey labels then collapsed the ordinary drawing set to one level.

The shared HR/CFS/openBIM validator now requires mapped intervals to form the actual physical reference axis. Collinear analysis subdivisions and explicitly mapped physical splice segments remain supported. Parallel occurrences, branches, gaps and catch-all claims produce a non-blocking `analysis_occurrence_geometry` finding for drawing consumers and prevent a required producer export from passing its completion gate.

For an ordinary HR job with invalid occurrence mappings, unmapped line elements or recovered analysis candidates, openBIM builds a separate source-workline view. It uses the captured nodes, element connectivity, section assignments and storey elevations, excludes declared analysis-only entities and does not execute the source configuration or any structural analysis. Unverified prototype members, panels and connections remain in the immutable source package, but are not presented as complete building geometry.

The A1 coordination set includes every captured level, measured grid distances, member marks, frame sections, joint references, section-count schedules and every original connection record. Member occurrence IDs and coordinates are retained in `member_index.json`; `source_workline_model.json` records coverage, exclusions and the representation basis. These source worklines are not physical cut lengths or resolved assembled connections. C-series sheets retain source specifications with applicability and missing geometry labelled TBD. Source notes that describe simple connections while also specifying RBS components are explicitly raised for reconciliation.

Four requests cover physical set-out, connection assemblies, floor/secondary geometry and opening layouts. Each has a proposal accepted for provisional drawing. Illustrative opening positions and sizes remain dashed and dimensionless until quantitatively resolved through the existing editable query interface. Existing source declarations and engineering results are not silently replaced with fictional review answers.

Regenerate, or re-import the same package with its current revision, to recheck completeness after updating. New requests are added without losing saved answers or historical PDFs. Opening confirmation uses the recovered model's bounds and storeys. Correct, fully declared packages also receive inferred storey labels from source elevations when labels are absent; their geometry is unchanged.

HR/CFS source fingerprints now exclude ephemeral `.run` scripts and root conversation/run logs. Actual configuration, calculation, schedule, model and job-local data files remain tracked. `bim_inputs.json` can explicitly include an otherwise excluded file if a configuration truly consumes it.

Regression fixtures are synthetic. The private local job used for diagnosis is not committed or published. The existing 61 fictional review recipes and their previously released PDFs are unchanged.
