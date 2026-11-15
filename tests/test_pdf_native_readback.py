import json
from pathlib import Path

from steltic_openbim.drawing_workflow import initial_state
from steltic_openbim.ifc_export import export_drawing
from steltic_openbim.pdf_verification import verify_dimensions
from steltic_openbim.physical_pdf import generate


def test_ordinary_physical_drawing_uses_return_ifc_as_dimension_evidence(tmp_path):
    source=Path(__file__).parent/'fixtures/synthetic_bim_package.json'
    p=json.loads(source.read_bytes())
    state=initial_state(p,1)
    manifest=generate(p,state,tmp_path)
    assert manifest['representation']=='source_physical_geometry'
    for name,value in [('source',p),('state',state)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value))
    export_drawing(tmp_path,tmp_path/'model.ifc')
    result=verify_dimensions(tmp_path)
    assert result['passed'],result
    moved=tmp_path/'exported_model.ifc'
    (tmp_path/'model.ifc').rename(moved)
    assert verify_dimensions(tmp_path,ifc_path=moved)['passed']
    actual=[r for r in manifest['dimensions'] if (r.get('source') or {}).get('kind')=='native_envelope']
    assert actual
    actual[0]['source']['connection']='absent'
    (tmp_path/'drawing_manifest.json').write_text(json.dumps(manifest))
    assert not verify_dimensions(tmp_path,ifc_path=moved)['passed']


def test_setback_frame_section_dimensions_only_the_levels_its_members_occupy(tmp_path,monkeypatch):
    """A column line that stops at the setback carries its own level chain and passes the read-back."""
    import steltic_openbim.physical_pdf as physical_pdf
    p=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    levels=[0,144,288,432,576]
    p['layout_evidence']={'levels_in':levels}
    def member(name,kind,a,b):
        return dict(p['physical']['members'][0],id=name,kind=kind,axis=[a,b],local_y=[0,1,0])
    p['physical']['members']+=[member('tower-1','column',[0,0,0],[0,0,576]),member('tower-2','column',[120,0,0],[120,0,576]),
                               member('low-3','column',[240,0,0],[240,0,144]),member('low-beam','beam',[120,0,144],[240,0,144])]
    def deliver(folder):
        folder.mkdir()
        state=initial_state(p,1)
        manifest=generate(p,state,folder)
        for name,value in [('source',p),('state',state)]:
            (folder/(name+'.json')).write_text(json.dumps(value))
        export_drawing(folder,folder/'model.ifc')
        chains={}
        for row in manifest['dimensions']:
            if (row.get('source') or {}).get('kind')=='levels':
                chains.setdefault(row['sheet'],[]).append([q[2] for q in row['model_points']])
        return chains,verify_dimensions(folder)
    chains,result=deliver(tmp_path/'fixed')
    assert result['passed'],result
    spans=[list(s) for s in zip(levels,levels[1:])]
    assert sorted(map(sorted,chains.values()))==[[[0,144]],spans,spans,spans]
    assert physical_pdf.section_level_spans(levels,(0,144))==[(0,144)]
    assert physical_pdf.section_level_spans(levels,(140,300))==[(0,144),(144,288),(288,432)]
    # The read-back is the judge: the former whole-building chain on the low section still fails it.
    monkeypatch.setattr(physical_pdf,'section_level_spans',lambda all_levels,extent:list(zip(all_levels,all_levels[1:])))
    chains,result=deliver(tmp_path/'former')
    assert not result['passed'] and 'outside printed crop' in json.dumps(result)
