from steltic_openbim.assembly_pdf import projection


def test_facing_view_places_outer_gusset_in_front_without_moving_elevation():
    scene=dict(front_axes=[0,2],section_axis=2)
    front,_=projection(scene,'front')
    other,_=projection(dict(scene,front_depth_sign=-1),'front')
    for p in ([2,3,4],[2,3.25,4]):assert front(p)[:2]==other(p)[:2]
    # Painter order is descending depth. At +Y the outer plate is painted last.
    assert other([2,3.25,4])[2]<other([2,3,4])[2]
    a,_=projection(scene,'section');b,_=projection(dict(scene,front_depth_sign=-1),'section')
    assert a([2,3,4])==b([2,3,4])
