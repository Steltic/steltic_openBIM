from steltic_openbim.design_pdf import plan_connections


def test_tall_column_does_not_put_base_and_roof_callouts_on_every_floor():
    column=dict(id='C',kind='column',level=1,axis=[[0,0,-120],[0,0,600]])
    connections=[dict(id=name,member_ids=['C'],point=[0,0,z],detail_ref=dict(id=family),drawing_ref=name)
                 for name,z,family in [('BASE',-120,'hr_column_base'),('F1',144,'hr_rbs_joint'),('F2',288,'hr_rbs_joint'),('ROOF',600,'hr_rbs_joint')]]
    model=dict(members=[column],connections=connections,levels=[(0,'BASE',0),(1,'L1',144),(2,'L2',288),(3,'ROOF',600)])
    for level,kind,want in [(0,'base','BASE'),(1,'floor','F1'),(2,'floor','F2'),(3,'roof','ROOF')]:
        assert [c['id'] for c in plan_connections(model,[column],level,kind)]==[want]
