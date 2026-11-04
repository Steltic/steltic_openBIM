"""Independent architectural and physical checks of a newly designed IFC return.

These are exchange/model-data acceptance checks, not structural certification.
No old design, drawing supplement or source IFC object is injected into a result.
"""
import argparse,collections,hashlib,json,math,re,sys,time
from pathlib import Path
import numpy as np
import ifcopenshell.util.element
from shapely.geometry import Polygon
from shapely.ops import unary_union

from audit_sources import ROOT,OUT
sys.path.insert(0,str(ROOT/'work/repos/steltic_openBIM/src'))
from steltic_openbim.ifc_handoff import top_surfaces,grids
from steltic_openbim.ifc_import import build_review,open_model,metadata
from steltic_openbim.source_worklines import physical_view
from steltic_openbim.ifc_export import opening_boundary
from steltic_openbim.bim_contract import validate
from audit_sources import save,read,sha
import os
sys.path.insert(0,str(ROOT/"work/stage13"))
from geometry_checks import opening_solid_clashes,sideways_gravity_members,overlapping_constituents,part_dimension_consistency,member_design_record_sections,connection_occurrence_coverage,scheduled_connection_coverage,scheduled_anchor_spacing,reviewed_fastener_quantities


def plane_groups(surfaces):
    groups=[]
    for surface in surfaces:
        pts=np.asarray(surface['boundary_m'],dtype=float);normal=np.zeros(3)
        for a,b in zip(pts,np.roll(pts,-1,axis=0)):normal+=np.cross(a,b)
        length=np.linalg.norm(normal)
        if length<1e-10:raise ValueError('Degenerate source surface')
        normal/=length
        if normal[2]<0:normal=-normal
        distance=-float(np.dot(normal,pts[0]))
        poly=Polygon(pts[:,:2],[[p[:2] for p in ring] for ring in surface.get('holes_m',[])])
        if not poly.is_valid:raise ValueError('Invalid surface polygon')
        match=next((g for g in groups if np.linalg.norm(g['normal']-normal)<1e-6 and abs(g['distance']-distance)<1e-5),None)
        if match is None:
            match=dict(normal=normal,distance=distance,polygons=[]);groups.append(match)
        match['polygons'].append(poly)
    for group in groups:group['polygon']=unary_union(group.pop('polygons'))
    return groups


def segment_box(a,b,bounds):
    bounds=np.asarray(bounds,dtype=float).copy();normal=int(np.argmin(bounds[:,1]-bounds[:,0]))
    for k in range(3):
        if k!=normal:bounds[k,0]+=.005;bounds[k,1]-=.005
    lo,hi=0.,1.
    for k,(low,high) in enumerate(bounds):
        delta=b[k]-a[k]
        if abs(delta)<1e-10:
            if a[k]<low or a[k]>high:return False
        else:
            t0,t1=sorted(((low-a[k])/delta,(high-a[k])/delta));lo=max(lo,t0);hi=min(hi,t1)
            if hi<lo:return False
    return hi-lo>1e-6


def polyline_distance(first,second):
    """Symmetric 3D vertex-to-segment distance plus total-length difference."""
    first=np.asarray(first,dtype=float);second=np.asarray(second,dtype=float)
    if len(first)<2 or len(second)<2:return float('inf')
    def distance(points,line):
        start=line[:-1];delta=np.diff(line,axis=0);denom=(delta*delta).sum(axis=1)
        keep=denom>1e-18;start,delta,denom=start[keep],delta[keep],denom[keep]
        if not len(start):return float('inf')
        values=[]
        for point in points:
            t=np.clip(((point-start)*delta).sum(axis=1)/denom,0,1)
            values.append(float(np.linalg.norm(point-start-t[:,None]*delta,axis=1).min()))
        return max(values,default=0.)
    length=lambda p:np.linalg.norm(np.diff(p,axis=0),axis=1).sum()
    return max(distance(first,second),distance(second,first),abs(float(length(first)-length(second))))


def check(key,variant='replay'):
    row=read(OUT/key/'source_audit.json');dest=OUT/key/('exchange_'+variant)
    source=OUT/key/('source.json' if variant=='saved' else 'replay/bim_package.json')
    package=read(source);physical=physical_view(package)
    source_sha=package.get('reference_system',{}).get('source_ifc_sha256')
    candidates=list((ROOT/'outputs/workflow_fresh_61').glob('*/architectural_geometry.json'))
    candidates+=list((ROOT/'outputs/workflow_six').glob('*/architectural_geometry.json'))
    matched=[]
    for file in candidates:
        try:
            value=read(file)
            if value.get('source_sha256')==source_sha:matched.append((file,value))
        except (ValueError,AttributeError):pass
    if not matched:
        result=dict(key=key,status='unverifiable_input',reason='No original architectural handoff matches the source package identity.')
        save(dest/'architectural_comparison.json',result);return result
    geometry_file,geometry=matched[0];folder=geometry_file.parent
    path=dest/'returned.ifc';returned=read(dest/'returned_review.json')
    model=open_model(path);issues=[];checks=[];scope=[]
    def result(code,passed,evidence):
        checks.append(dict(code=code,passed=bool(passed),evidence=evidence))
        if not passed:issues.append(dict(code=code,evidence=evidence))
    result('own_output_binding',sha(source)==read(dest/'result.json')['package_sha256'],dict(physical_supplements_supplied=False,source_package_sha256=sha(source)))
    current_findings=validate(package)
    result('complete_native_physical_export',package['readiness']['status']=='ready' and not current_findings,dict(stored_readiness=package['readiness'],current_contract_findings=current_findings))
    result('return_fully_rendered',returned['counts']['unrendered']==0,returned['counts'])
    source_guids={o['guid'] for o in geometry['doors_windows']}
    source_opening_ids={o['id'] for o in physical.get('openings',[]) if o.get('source_ifc_guid') in source_guids}
    export_report=read(dest/'source_export.json')
    opening_warnings=[w for w in export_report.get('warnings',[]) if w.get('id') in source_opening_ids]
    result('architectural_opening_export_geometry',not opening_warnings,dict(unresolved_opening_warnings=opening_warnings))
    # A structural discipline return is compared with the elevated framing
    # scope. Ground/host slabs remain architectural context, explicitly listed.
    ground=min(s['elevation_m'] for s in geometry['storeys'])
    expected_surfaces=[]
    for source_surface in geometry['surfaces']:
        context='EXISTING' in source_surface['name'].upper() and key=='cfs29'
        planar=source_surface['top_surfaces']
        base=bool(planar) and all(abs(p[2]-ground)<1e-5 for s in planar for p in s['boundary_m'])
        if context or base:
            scope.append(dict(guid=source_surface['guid'],name=source_surface['name'],role='architectural_context',reason='Existing host outside the new mezzanine design' if context else 'Ground/host slab outside elevated steel framing comparison'))
        else:
            scope.append(dict(guid=source_surface['guid'],name=source_surface['name'],role='required_structural_coordination'))
            expected_surfaces.extend(planar)
            result('recoverable_input_surface_'+source_surface['guid'],bool(planar),dict(name=source_surface['name']))
    # A producer can supply the correct roof geometry with an untyped 'panel'
    # kind. Check geometry independently of that IFC classification failure.
    panel_ids={p['id'] for p in physical.get('panels',[])}
    actual_surfaces=[];untyped=[]
    for obj in returned['objects']:
        props=obj.get('properties',{}).get('Steltic_Coordination',{})
        typed=obj['ifc_class'] in ('IfcSlab','IfcSlabStandardCase','IfcRoof')
        if not typed and props.get('SourceId') not in panel_ids:continue
        surfaces=top_surfaces(obj);actual_surfaces.extend(surfaces)
        if surfaces and not typed:untyped.append(dict(source_id=props.get('SourceId'),ifc_class=obj['ifc_class']))
    result('floor_roof_panel_classification',not untyped,dict(untyped_horizontal_or_sloped_panels=untyped,method='Panel geometry is compared even when the source did not declare its floor/roof role; role omission is reported separately.'))
    expected=plane_groups(expected_surfaces);actual=plane_groups(actual_surfaces);differences=[]
    for group in expected:
        matches=[g for g in actual if np.linalg.norm(g['normal']-group['normal'])<1e-5 and abs(g['distance']-group['distance'])<.005]
        poly=group['polygon'];coverage=unary_union([g['polygon'] for g in matches])
        delta=poly.symmetric_difference(coverage).area
        if delta>max(.001,poly.area*1e-6):differences.append(dict(plane=[*group['normal'].tolist(),group['distance']],input_area_m2=poly.area,changed_area_m2=delta,matched_planes=len(matches)))
    result('floor_roof_planes_footprints_voids',not differences,dict(required_plane_groups=len(expected),returned_plane_groups=len(actual),differences=differences,plane_distance_tolerance_m=.005))
    # Unexpected returned horizontal/sloped surfaces are recorded too: otherwise
    # a new floor across a gym or courtyard could escape one-way containment.
    extra=[]
    for group in actual:
        if abs(group['normal'][2]-1)<1e-6 and abs(group['distance']+ground)<.005:continue
        matches=[g for g in expected if np.linalg.norm(g['normal']-group['normal'])<1e-5 and abs(g['distance']-group['distance'])<.005]
        if not matches:extra.append(dict(plane=[*group['normal'].tolist(),group['distance']],area_m2=group['polygon'].area))
    result('no_unrequested_floor_roof_planes',not extra,dict(extra_planes=extra))
    # Check actual source storeys, not every vertex elevation of a sloped roof.
    # A roof ridge is geometry, and is a datum only when the IFC declares it.
    missing=[s for s in geometry['storeys'] if not any(s['name']==v['name'] and abs(s['elevation_m']-v['elevation_m'])<.005 for v in returned['storeys'])]
    result('structural_datums_retained',not missing,dict(required=geometry['storeys'],returned=returned['storeys'],missing=missing))
    original_grids=geometry['grids'];actual_grids=grids(model,1.);missing_grids=[]
    for axis in original_grids:
        if not any(axis['label']==other['label'] and axis['direction']==other['direction'] and polyline_distance(axis.get('points_m',[]),other.get('points_m',[]))<.005 for other in actual_grids):missing_grids.append(axis)
    result('architectural_grid_locations',not missing_grids,dict(source_axes=len(original_grids),returned_axes=len(actual_grids),missing_or_changed=missing_grids,checks='labels, U/V/W family and full 3D polyline'))
    declared_sha=package.get('reference_system',{}).get('source_ifc_sha256')
    result('architectural_source_identity',declared_sha==geometry['source_sha256'],dict(expected=geometry['source_sha256'],declared=declared_sha))
    actual_openings=[]
    for opening in physical.get('openings',[]):
        vertices=np.asarray(opening_boundary(opening))*.0254
        actual_openings.append((opening,vertices,np.stack((vertices.min(axis=0),vertices.max(axis=0)),axis=1)))
    changed=[];clashes=[]
    axes=[];duplicates=[];seen={};unknown_placement=[]
    for member in physical['members']:
        if member.get('end_offsets',[[0,0,0],[0,0,0]]) is None or member.get('local_y') is None:
            unknown_placement.append(member['id']);continue
        points=(np.asarray(member['axis'])+np.asarray(member.get('end_offsets',[[0,0,0],[0,0,0]])))*.0254
        axes.append((member,points))
        token=(tuple(sorted(tuple(round(x,7) for x in p) for p in points)),member['profile_id'],tuple(member.get('local_y',[])))
        if token in seen:duplicates.append([seen[token],member['id']])
        seen[token]=member['id']
    result('physical_member_placement_defined',not unknown_placement,dict(unknown_member_ids=unknown_placement,method='Null offsets or orientation remain unknown; no zero offsets or local axes are invented for these checks.'))
    kinematic=dict(physical,members=[m for m in physical['members'] if m['id'] not in set(unknown_placement)])
    for opening in geometry['doors_windows']:
        box=np.asarray(opening['bounds_m']);normal=int(np.argmin(box[:,1]-box[:,0]));tangent=[k for k in range(3) if k!=normal]
        def error(bounds):return max(abs(float(bounds[normal].mean()-box[normal].mean())),float(np.abs(bounds[tangent,:]-box[tangent,:]).max()))
        candidates=sorted((error(bounds),item['id']) for item,_,bounds in actual_openings)
        if not candidates or candidates[0][0]>.005:changed.append(dict(guid=opening['guid'],name=opening['name'],nearest=candidates[:1]))
        for member,points in axes:
            if segment_box(*points,box):clashes.append(dict(opening_guid=opening['guid'],opening_name=opening['name'],member_id=member['id'],kind=member['kind']))
    result('door_window_boundaries',not changed,dict(source_count=len(geometry['doors_windows']),physical_count=len(actual_openings),changed=changed))
    result('door_window_workline_clearance',not clashes,dict(count=len(clashes),examples=clashes[:100],method='Strict opening bounds against physical worklines; separate from a solid clash or fabrication-fit check'))
    product_props={p.GlobalId:ifcopenshell.util.element.get_psets(p).get('Steltic_Coordination',{}) for p in model.by_type('IfcElement')}
    source_ids={guid:props.get('SourceId') for guid,props in product_props.items()}
    def identify_parts(findings):
        for clash in findings['clashes']:
            props=product_props.get(clash['product_guid'],{})
            for key,target in [('ConnectionId','connection_id'),('JointId','joint_id')]:
                if props.get(key) is not None:clash[target]=props[key]
        return findings
    solid_clashes=identify_parts(opening_solid_clashes(returned['objects'],geometry['doors_windows'],source_ids))
    result('door_window_solid_clearance',not solid_clashes['clashes'],solid_clashes)
    part_dimensions=part_dimension_consistency(physical)
    result('connection_part_dimensions',not part_dimensions['mismatches'],part_dimensions)
    record_links=member_design_record_sections(physical,package['design_records'])
    result('member_design_record_sections',not record_links['mismatches'],record_links)
    orientations=sideways_gravity_members(kinematic)
    orientations['unknown_placement_members_not_screened']=unknown_placement
    result('gravity_profile_orientation',not orientations['suspect_members'],orientations)
    constituents=overlapping_constituents(physical)
    result('built_up_constituents_separate',not constituents['overlaps'],constituents)
    result('no_duplicate_physical_occurrences',not duplicates,dict(count=len(duplicates),examples=duplicates[:100]))
    connections=physical.get('connections',[]);unlocated=[c['id'] for c in connections if c.get('scope')!='delegated' and not c.get('parts')]
    result('located_connection_occurrences',bool(connections) and not unlocated,dict(connections=len(connections),designed_without_parts=unlocated,delegated_interfaces=[c['id'] for c in connections if c.get('scope')=='delegated']))
    joint_coverage=connection_occurrence_coverage(kinematic,returned['objects'],ground/.0254)
    joint_coverage['unknown_placement_members_not_screened']=unknown_placement
    result('connection_occurrence_coverage',not joint_coverage['problems'],joint_coverage)
    if row['case']=='hr16':
        hits=[]
        for member,points in axes:
            mid=points.mean(axis=0)/.3048
            if 140+.01<mid[0]<196-.01 and 56+.01<mid[1]<112-.01 and .01<mid[2]<26-1:
                hits.append(member['id'])
        result('school_gym_clear_volume',not hits,dict(interior_members=hits))
    if row['case']=='cfs29':
        outside=[m['id'] for m,p in axes if np.any(p[:,:2]<-.005) or np.any(p[:,0]>60*.3048+.005) or np.any(p[:,1]>32*.3048+.005)]
        result('mezzanine_existing_host_excluded',not outside,dict(outside_new_platform_scope=outside))
        aisles=[dict(guid='brief-forklift-aisle-'+str(i+1),name=f'Forklift clear aisle X={a}..{b} ft',bounds_m=(np.array([[a,b],[0,32],[0,9.5]])*.3048).tolist()) for i,(a,b) in enumerate(((12,24),(36,48)))]
        clearance=identify_parts(opening_solid_clashes(returned['objects'],aisles,source_ids,shrink_all=True))
        result('mezzanine_clear_forklift_aisles',not clearance['clashes'],clearance)
    report=dict(case=key,module=row['module'],project=row['project'],variant=variant,original_input_evidence=str(geometry_file),checked_at=time.time(),status='passed' if not issues else 'needs_resolution',checks=checks,issues=issues,input_scope=scope,
        architectural_sha256=geometry['source_sha256'],architectural_handoff_sha256=sha(geometry_file),physical_package_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),return_ifc_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        counts={k:len(v) for k,v in physical.items() if isinstance(v,list)},
        limits=['Existing own-output package with independent geometry/data checks; not a fresh analysis, engineering certification or fabrication acceptance.','Base slabs and explicitly existing host context are outside the new elevated steel design comparison and remain in the original architectural IFC.','Input fixtures are synthetic; no native Revit application acceptance is claimed.'])
    save(dest/'architectural_comparison.json',report)
    print(json.dumps(dict(case=key,status=report['status'],issues=[i['code'] for i in issues])),flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');ap.add_argument('variant',nargs='?',default='replay');args=ap.parse_args();check(args.case,args.variant)
