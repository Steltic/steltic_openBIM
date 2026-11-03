"""Three synthetic architectural IFCs for CFS workflow regression.

Architectural envelopes, wall axes, openings and existing-host context only.
No designed CFS members or connection components are supplied.
"""
import argparse
import hashlib
import json
import uuid
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit

from steltic_openbim.ifc_export import property_set, schema_errors

FT = 304.8


class Architect:
    def __init__(self, key, title, levels, xs, ys):
        self.key = key
        self.m = ifcopenshell.file(schema='IFC4')
        self.count = 0
        self.storeys = {}
        self.contained = {}
        self.spaces = {}
        self.project = self.entity('IfcProject', title)
        unit = ifcopenshell.api.unit.add_si_unit(self.m, unit_type='LENGTHUNIT', prefix='MILLI')
        ifcopenshell.api.unit.assign_unit(self.m, units=[unit])
        self.ctx = ifcopenshell.api.context.add_context(self.m, context_type='Model')
        self.body = ifcopenshell.api.context.add_context(self.m, context_type='Model', context_identifier='Body', target_view='MODEL_VIEW', parent=self.ctx)
        self.axis_ctx = ifcopenshell.api.context.add_context(self.m, context_type='Model', context_identifier='Axis', target_view='GRAPH_VIEW', parent=self.ctx)
        site = self.entity('IfcSite', 'Fictional workflow site')
        building = self.entity('IfcBuilding', title)
        ifcopenshell.api.aggregate.assign_object(self.m, products=[site], relating_object=self.project)
        ifcopenshell.api.aggregate.assign_object(self.m, products=[building], relating_object=site)
        for z in levels:
            storey = self.entity('IfcBuildingStorey', 'Ground' if z == 0 else 'Datum ' + str(z) + ' ft')
            storey.Elevation = float(z) * FT
            self.place(storey, (0, 0, z))
            ifcopenshell.api.aggregate.assign_object(self.m, products=[storey], relating_object=building)
            self.storeys[z] = storey
            self.contained[z] = []
            self.spaces[z] = []
        grid = self.entity('IfcGrid', 'Architectural setting-out grid')
        self.place(grid)
        grid.PredefinedType = 'RECTANGULAR'
        grid.UAxes = [self.m.create_entity('IfcGridAxis', AxisTag=str(i + 1), AxisCurve=self.line([(x, min(ys)-10, 0), (x, max(ys)+10, 0)]), SameSense=True) for i, x in enumerate(xs)]
        grid.VAxes = [self.m.create_entity('IfcGridAxis', AxisTag=chr(65+i), AxisCurve=self.line([(min(xs)-10, y, 0), (max(xs)+10, y, 0)]), SameSense=True) for i, y in enumerate(ys)]
        self.contained[0].append(grid)

    def entity(self, cls, name):
        self.count += 1
        result = ifcopenshell.api.root.create_entity(self.m, ifc_class=cls, name=name)
        result.GlobalId = ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL, f'steltic-cfs-architect:{self.key}:{self.count}').hex)
        return result

    def point(self, xyz):
        return self.m.create_entity('IfcCartesianPoint', Coordinates=tuple(float(v)*FT for v in xyz))

    def line(self, points):
        return self.m.create_entity('IfcPolyline', Points=[self.point(p) for p in points])

    def place(self, product, xyz=(0, 0, 0)):
        product.ObjectPlacement = self.m.create_entity('IfcLocalPlacement', RelativePlacement=self.m.create_entity('IfcAxis2Placement3D', Location=self.point(xyz)))

    def solid(self, cls, name, ring, low, height, storey, kind=None):
        product = self.entity(cls, name)
        self.place(product)
        profile = self.m.create_entity('IfcArbitraryClosedProfileDef', ProfileType='AREA', OuterCurve=self.line([*ring, ring[0]]))
        shape = self.m.create_entity('IfcExtrudedAreaSolid', SweptArea=profile,
            Position=self.m.create_entity('IfcAxis2Placement3D', Location=self.point((0, 0, low))),
            ExtrudedDirection=self.m.create_entity('IfcDirection', DirectionRatios=(0., 0., 1.)), Depth=float(height)*FT)
        rep = self.m.create_entity('IfcShapeRepresentation', ContextOfItems=self.body, RepresentationIdentifier='Body', RepresentationType='SweptSolid', Items=[shape])
        ifcopenshell.api.geometry.assign_representation(self.m, product=product, representation=rep)
        if kind:
            product.PredefinedType = kind
        if cls == 'IfcSpace':
            self.spaces[storey].append(product)
        elif cls != 'IfcOpeningElement':
            self.contained[storey].append(product)
        return product

    def box(self, cls, name, rect, low, height, storey, kind=None):
        x0, y0, x1, y1 = rect
        return self.solid(cls, name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], low, height, storey, kind)

    def slab(self, name, rect, top, storey, kind='FLOOR', thickness=.5, existing=False):
        slab = self.box('IfcSlab', name, rect, top-thickness, thickness, storey, kind)
        property_set(self.m, slab, {'Scope': 'Existing host; context only' if existing else 'New structural design scope', 'ThicknessBasis': 'Architectural reservation; verify in structural design'}, name='Architect_Scope')
        return slab

    def roof(self, name, points, storey):
        roof = self.entity('IfcSlab', name)
        roof.PredefinedType = 'ROOF'
        self.place(roof)
        top = [tuple(v*.3048 for v in p) for p in points]
        bottom = [(x, y, z-.1) for x, y, z in top]
        faces = [(0,1,2,3), (7,6,5,4), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]
        rep = ifcopenshell.api.geometry.add_mesh_representation(self.m, context=self.body, vertices=[top+bottom], faces=[faces])
        ifcopenshell.api.geometry.assign_representation(self.m, product=roof, representation=rep)
        self.contained[storey].append(roof)
        return roof

    def wall(self, name, a, b, low, high, storey, bearing=None, external=True, existing=False):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = (dx*dx+dy*dy)**.5
        nx, ny = -.25*dy/length, .25*dx/length
        ring = [(a[0]+nx,a[1]+ny),(b[0]+nx,b[1]+ny),(b[0]-nx,b[1]-ny),(a[0]-nx,a[1]-ny)]
        wall = self.solid('IfcWall', name, ring, low, high-low, storey)
        rep = self.m.create_entity('IfcShapeRepresentation', ContextOfItems=self.axis_ctx, RepresentationIdentifier='Axis', RepresentationType='Curve3D', Items=[self.line([(*a,low),(*b,low)])])
        wall.Representation.Representations = tuple(wall.Representation.Representations)+(rep,)
        values = {'IsExternal': external}
        if bearing is not None:
            values['LoadBearing'] = bearing
        property_set(self.m, wall, values, name='Pset_WallCommon')
        property_set(self.m, wall, {'Scope': 'Existing host; context only' if existing else 'Architectural wall layout', 'AxisBasis': 'Architect-declared wall centre plane'}, name='Architect_Scope')
        return wall

    def opening(self, wall, name, center, axis, width, sill, height, storey, door=False):
        x, y = center
        def ring(t):
            return [(x-width/2,y-t),(x+width/2,y-t),(x+width/2,y+t),(x-width/2,y+t)] if axis=='x' else [(x-t,y-width/2),(x+t,y-width/2),(x+t,y+width/2),(x-t,y+width/2)]
        void = self.solid('IfcOpeningElement', name+' void', ring(.6), sill, height, storey, 'OPENING')
        filling = self.solid('IfcDoor' if door else 'IfcWindow', name, ring(.05), sill, height, storey)
        filling.OverallWidth = width*FT
        filling.OverallHeight = height*FT
        ifcopenshell.api.feature.add_feature(self.m, feature=void, element=wall)
        ifcopenshell.api.feature.add_filling(self.m, opening=void, element=filling)

    def save(self, folder, source, brief, supplements):
        folder.mkdir(parents=True, exist_ok=True)
        for z, products in self.contained.items():
            if products:
                ifcopenshell.api.spatial.assign_container(self.m, products=products, relating_structure=self.storeys[z])
            if self.spaces[z]:
                ifcopenshell.api.aggregate.assign_object(self.m, products=self.spaces[z], relating_object=self.storeys[z])
        property_set(self.m, self.project, {'Synthetic':True,'ActuallyExportedFromRevit':False,'OriginalTestBrief':source,
            'StructuralMemberSizes':'Not supplied - CFS to design','ConnectionDesign':'Not supplied - CFS to design'}, name='Demo_Provenance')
        self.m.header.file_name.originating_system = 'Steltic synthetic architectural IFC - NOT Autodesk Revit'
        self.m.header.file_description.description = ('Fictional architectural workflow regression; no structural member sizing supplied.',)
        path = folder/'architect.ifc'
        self.m.write(str(path))
        errors = schema_errors(path)
        if errors:
            raise ValueError(errors[:5])
        assert not any(self.m.by_type(cls) for cls in ('IfcBeam','IfcColumn','IfcMember','IfcMechanicalFastener','IfcPlate'))
        text = 'FICTIONAL WORKFLOW CHECK - not a construction project.\n\n'+brief+'\n\nEXPLICIT FICTIONAL ARCHITECTURAL / DESIGN INPUTS\n'+supplements+'\n'
        (folder/'job_brief.txt').write_text(text, encoding='utf-8')
        manifest = dict(case=self.key, module='CFS', source_test=source, synthetic=True, actually_exported_from_revit=False,
                        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), ifc_schema='IFC4', member_sections_supplied=False, connection_design_supplied=False)
        (folder/'source_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps(dict(case=self.key, products=len(self.m.by_type('IfcProduct')), bytes=path.stat().st_size)), flush=True)


def walls(output, repo):
    key='CFS_01_Walls';source='CFS_Ex1_ShearWall_4levels.txt'
    levels=[0, 10+8/12, 20+2/12, 29+8/12, 39+2/12]
    a=Architect(key,'Four-storey CFS residential wall building',levels,[0,32,64,96,128,160],[0,14,28,34,48,62])
    for i,z in enumerate(levels):
        a.slab(('Ground slab' if i==0 else 'Roof' if i==4 else 'Residential floor'),[0,0,160,62],z,z,'BASESLAB' if i==0 else 'ROOF' if i==4 else 'FLOOR')
    for low,high in zip(levels,levels[1:]):
        a.box('IfcSpace','Residential volume',[0,0,160,62],low,high-low,low,'INTERNAL')
        for y in (0,62):
            wall=a.wall('Exterior bearing wall', (0,y),(160,y),low,high,low,bearing=True)
            for i,x in enumerate((16,40,64,88,112,144)):
                a.opening(wall,'Entrance' if low==0 and i==0 else 'Residential window',(x,y),'x',4 if low==0 and i==0 else 8,low if low==0 and i==0 else low+3,7 if low==0 and i==0 else 4,low,door=low==0 and i==0)
        for x in (0,160):
            wall=a.wall('Exterior end wall',(x,0),(x,62),low,high,low,bearing=True)
            for y in (14,48):
                a.opening(wall,'End wall window',(x,y),'y',6,low+3,4,low)
        for y in (14,28,34,48):
            a.wall('Corridor bearing wall' if y in (28,34) else 'Mid-unit bearing wall',(0,y),(160,y),low,high,low,bearing=True,external=False)
        for x in (32,64,96,128):
            for y0,y1 in ((0,28),(34,62)):
                a.wall('Party wall / proposed shear line',(x,y0),(x,y1),low,high,low,bearing=None,external=False)
    supplement='Use AISI S100-16 (2020), S240-20, S400-20 and ASCE 7-22 unless the installed engine records a more current compatible basis. Fictional S1=0.45 g, TL=8 s, Site Class D, enclosed. The architect-declared bearing axes are Y=0,14,28,34,48,62 ft. Corridor clear band is between Y=28 and 34 ft; do not span a single joist across the 28-ft unit depth. Exterior openings are explicit; locate the required shear segments in the remaining wall piers and record their exact physical coordinates. Door/window headers and interrupted studs must follow these openings. Stair/lift fit-out is delegated and no additional structural floor void is requested for this regression. The base floor is slab on grade, not a suspended CFS floor. Source wall thicknesses and slab thicknesses are architectural reservations, not selected CFS sizes or verified capacity. Design and export all CFS studs, tracks, joists, headers, lateral segments and their connections; unresolved delegated components remain identified.'
    a.save(output/key,source,(repo/'test_buildings'/source).read_text(encoding='utf-8'),supplement)


def twin_gable(output,repo):
    key='CFS_17_TwinGable';source='CFS_Ex17_Portal_twospan_snow.txt'
    a=Architect(key,'Unequal twin-gable CFS municipal garage',[0,18,21,22.5],list(range(0,217,24)),[0,25,50,68,86])
    a.slab('Garage slab on grade',[0,0,216,86],0,0,'BASESLAB')
    for name,y0,z0,y1,z1 in [('West roof south slope',0,18,25,22.5),('West roof north slope',25,22.5,50,18),('East roof south slope',50,18,68,21),('East roof north slope',68,21,86,18)]:
        a.roof(name,[(0,y0,z0),(216,y0,z0),(216,y1,z1),(0,y1,z1)],18)
    south=a.wall('South garage wall',(0,0),(216,0),0,18,0,bearing=False)
    a.wall('North garage wall',(0,86),(216,86),0,18,0,bearing=False)
    for x in (0,216):
        a.wall('Garage end wall',(x,0),(x,86),0,18,0,bearing=False)
    for i,x in enumerate((18,60,102,144,186),1):
        a.opening(south,'Overhead garage door '+str(i),(x,0),'x',16,0,14,0,door=True)
    a.box('IfcSpace','Garage usable volume',[0,0,216,86],0,18,0,'INTERNAL')
    supplement='Fictional criteria: S1=0.12 g, TL=8 s, Site Class D, Risk Category II, Ie=1.0, enclosed with doors closed for wind. Roof cross-section is Y/Z=(0,18),(25,22.5),(50,18),(68,21),(86,18) ft, constant along X=0..216 ft. Y=50 is the VALLEY with an interior column line, not a ridge. The IFC X grid every 24 ft is an architectural reference; choose a feasible structural frame spacing within the source brief and disclose added frame lines. Five 16x14 ft doors are on Y=0 at X=18,60,102,144,186 ft; support these openings with a designed arrangement and do not place an uncoordinated post through a door. Base is slab on grade. Source roof/wall thicknesses are envelope reservations. Design the real sloped frame geometry and all secondary framing, discrete interior-column restraint and connections; retain the true roof in the physical export.'
    a.save(output/key,source,(repo/'test_buildings'/source).read_text(encoding='utf-8'),supplement)


def mezzanine(output,repo):
    key='CFS_29_Mezzanine';source='CFS_Ex29_Mezzanine_freestanding_existing.txt'
    a=Architect(key,'Independent CFS mezzanine in existing host',[0,12,24],[0,12,24,36,48,60],[0,16,32])
    a.slab('EXISTING host slab - context only',[-8,-8,68,40],0,0,'BASESLAB',existing=True)
    a.slab('NEW storage platform',[0,0,60,32],12,12)
    a.slab('EXISTING host roof - context only',[-8,-8,68,40],24,24,'ROOF',existing=True)
    for x in (-8,68):
        a.wall('EXISTING host wall - no structural attachment',(x,-8),(x,40),0,24,0,bearing=None,existing=True)
    for y in (-8,40):
        a.wall('EXISTING host wall - no structural attachment',(-8,y),(68,y),0,24,0,bearing=None,existing=True)
    a.box('IfcSpace','NEW platform usable volume',[0,0,60,32],12,8,12,'INTERNAL')
    a.box('IfcSpace','Delegated stair clearance reservation',[4,-7,22,-3.5],0,12,0,'INTERNAL')
    # Architectural railing envelopes and the pallet gate do not declare member sections.
    a.box('IfcRailing','North platform guardrail reservation',[0,31.9,60,32.1],12,3.5,12,'GUARDRAIL')
    for x in (0,60):
        a.box('IfcRailing','End platform guardrail reservation',[x-.1,0,x+.1,32],12,3.5,12,'GUARDRAIL')
    for x0,x1 in ((0,4),(7.5,52),(56,60)):
        a.box('IfcRailing','South platform guardrail reservation',[x0,-.1,x1,.1],12,3.5,12,'GUARDRAIL')
    a.box('IfcDoor','Pallet gate - architectural reservation',[52,-.08,56,.08],12,3.5,12)
    supplement='Fictional inputs: S1=0.14 g, TL=8 s, Site Class D, Risk Category II. NEW structural scope is only the 60x32 ft platform at Z=12 ft, posts/straps beneath it, edge guardrails and stated stair/gate reactions. The host slab at Z=0, roof at Z=24 and walls X=-8/68,Y=-8/40 ft are EXISTING CONTEXT; do not design a second building or attach new bracing to them. Host clear envelope is 76x48 ft, giving 8 ft nominal perimeter clearance before drift allowances. New posts use the 12x16 ft source grid; two 12-ft-wide forklift travel bands run in Y direction between X=12..24 and X=36..48 ft. Clear distance between post faces must satisfy the brief: adjust post centerlines or explicitly resolve any conflict before claiming aisle clearance. South stair access is X=4..7.5 ft on Y=0; its external stair reservation is shown. Design the platform edge for a fictional 3 kip dead and 5 kip live stair reaction at that access; stair flight engineering is delegated. Pallet gate is X=52..56 ft on Y=0. Guardrail top is 3 ft 6 in above platform. Existing slab capacity/anchors and host-building verification remain delegated with reactions and required clearances handed off. The platform slab thickness is an architectural envelope, not the final joist/deck design. Retain these scope distinctions in the physical BIM interfaces.'
    a.save(output/key,source,(repo/'test_buildings'/source).read_text(encoding='utf-8'),supplement)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--cfs-repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for build in (walls,twin_gable,mezzanine):
        build(args.output,args.cfs_repo)
