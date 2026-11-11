"""Form a checked knife/clevis beam hinge and remove its clear steel gaps from the full member."""
import math
import re
from .assembly_templates import NUMBER, number
from .connection_cuts import drill_joined_plates
from .pilots.model import add, sub, dot, unit


def draw(ctx,face):
    records={r['id']:r['data'] for r in ctx.package['design_records']}
    found=[]
    for rid in ctx.c.get('design_record_ids',[]):
        row=records[rid];text=row.get('components','')
        knife=re.search(r'knife plate '+NUMBER+r' in at the hole, width '+NUMBER+r' in, extension '+NUMBER+r' in',text,re.I)
        clevis=re.search(r'two clevis plates '+NUMBER+r' in welded to the beam end \('+NUMBER+r' in fillets\)',text,re.I)
        pin=re.search(NUMBER+r' in dia\. pin \(([^,;)]+)',text,re.I)
        if not (knife and clevis and pin):continue
        rows=row.get('checks',[])
        count=next((re.search(r'total length '+NUMBER+r' in',r['limit_state']) for r in rows if 'clevis plates to beam web/flanges' in r.get('limit_state','')),None)
        moment=next((r.get('Mu_kipin') for r in rows if 't/4 + gap + tclevis/2' in r.get('limit_state','')),None)
        force=next((r.get('Ru_kip') for r in rows if 'pin' in r.get('limit_state','') and 'in double shear' in r['limit_state']),None)
        bore=re.search(r'pin hole '+NUMBER+r'\s*(?:=|in)',text,re.I);flange_gap=re.search(NUMBER+r' in clear gap at the flanges',text,re.I)
        if not (count and bore and flange_gap and moment and force):raise ValueError('Selected beam hinge lacks a checked bore, side clearance, weld length or flange gap')
        kt,w,a=(number(v) for v in knife.groups());ct,size=(number(v) for v in clevis.groups());diam=number(pin[1]);hole=number(bore[1])
        raw_gap=2*float(moment)/float(force)-kt/4-ct/2;gap=round(raw_gap*64)/64
        if gap<0 or abs(gap-raw_gap)>.001:raise ValueError('No unique resolved hinge side clearance at the reported force precision')
        found.append((kt,w,a,ct,size,diam,hole,pin[2].strip(),number(count[1]),number(flange_gap[1]),gap,rid))
    if not found:return False
    if len({r[:-1] for r in found})!=1:raise ValueError('Conflicting selected beam hinge records at '+ctx.c['id'])
    kt,w,extension,ct,size,diam,hole,alloy,total,flange_gap,gap,rid=found[0];s=ctx.p[ctx.pid]['dimensions'];d,b,tf,tw=(s[k] for k in ('d','bf','tf','tw'));height=d-2*tf
    if not 0<diam<hole<min(height,w) or w>height or kt+2*gap+2*ct>=b:raise ValueError('Selected pin or ply footprint does not fit the beam hinge')
    a=ctx.a;z=-d/2;end_length=total/4;stub=ctx.n(r'beam stub '+NUMBER+r' in',22);px=face+stub+flange_gap/2
    knife_start=max(face+2,face+stub-max(10,hole+extension));beam_start=face+stub+flange_gap;beam_full=beam_start+end_length
    a.member('M2',ctx.pid,[face,0,z],[knife_start,0,z],description='Intact column-side beam stub')
    a.member('M3',ctx.pid,[beam_full,0,z],[beam_full+15,0,z],description='Intact connected beam beyond the inserted clevis')
    for component,x,end in (('STUB',knife_start,face+stub),('BEAM',beam_start,beam_full)):
        for i,z0 in enumerate((-d,-tf)):
            a.box(component+str(i),[x,-b/2,z0],[end-x,b,tf],'S','Actual beam flange over its cut-back web; selected clear gap between flange ends')
    a.box('KNIFE',[knife_start,-kt/2,z-w/2],[px+hole/2+extension-knife_start,kt,w],'S','Selected centred knife thickness, breadth at the hole and clear end extension').update(thickness=kt)
    for j,sgn in enumerate((-1,1)):
        y=kt/2+gap if sgn>0 else -kt/2-gap-ct;role='CLEVIS'+str(j);out=y+ct if sgn>0 else y
        begin=px-hole/2-max(diam,extension);a.box(role,[begin,y,-d+tf],[beam_full-begin,ct,height],'S','Selected clevis ply drilled through its actual parallel faces').update(thickness=ct)
        for name,flange,z0 in (('WC'+str(j),'BEAM1',-tf),('WC'+str(j)+'-B','BEAM0',-d+tf)):
            a.weld(name,[beam_start,out,z0],[beam_full,out,z0],[role,flange],size,basis='S',description='Outer-face clevis-to-flange fillet; one of four finite source runs')
    g=a.fastener('PIN',[[px,-kt/2-gap-ct,z]],[0,1,0],diam,kt+2*gap+2*ct,['CLEVIS0','KNIFE','CLEVIS1'],f'{diam:g} in {alloy} pin in double shear; source 3-ply grip')
    g.update(functional_kind='pin',selected_material=alloy);drill_joined_plates(a,g,hole,'S checked diametral pin-hole clearance')
    a.weld('WK',[knife_start,0,z-w/2],[knife_start,0,z+w/2],['KNIFE','M2'],kind='CJP',description='Selected knife to stub-web CJP over actual common steel')
    for key,za in (('WS-TOP',-tf/2),('WS-BOT',-d+tf/2)):
        a.weld(key,[face,-b/2,za],[face,b/2,za],['M1','M2'],kind='CJP',basis='A',description='Fitted connection of intact stub flange to its column')
    a.weld('WS-WEB',[face,0,-d+tf],[face,0,-tf],['M1','M2'],kind='CJP',basis='A',description='Fitted connection of intact stub web to its column')
    a.section_at=px;a.dim([px,0,z-w/2],[px,0,z+w/2],'Selected knife width at hole',basis='S')
    a.dim([px+hole/2,0,z],[px+hole/2+extension,0,z],'Selected clear end extension',basis='S',offset=40)
    a.notes.append(f'S: {diam:g} in pin, {hole:g} in holes, {gap:g} in side clearance, {flange_gap:g} in flange gap and four {size:g} in clevis fillets totalling {total:g} in. A: stub and clevis tip outlines are fitted to those selections.')
    ctx.c.setdefault('parameters',{})['selected_hinge_member_cuts']={'source_record_id':rid,'receiver':'M3','axis_elevation':z,'full_section_width_in':b+2.,'removed_intervals_in':[[0.,face],[knife_start,beam_full]],'steel_replacement':'STUB0, STUB1, BEAM0, BEAM1 replace the interrupted full-width rolled profile'}
    return True


def bind_cuts(c,frame,members,drawing_members=None):
    spec=c.get('parameters',{}).get('selected_hinge_member_cuts')
    if not spec:return
    from .bim_assemblies import transformed
    mid=frame['bindings'][spec['receiver']];m=members[mid];ends=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
    u=unit(sub(ends[1],ends[0]));length=math.dist(*ends);cid=c['id'];slots=[s for s in m.get('slots',[]) if s.get('connection_id')!=cid]
    for a,b in spec['removed_intervals_in']:
        pts=[transformed([x,0,spec['axis_elevation']],frame) for x in (a,b)]
        stations=[dot(sub(p,ends[0]),u) for p in pts]
        if any(math.dist(p,add(ends[0],[v*s for v in u]))>.02 for p,s in zip(pts,stations)) or min(stations)<-.02 or max(stations)>length+.02:raise ValueError('Selected hinge cut is off the actual beam axis '+cid)
        lo,hi=sorted(max(0,min(length,s)) for s in stations)
        if hi-lo>1e-7:
            slots.append(dict(section_axis=0,centre_in=0.,width_in=spec['full_section_width_in'],start_in=lo,end_in=hi,connection_id=cid,source='Source beam hinge interruption, separately modelled steel flanges and pin plates'))
    m['slots']=slots
    if drawing_members is not None:drawing_members[mid]['slots']=list(slots)
