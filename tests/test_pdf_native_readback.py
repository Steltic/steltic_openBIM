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
