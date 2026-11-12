from copy import deepcopy

import numpy as np
import pytest
from shapely import union_all
from shapely.geometry import Point, Polygon, box

from steltic_openbim.ifc_rafter_gussets import seat_web_edge


def test_knee_gusset_follows_web_cut_preserving_pin_and_two_full_welds():
    frame=dict(origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0])
    rod=dict(id='rod',assembly_instance=dict(frame,bindings={'HOST':'rafter'}),
             parameters=dict(into=[.8,.6,0]))
    knee=dict(assembly_instance=dict(frame,template_id='knee',bindings={'COLUMN':'column'}))
    hole=dict(point=[12,9,-.875],axis=[0,0,1],diameter_in=1.3125,basis='saved pin bore')
    gusset=dict(id='GUSSET',parameters=dict(thickness=.5,holes=[hole]),kind='plate')
    welds=[dict(id='GW'+str(i),kind='weld',connects=['HOST','GUSSET'],
                geometry=dict(type='polyline',points=[[.25,2,z],[.25,14,z]])) for i,z in enumerate((-.25,.25))]
    template=dict(id='rod-end',parts=[gusset,*welds,dict(id='PIN',kind='pin',parameters=dict(diameter=1.25))])
    original=deepcopy(template)
    ep=dict(id='EP',geometry=dict(faces=[[[-5,12,-10],[5,12,-10],[5,13,10],[-5,13,10]]]))
    got=seat_web_edge(template,rod,knee,dict(normal=[0,1,0],offset_in=13),
        {'rafter':dict(local_y=[1,0,0]),'column':dict(profile_id='W')},
        {'W':dict(dimensions=dict(bf=9))},{'knee':dict(parts=[ep])})
    assert original==template
    parts={p['id']:p for p in got['parts']}
    assert parts['PIN']==template['parts'][-1]
    assert parts['GUSSET']['parameters']['holes']==[hole]
    for i,weld in enumerate(welds):
        old=np.asarray(weld['geometry']['points'])
        new=np.asarray(parts['GW'+str(i)]['geometry']['points'])
        np.testing.assert_allclose(new[1]-new[0],old[1]-old[0])
        assert new[:,1].min()==pytest.approx(13)
    faces=[np.asarray(f) for f in parts['GUSSET']['geometry']['faces']]
    footprint=union_all([Polygon(f[:,:2]) for f in faces if np.allclose(f[:,2],.25)])
    assert footprint.intersection(box(-20,-20,5,13)).area<1e-6
    assert footprint.distance(Point(12,9))==pytest.approx(1.3125/2,abs=.005)
