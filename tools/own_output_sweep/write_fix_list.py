"""Review-only upstream fixes, with case evidence generated from this audit."""
import collections
import json
from audit_sources import ROOT,OUT,read,save

def main():
    rows=read(OUT/'replay_summary.json');audits=[read(p) for p in OUT.glob('*/source_audit.json')]
    groups=collections.defaultdict(set)
    for r in rows:
        for f in r.get('findings',[]):groups[f['code']].add(r['key'])
    cases=lambda *codes:', '.join(sorted(set().union(*(groups[c] for c in codes)))) or 'None identified'
    feedback=[];real_inputs=[]
    for r in audits:
        changed=[n for f in r.get('source_freshness',{}).get('findings',[]) if f['code']=='source_stale' for n in f['entity_ids']]
        if 'workflow_review.json' in changed:feedback.append(r['key'])
        real_inputs.extend((r['key'],n) for n in changed if n!='workflow_review.json')
    comparisons=[]
    for path in OUT.glob('*/exchange_replay/architectural_comparison.json'):
        r=read(path)
        for i in r.get('issues',[]):
            if i['code']!='complete_native_physical_export':comparisons.append(dict(case=path.parent.parent.name,code=i['code'],evidence_file=str(path.relative_to(OUT))))
    unavailable=[r['key'] for r in rows if r['status']=='unavailable' and not r['key'].endswith('_earlier')]
    record=dict(policy='Review only. No HR, CFS or Hub edits, PRs, merges or runtime pin updates.',
        native_findings={k:sorted(v) for k,v in groups.items()},feedback_fingerprint_cases=feedback,
        genuine_changed_inputs=[dict(case=c,file=n) for c,n in real_inputs],independent_geometry_findings=comparisons,
        unavailable_primary_jobs=unavailable)
    save(OUT/'upstream-fix-list.json',record)
    lines=['# HR, CFS and Hub: fixes for review','',
        '**Review only. No changes, PRs or merges have been made to these three repositories.** The openBIM consumer fixes are handled separately in its own repository. Existing native completion checks correctly reject many of these incomplete sources; a failed check is evidence to resolve, not a reason to weaken the check.','',
        '## HR and CFS shared export pipeline','',
        '1. **Separate generated review feedback from consumed source inputs.** `steel_engine/bim_export.py:148` currently discovers root JSON files broadly. It tracks `workflow_review.json`, so publishing independent review feedback after an export makes an unchanged physical design appear stale. Proposed fix: exclude generated feedback by default while retaining explicit `bim_inputs.json` dependencies, and retain strict checks for real configuration/helper changes. Acceptance: feedback-only changes do not invalidate the export; changing cfg, calculation records, input geometry or explicitly declared inputs does.',
        '   Affected cases: '+', '.join(feedback)+'. Genuine changed inputs still requiring a new export: '+', '.join(c+' / '+n for c,n in real_inputs)+'.','',
        '2. **Generate connection occurrences from selected design records through tested assembly helpers.** Job-authored physical declarations still omit the selected connection family, plates/components, or specified fastener quantities. Proposed fix: reusable, deterministic constructors for each supported designed assembly, with source record IDs, actual joints, profiles, orientations and exact quantities. Unsupported or delegated components must stay explicit information requests. Existing validators remain enforced. Do not place generic hardware at every analysis node or guess quantities from a family name.',
        '   Missing selected families: '+cases('connection_selected_family')+'. Missing selected components: '+cases('connection_selected_components')+'. Fastener quantities: '+cases('connection_fastener_quantity')+'.',
        '   Acceptance: each selected assembly has all required constituent occurrences; linked design parameters and placed counts agree; changing a design regenerates only the corresponding occurrences.','',
        '3. **Make assembly generation idempotent and justify joint exceptions.** Repeated routines currently leave duplicate parts; joint exemptions can also use unrecognised categories. Proposed fix: occurrence keys based on assembly/joint/part role, replacement rather than append-on-rerun, and typed dispositions with a supported reason and applicable connected members. Never silently delete legitimate coincident plates without resolving their ownership.',
        '   Duplicate parts: '+cases('connection_duplicate_parts')+'. Invalid disposition kinds: '+cases('joint_disposition_kind')+'. Acceptance: exporting the same job twice yields the same physical occurrences, with no duplicate IDs or coincident duplicate hardware and no unexplained joint exceptions.','',
        '4. **Verify full solid clearance at architectural openings.** Workline clearance alone misses flanges, connection plates, washers and anchors intruding into openings. The independent IFC checks found CFS18 hardware in its overhead/personnel door clearances even though the current native package reports ready. Proposed fix: compare declared member and assembly solid envelopes against retained opening reservations, and report actual affected parts. Reposition or redesign interfaces in the owning job using its own engineering evidence; do not trim or move hardware in openBIM to hide a source error.',
        '   Acceptance: the CFS18 door-clearance regression passes with actual solid geometry, alongside existing workline tests. The full list of additional independent findings is below; individual screenings may require engineering review.','',
        '5. **Capture complete physical geometry in the same finalisation as the saved design.** HR9 and HR24 retain enough input to replay their model, but only reference geometry/incomplete mapping and failing or stale design provenance emerge. A successful model build does not establish a complete physical package. Proposed fix: require explicit physical member placement, primary/secondary framing, floor/roof panels, opening hosts and connection occurrence mappings before a required new-job export can be called ready. Use the producer job data, not the gold supplement recipes.',
        '   Acceptance: HR9/HR24 export their own complete geometry with independent input agreement and current native completion evidence. Do not promote captured analysis worklines to finished physical members. Physical panels must also declare their role: CFS28 supplies its roof planes but labels them generically as panel, so the IFC correctly retains them as proxies rather than guessing a roof class. Its purlin depth axes also require review. Geometry coverage and semantic classification are checked separately.',
        '   Surface comparisons also flag HR22, HR25, HR11, CFS7 and CFS6. Resolve the relationship between architectural finished surfaces, physical reference planes, declared thickness and legitimately added structural panels before changing coordinates. For example, HR22 has 3-inch surface offsets and footprint/void differences. The comparison establishes an unexplained difference, not that every additional structural panel is a design error.',
        '   HR11 declares twelve wall hosts with exactly the same bounds as their openings. openBIM now retains these as explicit boundary references instead of failing or filling the opening. Review whether they are intended reservation boundaries or incomplete wall-host declarations in HR.','',
        '6. **Record the actual producer revision and keep it distinct from a later exporter revision.** Existing saved packages have `producer_revision: null`; `exporter_revision` is often null as well. `steel_engine/bim_export.py:260` currently hardcodes the former and relies on an environment variable for the latter. Proposed fix: persist the installed native revision at design creation/finalisation and stamp the active exporter revision on export/replay. Preserve source and engine-file hashes; a replay must not relabel the old design as newly produced by the current engine.',
        '   Acceptance: a new job records both revisions; replay under another exporter retains the original producer identity and records the new exporter identity. Historical unknown producer revisions remain explicitly unknown.','',
        '7. **Publish consistent final output checkpoints.** HR33 has an otherwise ready physical export but its native sanity results are stale relative to cfg.py. Genuine helper-file changes also occur in CFS16/CFS29. Proposed fix: verify all final configuration/calculation/sanity/export fingerprints together before presenting job completion, and create a new checkpoint after any source edit. If analysis-affecting inputs changed, the native job must rerun the required analysis/checks; model-only replay cannot clear stale structural results.',
        '   Acceptance: no done/current output set mixes old sanity evidence with changed cfg or helper geometry. This review task did not rerun structural design or analysis.','',
        '## CFS-specific source correction','',
        '8. **Repair and prevent malformed joint-disposition declarations in CFS8.** Current own-input replay emits 368 schema errors because disposition records omit required `reason`. Its saved package also has invalid profile/joint references. Proposed fix: validate declarations at construction and provide typed helpers for dispositions and flat straps; resolve the actual job records and references. Do not remove the required reason or accept invalid profile geometry in the consumer.',
        '   Acceptance: CFS8 produces a schema-valid physical package, all referenced joints/profiles exist, the dispositions are justified, and then it passes the same IFC/input comparisons. Adding the reasons alone is not claimed to resolve all of its downstream geometry findings.','',
        '## Hub','',
        '9. **Update the embedded openBIM dependency after review.** `steltic_hub/catalog/steltic_userbuilding/pyproject.toml` is still pinned to openBIM commit `6958f8eb1b7d5293d5f047796659195ff2a75ec4`. The standalone openBIM fixes are merged through `b3a50f068a5b0401f47f1bd3ce958d009ef8e6db` (0.8.32, PRs #41/#42). Proposed fix: move the embedded pin to this reviewed openBIM release and verify stale-source rejection, provisional findings, fully voided panel references and import warning retention in User-designed building. The pin and installed Hub were deliberately left unchanged here.',
        '10. **Present run completion, source freshness, physical completeness and IFC exchange as separate statuses.** This audit found saved done statuses that no longer pass the current native gate. Proposed UX change: retain historical run status, show its producer version/checkpoint, and expose current validation separately; do not use schema-valid IFC or transport success as a complete-design badge. This is a proposed improvement, not a claim that Hub can independently certify missing engineering data.','',
        '## Case evidence','',
        '| Native finding | Affected case/run identities |','|---|---|']
    lines += ['| '+code+' | '+', '.join(sorted(values))+' |' for code,values in sorted(groups.items())]
    lines += ['','Independent architectural/geometry comparisons (updated as the sweep finishes):','']
    lines += ['- '+r['case']+': `'+r['code']+'` — ['+r['evidence_file']+']('+r['evidence_file']+').' for r in comparisons]
    lines += ['','## Missing production jobs','',f"{len(unavailable)} primary cases lack a saved configuration/calculation pair for replay: "+', '.join(unavailable)+'.',
        'These are availability gaps from the earlier stopped/incomplete queue, not demonstrated exporter bugs. Successful tests for those cases require actual producer job outputs. This audit did not resume the queue, use OpenRouter, redesign buildings or substitute the old supplemented gold models.','',
        'Suggested review order: source/checkpoint provenance; deterministic physical/connection assembly; architectural solid clearances and CFS8 schema repair; then the Hub pin/status presentation. Rerun affected own-output cases after approved producer fixes, and populate the unavailable cases separately.']
    (OUT/'upstream-fix-list.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(native_finding_groups=len(groups),feedback_stale=len(feedback),independent_findings=len(comparisons),unavailable=len(unavailable))))

if __name__=='__main__':main()
