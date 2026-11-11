import numpy as np
import pytest
from shapely.affinity import scale
from shapely.geometry import box

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.connection_cuts import drill_joined_plates
from steltic_openbim.ordinary_pin_geometry import eye_stock, fit_to_support
from steltic_openbim.ordinary_pin_readback import measure
from test_brb_core_readback import as_mesh
from test_ifc_assembly_verification import export_readback


@pytest.mark.parametrize('damage',('clean','short_eye','wrong_breadth','wrong_gap','thin_clevis','short_grip',
    'missing_weld','repeated_weld','wrong_face','wrong_leg','one_unbacked_fillet','short_pin','eccentric_bore',
    'corner','missing_bar','thin_bar','too_narrow_bar','short_whitmore','short_restraint','long_thornton'))
def test_credited_bearing_plys_and_developed_face_fillets(tmp_path,damage):
    eye=eye_stock(19.,4.0625,10.,40.,.5625)
    assembly=Assembly('Composite pin fixture',{})
    def at(s,d,y):return [s,y,d]
    def addplate(key,shape,y,t):
        return assembly.polygon(key,[at(x,z,y) for x,z in list(shape.exterior.coords)[:-1]],t)
    corner=damage in ('corner','missing_bar','thin_bar','too_narrow_bar','short_whitmore','short_restraint','long_thornton')
    if corner:main=fit_to_support(eye,0.,[(-25,-22),(-25,22)],-19.625,28.2)
    else:main=fit_to_support(eye,0.,[(-45,-22),(-45,10),(-45,-22),(-17,-22)],-19.625,28.2)
    if damage=='one_unbacked_fillet':main=eye['cheek'].union(main.intersection(box(-100,-100,-eye['rear']+1,100)))
    addplate('GUSSET',main,-.625,1.25)
    parts={}
    paths={}
    for i,sg in enumerate((-1,1)):
        cheek=eye['cheek']
        if i==0 and damage=='short_eye':cheek=cheek.intersection(box(-60,-60,7,60))
        if i==0 and damage=='wrong_breadth':cheek=scale(cheek,yfact=.87,origin=(0,0))
        k=f'CHEEK{i}'
        addplate(k,cheek,.625 if sg>0 else -1.5,.875)
        for j,(a,b) in enumerate(eye['runs']):
            wid=f'W-{k}-{j}'
            if damage=='missing_weld' and i==0 and j==0:continue
            if damage=='repeated_weld' and i==0 and j==0:a,b=eye['runs'][1]
            y=sg*.625+(.25 if damage=='wrong_face' and j==0 and i==0 else 0.)
            paths[wid]=np.array([at(*a,y),at(*b,y)])
            parts[wid]=dict(kind='weld',connects=[k,'GUSSET'],parameters=dict(weld_type='fillet',
                size_in=.25 if damage=='wrong_leg' and i==0 else .5625))
        y=1.75 if sg>0 else -3.25
        if damage=='wrong_gap' and i==0:y+=.125
        addplate(f'CLEVIS{i}',box(-8,-8,35,8),y,1.25 if damage=='thin_clevis' and i==0 else 1.5)
    stock=[p['id'] for p in assembly.parts]
    if corner:
        from steltic_openbim.ordinary_pin_stiffeners import add_face_stock
        support=[dict(a=at(-25,-22,0),b=at(-25,22,0))]
        paths['WGC']=np.array([at(-25,-(9 if damage=='short_restraint' else 22),0),
                               at(-25,9 if damage=='short_restraint' else 22,0)])
        parts['WGC']=dict(kind='weld',parameters=dict(weld_type='fillet',size_in=.5),connects=['COLUMN','GUSSET'])
        if damage!='missing_bar':
            source=dict(width=3. if damage=='too_narrow_bar' else 6.,thickness=.5 if damage=='thin_bar' else .75,
                        primary_thickness=1.25,cheek_fillet=.5625,faces=2)
            add_face_stock(assembly,main,eye['cheek'],support,source,at,[(0,1,-25.)],[1.,0.,0.])
            for p in assembly.parts:
                if p.get('parameters',{}).get('free_edge_bar'):parts[p['id']]=dict(kind='plate',parameters=p['parameters'])
            for weld in assembly.welds:
                parts[weld['id']]=dict(kind='weld',parameters=dict(weld_type=weld['kind'],size_in=weld['size']),connects=weld['connects'])
                paths[weld['id']]=np.array([weld['a'],weld['b']])
    f=assembly.fastener('PIN',[[0,-3.25,0]],[0,1,0],4,3.8 if damage=='short_pin' else 6.5,stock,'Pin')
    if damage=='eccentric_bore':
        from steltic_openbim.connection_cuts import drill_plate
        for p in assembly.parts:
            drill_plate(p,[[.25 if p['id']=='CHEEK1' else 0,0,0]],[0,1,0],4.0625,'S')
    else:drill_joined_plates(assembly,f,4.0625,'S')
    for k in stock:parts[k]=dict(kind='plate')
    parts['PIN']=dict(kind='pin',connects=stock,parameters=dict(axis=[0,1,0]))
    meshes={p['id']:as_mesh(p['faces']) for p in assembly.parts}
    meshes['PIN']=as_mesh(f['faces'])
    rb=export_readback(tmp_path,meshes,{k:line for k,line in paths.items()},reader=True)
    actual={k:rb.member(k) for k in meshes}
    curves={k:rb.curves(k)[0] for k in paths}
    fields={key:[val] for key,val in {('gusset','width_at_hole_in'):19.,('gusset','extension_in'):10.,
        ('pin','diameter_in'):4.,('pin_hole','diameter_in'):4.0625,('cheek_plate','thickness_in'):.875,
        ('clevis_plate','thickness_in'):1.5,('clevis_plate','side_gap_in'):.25,
        ('pin','grip_in'):6. if damage=='short_grip' else 6.5,
        ('cheek_fillet','size_in'):.5625,('cheek_fillet','perimeter_each_in'):40.}.items()}
    if corner:
        fields.update({('gusset','whitmore_effective_width_in'):[60. if damage=='short_whitmore' else 28.2],
            ('gusset','whitmore_distance_beyond_cheek_in'):[8.],
            ('gusset','thornton_length_in'):[2. if damage=='long_thornton' else 6.],
            ('gusset_edge_stiffener','thickness_in'):[.75],('gusset_edge_stiffener','width_in'):[6.],
            ('gusset_edge_stiffener','faces'):[2]})
    counts,issues,facts=measure(parts,actual,curves,fields,[1,0,0])
    assert bool(issues)==(damage not in ('clean','corner')),(damage,issues)
    if damage=='clean':
        assert counts['actual_ordinary_pin_plies']==5
        assert counts['actual_ordinary_cheek_weld_groups']==2
        assert len(facts)==7
