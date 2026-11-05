import json
import ifcopenshell
import ifcopenshell.util.element
from test_ifc import drawing_source
from steltic_openbim.drawing_workflow import initial_state,write_json
from steltic_openbim.ifc_export import export_drawing,export_import
from steltic_openbim.bim_contract import mapping_geometry_findings


def test_source_axis_mapping_and_physical_extents_survive_ifc_return(tmp_path):
    folder,p,_=drawing_source(tmp_path);m=p['physical']['members'][0]
    mapping=dict(axis_order=[1,0,2],basis='Synthetic span/station relabelling; unchanged inch units.')
    m['analysis_coordinate_mapping']=mapping
    p['analysis']=dict(nodes=[dict(id=name,point=[q[1],q[0],q[2]]) for name,q in zip(('a','b'),m['axis'])],
        elements=[dict(id='e1',node_ids=['a','b'])])
    m['analysis_ids']=['e1']
    m['end_offsets']=[[0,0,0],[3,0,0]]
    assert not mapping_geometry_findings(p)
    write_json(folder/'source.json',p);write_json(folder/'state.json',initial_state(p,1))
    path=tmp_path/'source.ifc';report=export_drawing(folder,path)
    returned=tmp_path/'return.ifc'
    result=export_import(path,returned,dict(source_sha256=report['sha256'],revision=2,status='built',options=dict(scope='all',units='auto')))
    assert not result['schema_errors']
    original=ifcopenshell.open(str(path));again=ifcopenshell.open(str(returned))
    assert all(again.by_id(e.id()).to_string()==e.to_string() for e in original)
    for model in (original,again):
        props=ifcopenshell.util.element.get_psets(model.by_type('IfcBeam')[0])['Steltic_Coordination']
        assert json.loads(props['AnalysisCoordinateMapping'])==mapping
        entity=json.loads(props['SourceEntity'])
        assert entity['axis']==m['axis'] and entity['end_offsets']==m['end_offsets']
        assert entity['analysis_ids']==m['analysis_ids']
