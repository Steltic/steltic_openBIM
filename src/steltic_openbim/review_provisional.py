"""Clearly provisional views for source-bound schedule-only wall test cases."""
import copy,hashlib
from pathlib import Path
from .drawing_workflow import fingerprint,write_json
from .review_cases import scenario,build_model

def generate(package,state,dest):
    from .design_scenarios import available_scenario
    from .drawing_pdf import Sheets,AMBER
    key=available_scenario(package);spec=scenario(key);proposal=copy.deepcopy(state)
    # Author geometry for display without adopting answers or changing the live state.
    proposal['design_scenario']=dict(id=key,answers_sha256=fingerprint(spec['answers']),source_sha256=fingerprint(package),fictional=True,provisional=True)
    model=build_model(package,proposal);dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);sh=Sheets(package,state,dest)
    sh.start('G001','Proposed physical reconstruction / information requests')
    y=sh.H-120
    y=sh.wrap(42,y,'A - ILLUSTRATIVE PROPOSAL ONLY. This saved CFS wall job contains design schedules and wall-analysis evidence. The following physical arrangement is an authored proposal tied to this exact fictional test source. No test answers have been adopted. All arrangement dimensions remain TBD - resolve query.',1080,12,18)-24
    for r in state['requests']:
        sh.text(42,y,r['id']+' / '+r['status'],10,AMBER);y-=20;y=sh.wrap(42,y,r['proposal'],1080,9,13)-18
    for k in sorted({m['level'] for m in model['members']}):
        ms=[m for m in model['members'] if m['level']==k];panels=[p for p in model['panels'] if p['level']==k]
        sh.plot(f'S{100+k:03}',f'A PROPOSAL / level {k} / dimensions TBD',ms,panels,show_extent=False)
        sh.text(75,128,'ALL SUPPLEMENTARY ARRANGEMENT IS A PROPOSAL. TBD - resolve query. Source section schedules retained.',9,AMBER)
    for i,axes in enumerate(((0,2),(1,2)),201):
        sh.plot('S'+str(i),'A PROPOSAL / elevation / dimensions TBD',model['members'],axes=axes,show_extent=False)
    sh.c.save()
    report=dict(schema='steltic.drawing_set',revision=state['revision'],building_id=package['building_id'],source_model_sha256=fingerprint(package),decision_state_sha256=fingerprint(state),drawing_status='provisional',can_generate=True,open_requests=sum(not r['confirmed'] for r in state['requests']),sheets=sh.rows,dimensions=[],pdf_sha256=hashlib.sha256((dest/'drawings.pdf').read_bytes()).hexdigest(),artifacts=['drawings.pdf','drawing_manifest.json','information_requests.json'],omitted_dimensions_policy='All authored reconstruction positions remain TBD until explicit fictional adoption.')
    write_json(dest/'drawing_manifest.json',report);return report
