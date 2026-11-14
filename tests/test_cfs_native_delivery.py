"""Native CFS delivery (drawings + IFC + self-check) and composite projects.

The fixture is a real two-part project exported by the Steltic CFS engine: a shop on special bolted moment
frames (portal kind, hollow columns) and a free-standing strap-braced mezzanine (wall kind), bound as one
project with a seismic joint.  One delivery is made per test session; the mutation tests then damage one
artifact at a time and expect the certificate to fail on the check that owns that agreement.
"""
import json
import shutil
import zipfile
from pathlib import Path

import pytest

pytest.importorskip('reportlab')
pytest.importorskip('pypdf')
pytest.importorskip('ifcopenshell')

from steltic_openbim import cfs_composite, cfs_delivery, cfs_delivery_verification

FIXTURE = Path(__file__).parent / 'fixtures' / 'cfs_native_ex18.zip'


@pytest.fixture(scope='module')
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp('cfs_native')
    with zipfile.ZipFile(FIXTURE) as z:
        z.extractall(root / 'jobs')
    out = root / 'delivery'
    result = cfs_composite.deliver(root / 'jobs' / 'CFS_Ex18', out, root / 'jobs')
    return dict(root=root, jobs=root / 'jobs', out=out, result=result)


def failed(cert):
    return {c['name'] for c in cert['checks'] if not c['passed']}


def test_parts_and_project_pass(project):
    out = project['out']
    assert project['result']['passed'] is True
    cert = json.loads((out / 'delivery_certificate.json').read_text(encoding='utf-8'))
    assert cert['schema'] == 'steltic.cfs_composite_certificate' and cert['passed'] is True
    assert [c['name'] for c in cert['checks']] == ['parts_certified', 'report_contains_parts', 'drawings_contain_parts', 'model_contains_parts', 'interface_matches_model']
    assert all(c['checked'] > 0 for c in cert['checks'])
    for part in cert['parts']:
        assert part['passed'] is True and len(part['checks']) == 10 and all(k['passed'] and k['checked'] > 0 for k in part['checks'])
    for name in ('drawings.pdf', 'model.ifc', 'parts/A/drawings.pdf', 'parts/B/model.ifc'):
        assert (out / name).stat().st_size > 10000


def test_project_model_is_one_project_with_every_part_tagged(project):
    import ifcopenshell
    f = ifcopenshell.open(str(project['out'] / 'model.ifc'))
    assert len(f.by_type('IfcProject')) == 1 and f.by_type('IfcProject')[0].Name == 'CFS_Ex18'
    assert len(f.by_type('IfcBuilding')) == 2
    merged = cfs_delivery_verification.read_ifc(project['out'] / 'model.ifc', part_key=True)
    parts = {key[1] for key in merged['products']}
    assert parts == {'A', 'B'}
    columns_a = [p for (cls, part, sid), p in merged['products'].items() if part == 'A' and cls == 'IfcColumn']
    assert len(columns_a) == 58 and all(p['props']['Section'] == 'HSS12X12X1/2' for p in columns_a)       # hollow columns of the bolted frames


def test_hollow_column_and_bolted_joint_are_drawn_and_checked(project):
    model = json.loads((project['out'] / 'parts' / 'A' / 'cfs_drawing_model.json').read_text(encoding='utf-8'))
    titles = [s['title'] for s in model['sheets']]
    assert any('bolted moment connection' in t for t in titles) and any(t.startswith('Portal frame elevation') for t in titles)
    source = json.loads((project['out'] / 'parts' / 'A' / 'source.json').read_text(encoding='utf-8'))
    families = {p['family'] for p in source['physical']['profiles']} if isinstance(source['physical']['profiles'], list) else {p['family'] for p in source['physical']['profiles'].values()}
    assert 'rhs' in families


def reverify_part(project, tmp_path, part, mutate_job=None, mutate_delivery=None):
    job = tmp_path / 'job'
    shutil.copytree(project['jobs'] / ('CFS_Ex18_%s' % part), job)
    delivery = tmp_path / 'delivery'
    shutil.copytree(project['out'] / 'parts' / part, delivery)
    if mutate_job:
        mutate_job(job)
    if mutate_delivery:
        mutate_delivery(delivery)
    return cfs_delivery_verification.verify(delivery, job)


def test_part_report_value_change_is_caught(project, tmp_path):
    def mutate(job):
        calc = json.loads((job / 'design' / 'calc_package_cfs.json').read_text(encoding='utf-8'))
        row = next(r for r in calc['wall_lines'] if isinstance(r.get('DC'), (int, float)))
        text = (job / 'report.html').read_text(encoding='utf-8')
        token = '>%.2f<' % row['DC']
        assert token in text
        (job / 'report.html').write_text(text.replace(token, '>0.11<'), encoding='utf-8')
    cert = reverify_part(project, tmp_path, 'B', mutate_job=mutate)
    assert cert['passed'] is False and 'report_matches_design_records' in failed(cert)


def test_part_ifc_material_change_is_caught(project, tmp_path):
    def mutate(delivery):
        text = (delivery / 'model.ifc').read_text(encoding='utf-8')
        assert 'ASTM A500 Grade C' in text
        (delivery / 'model.ifc').write_text(text.replace('ASTM A500 Grade C', 'ASTM A36 plate'), encoding='utf-8')
    cert = reverify_part(project, tmp_path, 'A', mutate_delivery=mutate)
    assert cert['passed'] is False and {'source_binding', 'ifc_members_match_model'} <= failed(cert)


def test_part_calculation_change_after_export_is_caught(project, tmp_path):
    def mutate(job):
        p = job / 'design' / 'calc_package_cfs.json'
        calc = json.loads(p.read_text(encoding='utf-8'))
        calc['members'][0]['section'] = 'HSS10X10X1/2'
        p.write_text(json.dumps(calc), encoding='utf-8')
    cert = reverify_part(project, tmp_path, 'A', mutate_job=mutate)
    assert cert['passed'] is False and 'source_binding' in failed(cert)


def recheck_project(project, tmp_path, mutate):
    jobs = tmp_path / 'jobs'
    shutil.copytree(project['jobs'], jobs)
    out = tmp_path / 'delivery'
    shutil.copytree(project['out'], out)
    mutate(jobs, out)
    return cfs_composite.verify(out, jobs / 'CFS_Ex18', jobs)


def test_project_set_out_change_is_caught(project, tmp_path):
    def mutate(jobs, out):
        p = jobs / 'CFS_Ex18' / 'design' / 'composite.json'
        m = json.loads(p.read_text(encoding='utf-8'))
        m['parts'][1]['origin_in'][1] += 6.0                      # the mezzanine declared 6 in. nearer the end frame than it is modelled
        p.write_text(json.dumps(m), encoding='utf-8')
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and {'model_contains_parts', 'interface_matches_model'} <= failed(cert)


def test_project_gap_stated_larger_than_modelled_is_caught(project, tmp_path):
    def mutate(jobs, out):
        p = jobs / 'CFS_Ex18' / 'design' / 'composite.json'
        m = json.loads(p.read_text(encoding='utf-8'))
        m['interface']['clear_gaps'][0]['stated_in'] = 18.0
        p.write_text(json.dumps(m), encoding='utf-8')
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and 'interface_matches_model' in failed(cert)


def test_project_gap_below_required_separation_is_caught(project, tmp_path):
    def mutate(jobs, out):
        p = jobs / 'CFS_Ex18' / 'design' / 'composite.json'
        m = json.loads(p.read_text(encoding='utf-8'))
        for g in m['interface']['clear_gaps']:
            g['required_in'] = 14.0
        p.write_text(json.dumps(m), encoding='utf-8')
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and 'interface_matches_model' in failed(cert)


def test_project_report_without_a_part_is_caught(project, tmp_path):
    def mutate(jobs, out):
        p = jobs / 'CFS_Ex18' / 'report.html'
        text = p.read_text(encoding='utf-8')
        cut = text.index("<hr class='part'><p class='part'>PART B")
        p.write_text(text[:cut] + '</body></html>', encoding='utf-8')
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and {'parts_certified', 'report_contains_parts'} <= failed(cert)


def test_project_drawing_set_missing_a_sheet_is_caught(project, tmp_path):
    def mutate(jobs, out):
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(str(out / 'drawings.pdf'))
        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if i != 7:
                writer.add_page(page)
        with (out / 'drawings.pdf').open('wb') as stream:
            writer.write(stream)
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and 'drawings_contain_parts' in failed(cert)


def test_project_model_missing_a_product_is_caught(project, tmp_path):
    def mutate(jobs, out):
        import ifcopenshell
        f = ifcopenshell.open(str(out / 'model.ifc'))
        f.remove(f.by_type('IfcColumn')[0])
        f.write(str(out / 'model.ifc'))
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and 'model_contains_parts' in failed(cert)


def test_part_changed_after_binding_is_caught(project, tmp_path):
    def mutate(jobs, out):
        p = jobs / 'CFS_Ex18_B' / 'report.html'
        p.write_text(p.read_text(encoding='utf-8').replace('</body>', '<p>late edit</p></body>'), encoding='utf-8')
    cert = recheck_project(project, tmp_path, mutate)
    assert cert['passed'] is False and 'parts_certified' in failed(cert)


def test_cfs_delivery_refuses_other_modules(tmp_path):
    job = tmp_path / 'job'
    (job / 'design').mkdir(parents=True)
    (job / 'design' / 'bim_package.json').write_text(json.dumps(dict(module='HR', building_id='X')), encoding='utf-8')
    with pytest.raises(ValueError, match='CFS packages only'):
        cfs_delivery.deliver(job, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_clear_gap_geometry():
    a = [([0.0, 0.0, 0.0], [12.0, 12.0, 288.0])]
    b = [([24.0, -50.0, 0.0], [500.0, 50.0, 240.0])]
    assert cfs_composite.clear_gap(a, b, 'x') == pytest.approx(12.0)
    assert cfs_composite.clear_gap(a, [([6.0, -50.0, 0.0], [500.0, 50.0, 240.0])], 'x') == pytest.approx(-6.0)       # overlap is a clash
    assert cfs_composite.clear_gap(a, [([24.0, 40.0, 0.0], [500.0, 90.0, 240.0])], 'x') is None                      # not facing
    assert cfs_composite.clear_gap(a, [([24.0, 40.0, 0.0], [500.0, 90.0, 240.0])], 'x', projected=True) == pytest.approx(12.0)
