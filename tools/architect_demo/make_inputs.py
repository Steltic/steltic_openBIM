"""Create fictional architectural IFCs for the HR workflow demonstration.

Uses standard IFC4 entities, millimetres, swept slabs/walls and real void/fill
relationships. These are synthetic Revit-style exchange inputs, not Revit exports.
No structural members, member sections or connection sizes are supplied.
"""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
from shapely.geometry import box
from shapely.ops import unary_union

from steltic_openbim.ifc_export import property_set,schema_errors

FT=304.8
CASES=[
 dict(key='01_Office_SCBF',title='Five-storey glazed office',source='Ex1_SCBF_5levels.txt',
      x=[i*30 for i in range(6)],y=[i*30 for i in range(4)],levels=[0,15,28,41,54,67],
      regions=[dict(name='Office',rect=[0,0,150,90],levels=[0,15,28,41,54,67])],
      supplement='Fictional video criteria: SDS=1.0 g, SD1=0.60 g, S1=0.60 g, TL=8 s, Site Class D, Risk Category II, Ie=1.0, rho=1.3. ASCE 7-22 / AISC 360-22 / AISC 341-22. Five storeys: 15 ft then four at 13 ft; roof framing at 67 ft. Enclosed building. Architectural floor plates are gross coordination surfaces; stairs and lift fit-out are delegated inside the core and no additional structural floor void is requested in this demo. Select and design all structural sections and connections in HR. Architectural slab thickness is an envelope reservation, not a composite capacity calculation.'),
 dict(key='02_School_Zplan',title='Z-plan school with three roof heights',source='Ex16_IMF_3levels_Zplan_school.txt',
      x=[i*28 for i in range(8)],y=[i*28 for i in range(5)],levels=[0,12,24,26,36],
      regions=[dict(name='Classroom',rect=[0,0,84,56],levels=[0,12,24,36]),dict(name='Link',rect=[84,28,140,84],levels=[0,12,24]),dict(name='Gym',rect=[140,56,196,112],levels=[0,26])],
      supplement='Fictional video criteria: S1=0.20 g, TL=8 s; use the SDS, SD1, wind and loads in the brief. The shared Grid 4/B-C and Grid 6/C-D interfaces are connected building interfaces, not seismic joints. Do not introduce a floor across the gym at 12 ft or 24 ft. Gym interior Grid D columns are omitted. Architectural floor thicknesses reserve space only. Library stack loading is a separate zone as stated. Long-span gym framing is an HR/delegated engineering choice, not supplied by the architect.'),
 dict(key='03_Warehouse_Gable',title='Gabled warehouse with low shipping office',source='Ex31_Gable_warehouse_R3_unbalanced_snow_ponding.txt',
      x=[i*25 for i in range(9)],y=[-40,0,40,80],levels=[0,16,26,36],
      regions=[dict(name='Hall',rect=[0,0,200,80],levels=[0,26]),dict(name='Shipping office',rect=[50,-40,150,0],levels=[0,16])],
      supplement='Fictional video criteria: S1=0.10 g, TL=8 s; enclosed with dock doors closed for design wind. Four north dock openings 12 ft wide x 14 ft high at X=25,75,125,175 ft. Personnel entrances are shown. Office primary drain hydraulic head 2 in and overflow sill 4 in above finished roof are demo inputs; verify ponding and roof drainage explicitly. The architect IFC retains the true 26 ft eaves / 36 ft ridge and 16 ft office roof. If using the prescribed mean-height 31 ft analytical idealisation, retain the true sloped physical roof for drawings/IFC and record the mapping. Do not substitute the analysis flat roof for the architectural roof.'),
]


def create(case,folder,hr_repo):
    folder.mkdir(parents=True,exist_ok=True);m=ifcopenshell.file(schema='IFC4');serial=0
    def entity(cls,name,key=None,**kw):
        nonlocal serial
        serial+=1;e=ifcopenshell.api.root.create_entity(m,ifc_class=cls,name=name)
        e.GlobalId=ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL,'steltic-architect-demo:'+case['key']+':'+str(key or serial)).hex)
        for k,v in kw.items():setattr(e,k,v)
        return e
    def point(xyz):return m.create_entity('IfcCartesianPoint',Coordinates=tuple(float(v)*FT for v in xyz))
    origin=m.create_entity('IfcAxis2Placement3D',Location=point((0,0,0)))
    def place(e):e.ObjectPlacement=m.create_entity('IfcLocalPlacement',RelativePlacement=origin)
    project=entity('IfcProject',case['title'],'project')
    unit=ifcopenshell.api.unit.add_si_unit(m,unit_type='LENGTHUNIT',prefix='MILLI');ifcopenshell.api.unit.assign_unit(m,units=[unit])
    ctx=ifcopenshell.api.context.add_context(m,context_type='Model')
    body=ifcopenshell.api.context.add_context(m,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=ctx)
    site=entity('IfcSite','Fictional video site','site');building=entity('IfcBuilding',case['title'],'building')
    ifcopenshell.api.aggregate.assign_object(m,products=[site],relating_object=project)
    ifcopenshell.api.aggregate.assign_object(m,products=[building],relating_object=site)
    property_set(m,project,dict(Synthetic=True,Authoring='Steltic architectural demo generator; not an actual Autodesk Revit export',
        OriginalTestBrief=case['source'],Purpose='Architectural design intent before structural engineering',
        StructuralMemberSizes='Not supplied - HR to design',ConnectionDesign='Not supplied - HR to design'),name='Demo_Provenance')
    storeys={};contained={}
    for i,z in enumerate(case['levels']):
        s=entity('IfcBuildingStorey',('Ground' if z==0 else 'Datum '+str(z)+' ft'),'storey:'+str(z));s.Elevation=z*FT
        s.ObjectPlacement=m.create_entity('IfcLocalPlacement',RelativePlacement=m.create_entity('IfcAxis2Placement3D',Location=point((0,0,z))))
        ifcopenshell.api.aggregate.assign_object(m,products=[s],relating_object=building);storeys[z]=s;contained[z]=[]
    def solid(cls,name,ring,z,depth,storey,kind=None):
        e=entity(cls,name);place(e)
        curve=m.create_entity('IfcPolyline',Points=[point(p) for p in [*ring,ring[0]]])
        profile=m.create_entity('IfcArbitraryClosedProfileDef',ProfileType='AREA',OuterCurve=curve)
        item=m.create_entity('IfcExtrudedAreaSolid',SweptArea=profile,Position=m.create_entity('IfcAxis2Placement3D',Location=point((0,0,z))),ExtrudedDirection=m.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)),Depth=float(depth)*FT)
        rep=m.create_entity('IfcShapeRepresentation',ContextOfItems=body,RepresentationIdentifier='Body',RepresentationType='SweptSolid',Items=[item])
        ifcopenshell.api.geometry.assign_representation(m,product=e,representation=rep)
        if kind:e.PredefinedType=kind
        if cls!='IfcOpeningElement':contained[storey].append(e)
        return e
    def rectangle(cls,name,rect,z,depth,storey,kind=None):
        x0,y0,x1,y1=rect
        return solid(cls,name,[(x0,y0),(x1,y0),(x1,y1),(x0,y1)],z,depth,storey,kind)
    def surface(name,vertices,storey):
        e=entity('IfcSlab',name);e.PredefinedType='ROOF';place(e)
        # Thin architectural roof reservation, expressed in SI to the geometry API.
        top=[tuple(v*.3048 for v in p) for p in vertices];bottom=[(x,y,z-.1) for x,y,z in top]
        faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        rep=ifcopenshell.api.geometry.add_mesh_representation(m,context=body,vertices=[top+bottom],faces=[faces])
        ifcopenshell.api.geometry.assign_representation(m,product=e,representation=rep);contained[storey].append(e)
    grid=entity('IfcGrid','Architectural setting-out grid','grid');place(grid);grid.PredefinedType='RECTANGULAR'
    ux=[];vy=[]
    for label,x in enumerate(case['x'],1):
        ux.append(m.create_entity('IfcGridAxis',AxisTag=str(label),AxisCurve=m.create_entity('IfcPolyline',Points=[point((x,min(case['y'])-10,0)),point((x,max(case['y'])+10,0))]),SameSense=True))
    for index,y in enumerate(case['y']):
        label=chr(65+index)
        vy.append(m.create_entity('IfcGridAxis',AxisTag=label,AxisCurve=m.create_entity('IfcPolyline',Points=[point((min(case['x'])-10,y,0)),point((max(case['x'])+10,y,0))]),SameSense=True))
    grid.UAxes=ux;grid.VAxes=vy;contained[0].append(grid)
    for region in case['regions']:
        rect=region['rect'];levels=region['levels'];name=region['name']
        for i,z in enumerate(levels):
            if name=='Hall' and z==26:continue
            kind='BASESLAB' if i==0 else 'ROOF' if i==len(levels)-1 else 'FLOOR'
            rectangle('IfcSlab',name+' '+kind+' '+str(z)+' ft',rect,z-.5,.5,z,kind)
        for low,high in zip(levels,levels[1:]):
            space=rectangle('IfcSpace',name+' space '+str(low)+'-'+str(high)+' ft',rect,low,high-low,low)
            space.PredefinedType='INTERNAL'
            property_set(m,space,dict(Use=name,ClearOfInteriorColumns=(name in ('Gym','Hall')),StructuralSizing='By HR'),name='Architect_Intent')
    if case['key'].startswith('03'):
        surface('Hall south roof slope 3:12',[(0,0,26),(200,0,26),(200,40,36),(0,40,36)],26)
        surface('Hall north roof slope 3:12',[(0,40,36),(200,40,36),(200,80,26),(0,80,26)],26)
    # Exterior walls are the union of occupied wings at each height band. Shared
    # wing interfaces therefore remain open and no wall crosses the school link.
    heights=sorted({z for r in case['regions'] for z in r['levels']})
    for low,high in zip(heights,heights[1:]):
        active=[box(*r['rect']) for r in case['regions'] if r['levels'][0]<=low and r['levels'][-1]>=high]
        if not active:continue
        union=unary_union(active);polys=[union] if union.geom_type=='Polygon' else union.geoms
        for poly in polys:
            pts=list(poly.exterior.coords)
            for a,b in zip(pts,pts[1:]):
                dx,dy=b[0]-a[0],b[1]-a[1];length=(dx*dx+dy*dy)**.5
                if length<1e-6:continue
                ux,uy=dx/length,dy/length;nx,ny=-uy*.35,ux*.35
                ring=[(a[0]+nx,a[1]+ny),(b[0]+nx,b[1]+ny),(b[0]-nx,b[1]-ny),(a[0]-nx,a[1]-ny)]
                wall=solid('IfcWall','Exterior wall '+str(low)+' ft',ring,low,high-low,low,'NOTDEFINED')
                dock_wall=case['key'].startswith('03') and low==0 and abs(a[1]-80)<.1 and abs(b[1]-80)<.1
                n=4 if dock_wall else max(1,round(length/28))
                for k in range(n):
                    station=(k+.5)*length/n;cx,cy=a[0]+ux*station,a[1]+uy*station
                    dock=case['key'].startswith('03') and low==0 and abs(cy-80)<.1 and abs(uy)<.1
                    if case['key'].startswith('03') and not dock and low>0:continue
                    door=low==0 and (k==0 or dock);width=12 if dock else 4 if door else min(14,length/n-4)
                    sill=0 if door else 3;opening_height=14 if dock else 8 if door else min(6,high-low-4)
                    if opening_height<=0 or sill+opening_height>high-low:continue
                    def aperture(thickness):
                        return [(cx-ux*width/2-uy*thickness,cy-uy*width/2+ux*thickness),(cx+ux*width/2-uy*thickness,cy+uy*width/2+ux*thickness),(cx+ux*width/2+uy*thickness,cy+uy*width/2-ux*thickness),(cx-ux*width/2+uy*thickness,cy-uy*width/2-ux*thickness)]
                    opening=solid('IfcOpeningElement','Door opening' if door else 'Window opening',aperture(.6),low+sill,opening_height,low,'OPENING')
                    filling=solid('IfcDoor' if door else 'IfcWindow',('Dock door' if dock else 'Entrance' if door else 'Window')+' '+str(low)+' ft',aperture(.08),low+sill,opening_height,low)
                    filling.OverallHeight=opening_height*FT;filling.OverallWidth=width*FT
                    ifcopenshell.api.feature.add_feature(m,feature=opening,element=wall)
                    ifcopenshell.api.feature.add_filling(m,opening=opening,element=filling)
    # Gable end wall triangles above the eaves (architectural cladding surfaces).
    if case['key'].startswith('03'):
        for x in (0,200):
            e=entity('IfcWall','Gable end above eaves');place(e)
            rep=ifcopenshell.api.geometry.add_mesh_representation(m,context=body,vertices=[[(x*.3048,0,26*.3048),(x*.3048,80*.3048,26*.3048),(x*.3048,40*.3048,36*.3048)]],faces=[[(0,1,2)]])
            ifcopenshell.api.geometry.assign_representation(m,product=e,representation=rep);contained[26].append(e)
    # Spaces decompose storeys; ordinary products use containment.
    for z,items in contained.items():
        spaces=[e for e in items if e.is_a('IfcSpace')];other=[e for e in items if not e.is_a('IfcSpace')]
        if spaces:ifcopenshell.api.aggregate.assign_object(m,products=spaces,relating_object=storeys[z])
        if other:ifcopenshell.api.spatial.assign_container(m,products=other,relating_structure=storeys[z])
    path=folder/'architect.ifc'
    m.header.file_name.name=path.name;m.header.file_name.originating_system='Steltic synthetic architectural IFC - NOT Autodesk Revit'
    m.header.file_description.description=('Fictional architectural coordination model for a video demonstration; no structural sizing supplied.',)
    m.write(str(path));errors=schema_errors(path)
    if errors:raise ValueError(errors[:5])
    assert not any(m.by_type(cls) for cls in ('IfcBeam','IfcColumn','IfcMember','IfcMechanicalFastener','IfcPlate'))
    brief=(hr_repo/'test_buildings'/case['source']).read_text(encoding='utf-8')
    brief='FICTIONAL VIDEO DEMONSTRATION - not a construction project.\n\n'+brief+'\n\n'+case['supplement']+'\n'
    (folder/'job_brief.txt').write_text(brief,encoding='utf-8')
    (folder/'source_manifest.json').write_text(json.dumps(dict(case=case['key'],source_test=case['source'],synthetic=True,actually_exported_from_revit=False,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),ifc_schema='IFC4',member_sections_supplied=False,connection_design_supplied=False),indent=2))
    return dict(case=case['key'],products=len(m.by_type('IfcProduct')),ifc_bytes=path.stat().st_size)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--hr-repo',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    for case in CASES:print(json.dumps(create(case,args.output/case['key'],args.hr_repo)),flush=True)
