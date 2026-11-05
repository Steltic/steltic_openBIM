import copy
from steltic_openbim.review_cfs6_floor_references import apply


def fixture():
    track=dict(id='T',kind='ordinary_track',axis=[[0,0,0],[96,0,0]],end_offsets=[[0,0,0],[0,0,0]])
    marker=dict(id='OLD',detail_ref=dict(id='review_cfs_floor'),member_ids=['T'],point=[48,0,0],
                design_record_ids=['source/floor'],source_record_selections=[dict(record_id='source/floor',clause='bearing')])
    packs=[dict(id='PACK'+str(i),detail_ref=dict(id='review_source_floor_block'),member_ids=['B'+str(i),'T'],
                point=[x,0,-5],parameters=dict(actual_source_floor=True),design_record_ids=['source/block'])
           for i,x in enumerate((8,88))]
    return dict(pilot='cfs6',members=[track],connections=[marker]+packs,changes=[])


def test_real_bound_bearing_packs_replace_an_unbound_mid_track_marker():
    model=fixture();apply(model)
    assert {c['id'] for c in model['connections']}=={'PACK0','PACK1'}
    for c in model['connections']:
        assert c['design_record_ids']==['source/block','source/floor']
        assert c['source_record_selections']==[dict(record_id='source/floor',clause='bearing')]
    assert {(r['end'],r['connection_id']) for r in model['connection_endpoint_links']}=={('start','PACK0'),('end','PACK1')}


def test_unbound_or_remote_hardware_cannot_remove_the_marker():
    for mode in ('unbound','remote'):
        model=fixture()
        for c in model['connections'][1:]:
            if mode=='unbound':c['member_ids']=['B','OTHER']
            else:c['point']=[48,0,-5]
        before=copy.deepcopy(model['connections']);apply(model)
        assert model['connections']==before


def test_nested_inner_track_uses_the_floor_packs_on_its_stitched_outer_ply():
    model=fixture()
    for c in model['connections'][1:]:c['member_ids'][-1]='OUTER'
    model['connections'] += [dict(id='STITCH'+str(i),detail_ref=dict(id='review_double_top_track'),
        member_ids=['T','OUTER'],point=[x,0,0],parameters=dict(purpose='stitch'),design_record_ids=[])
        for i,x in enumerate((4,92))]
    apply(model)
    assert 'OLD' not in {c['id'] for c in model['connections']}
    assert {(r['end'],r['connection_id']) for r in model['connection_endpoint_links']}=={('start','STITCH0'),('end','STITCH1')}


def test_compression_only_pack_does_not_claim_the_screwed_floor_selection():
    model=fixture();bearing=copy.deepcopy(model['connections'][1])
    bearing.update(id='BEARING',detail_ref=dict(id='review_chord_floor_pack'),parameters=dict(actual_chord_floor=True))
    model['connections'].append(bearing);apply(model)
    assert bearing['design_record_ids']==['source/block']
    assert bearing['source_context_records']==['source/floor']
    assert not bearing.get('source_record_selections')
    assert 'OLD' not in {c['id'] for c in model['connections']}


def test_bearing_only_cannot_replace_a_fastened_floor_marker():
    model=fixture()
    for c in model['connections'][1:]:
        c.update(detail_ref=dict(id='review_chord_floor_pack'),parameters=dict(actual_chord_floor=True))
    before=copy.deepcopy(model['connections']);apply(model)
    assert model['connections']==before
