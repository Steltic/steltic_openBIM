# Architectural IFC video examples

These are synthetic IFC4 architectural models in millimetres, prepared to stand in for an architect's Revit-to-IFC exchange. They were **not actually exported by Revit**. Each has standard IFC grids, storeys, slabs/roofs, exterior walls, door/window void-and-fill relationships and spaces. No structural beams, columns, member section sizes, plates or fasteners are supplied.

| Example | Architectural source | Import review | HR model-creation check |
| --- | --- | --- | --- |
| Five-storey office | Ex1 SCBF; 150 x 90 ft, 67 ft roof | 111/111 objects displayed | 164 nodes, 370 members; five storeys, 40 chevron braces |
| Z-plan school | Ex16 IMF; classroom/link/gym | 105/105 objects displayed | 80 nodes, 136 members; 36/24/26 ft roofs, no intermediate gym floor |
| Gabled warehouse | Ex31; 200 x 80 ft hall and lower office | 41/41 objects displayed | 60 nodes, 83 members; 26 ft eaves, 36 ft ridge, 16 ft office, no ridge columns |

Architectural space volumes are hidden by default in the preview; this does not discard them. Source counts exclude spatial containers, grids and opening void entities, and count the displayed doors/windows separately. All three IFCs validate and all selected objects render. Architectural slab material/structural design data remain explicitly unspecified.

`job_brief.txt` is the engineering input to enter in openBIM. It contains the original fictional HR test brief and explicit demo supplements for missing criteria. `hr_brief.txt` is the generated handoff to HR with IFC-derived geometry and source references. `source_manifest.json` records the synthetic origin and input fingerprint.

## Model creation versus design

`hr_model_creation` contains an actual HR-engine/OpenSees model and its exact replay check. The framing arrangements and starting sections are explicitly recorded as **preliminary engineering proposals** in `framing_proposal.json`. They are not architectural facts, completed designs or analysed models. No masses/diaphragms or capacity claims are assigned in this geometry check. Warehouse longitudinal bracing/secondary purlins and final school frame-line releases remain engineering work for a full HR run. No previous gold-standard designs are read to create these previews.

Each preview was checked for connected member topology, zero-length members and preservation of key IFC geometry. The standalone OpenSees script was replayed and every node coordinate and element connection compared with the original build. Three architectural previews and three framing previews were visually inspected.

## Recording sequence

1. Create/select a new Hub project. In openBIM > IFC import, upload the example's `architect.ifc`.
2. Retain all objects and declared millimetres; build and inspect the review. Record model-review notes if useful.
3. Under Continue to structural design, choose HR Steel, paste `job_brief.txt` and prepare the HR design brief. Download it.
4. Open HR Steel > Design for the same project. Upload `hr_brief.txt` and run the normal design workflow.
5. When the HR run is complete, select its source in openBIM > Steltic import. Generate drawings and review the request register.
6. Generate the return model in IFC export, choosing the Steltic drawing revision. The IFC report states exactly which physical geometry and connection information the HR output supplied.

Fresh HR jobs with declared physical occurrences now use A1 source drawing sheets: dimensioned grids and levels, member marks, frame sections, connection callouts and member schedules. Supplied connection parts appear in three orthographic views and an isometric assembly view, with their source envelope dimensions. Reference-only details stay explicitly TBD. The member, connection and source-record indexes accompany the PDF; this route does not adopt a fictional review recipe or change the HR design.

Source connection polylines (for example, splice references) are retained as amber dashed references in the drawings and as `IfcAnnotation` objects in the structural return. Their coordinates and detail notes survive reimport; they are counted separately from connection-part surfaces. They do not establish plate or weld solids. Connection views include members joined through an intermediate attachment as well as member ends. Declared delegated interfaces are retained in the drawing basis and IFC project properties.

For video narration, call the input a **mock architect IFC**. The receiving architect can use an IFC-capable application; actual Revit import/export acceptance was not tested in this environment.

## Reproduce inputs and geometry checks

From a checkout with openBIM's IFC dependencies and the HR engine environment:

```powershell
python tools/architect_demo/make_inputs.py --hr-repo ../steltic --output demo
# Import/build each IFC in openBIM, prepare its HR handoff, and download
# architectural_geometry.json into the corresponding example folder.
python tools/architect_demo/build_hr_previews.py --hr-engine ../steltic/steel_engine --examples demo
```
