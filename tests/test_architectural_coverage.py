import copy,json
from pathlib import Path
from steltic_openbim.bim_contract import validate


def test_consumer_rechecks_bound_source_even_when_producer_claims_ready():
    package=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())
    reference=dict(basis='Original architectural input, inches',source_ifc_sha256='a'*64,
        levels=[dict(level=0,name='Ground',elevation_in=0),dict(level=1,name='Roof',elevation_in=120)],grids=[])
    package['architectural_input']=dict(schema='steltic.architectural_input',version=1,source_file='architect.ifc',source_ifc_sha256='a'*64,
        reference_system=reference,openings=[dict(source_ifc_guid='door-source',name='Door',bounds_in=[[24,60],[-1,1],[0,84]],host_wall_guids=['wall-source'])])
    package['reference_system']=copy.deepcopy(reference)
    package['reference_system']['levels'].pop()
    package['physical']['members'].append({**package['physical']['members'][0],'id':'duplicate'})
    before=copy.deepcopy(package)
    findings=validate(package)
    assert {'architectural_levels','architectural_openings','duplicate_physical_members'} <= {f['code'] for f in findings}
    assert package==before
