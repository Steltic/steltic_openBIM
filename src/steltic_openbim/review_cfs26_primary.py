"""Actual source canopy frame plies and their through-web attachments.

Source sections, bolt groups and plate sizes are retained. Unspecified pipe
walls, washers, packing, cut positions and brace fit remain explicit A choices.
"""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .pilots.geometry import strips
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point

GLOBAL=([1,0,0],[0,1,0],[0,0,1])
CT=.1242;RT=.1017;BT=.0713
COL_HALF=3.5+CT/2
RAF_HALF=COL_HALF+RT
BRACE_HALF=RAF_HALF+BT


def prepare(b):
    if b.key!='cfs26':return
    # Source puts one rafter/brace channel on each column face. A close-spaced
    # generic back-to-back profile instead passed through the column interior.
    for label,half,t in [('2X1400S250-97',COL_HALF+RT/2,RT),('2X600S250-68',RAF_HALF+BT/2,BT)]:
        p=b.profiles[label];old=copy.deepcopy(p['components'])
        p['components'][0]['offset'][0]=-half;p['components'][1]['offset'][0]=half
        p.update(basis='S two selected channels, one on each actual receiving face; A exact ply fit',
                 fit_proposal='Source one-channel-per-face arrangement; A transverse brace outside the rafter webs, with column-end packs. Source capacity is not extended to these local fit choices.')
        b.changes.append(dict(kind='canopy_source_face_plies',profile_id=label,previous_components=old,components=copy.deepcopy(p['components'])))
    for m in b.members:
        if m['kind']=='column':
            m['axis'][0][2]=2.75;m['axis'][1][2]+=4.5
            m.update(basis='A',design_record_ids=['members/frame-col'],physical_fit_basis='S source box; A bottom at1.5in grout plus1.25in base, head4.5in above knee workpoint for source6in bolt square.')
        elif m['kind']=='rafter':m['design_record_ids']=['members/frame-raf']
        elif m['id'].startswith('F') and m['kind']=='knee_brace':
            m['design_record_ids']=['members/frame-kb']
            u=unit(sub(*axis(m)[::-1]));m['end_offsets']=[mul(u,-6),mul(u,6)]
            m['physical_fit_basis']='S3ft column drop /4ft rafter run and source sections. A6in end extensions place four source bolts at3in pitch with1.5in end distance.'


def apply(b):
    if b.key!='cfs26':return
    b.endpoint_links=getattr(b,'endpoint_links',[])
    lookup={m['id']:m for m in b.members};changed=set()
    for c in b.connections:
        f=c['detail_ref']['id'];m=lookup[c['member_ids'][0]]
        purpose=None
        if f=='review_portal_base' and m['kind']=='column':purpose='base'
        elif f=='review_canopy_knee':purpose='knee'
        elif f=='review_canopy_brace' and m['id'].startswith('F'):
            purpose='brace';end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']))
            frame=m['id'].split('-')[0];side=m['id'][-1]
            c['member_ids']=[m['id'],frame+'-C'+side if end==0 else frame+'-R0']
            c['parameters']['end']=end
        if purpose:
            c['detail_ref']={'id':'review_canopy_primary'}
            c['parameters']=dict(purpose=purpose,actual_canopy_primary=True,**({'end':c['parameters']['end']} if purpose=='brace' else {}))
            c['title']='CANOPY / SOURCE '+purpose.upper()+' ON ACTUAL MEMBERS';changed.add(c['id'])
            for mid in c['member_ids']:
                member=lookup[mid]
                if purpose=='base' and member['kind']=='column':end=0
                elif purpose=='brace' and mid==m['id']:end=c['parameters']['end']
                elif purpose=='knee' and member['kind']=='column':end=1
                else:continue
                b.endpoint_links.append(dict(member_id=mid,end='start' if end==0 else 'end',connection_id=c['id'],basis='Source through-web group on actual finite plies; A fit retained.'))
    # The source specifies rafter spacer blocks and No12 stitches at24in, plus
    # a transverse brace mid-length tie. Both need their own actual occurrences.
    for m in list(b.members):
        if m['kind']=='rafter':
            aa,dd=axis(m);u=unit(sub(dd,aa));length=math.dist(aa,dd)
            stations=[12+24*i for i in range(math.ceil((length-24)/24)+1)]
            for i,s in enumerate(stations):
                if s>length-6:continue
                b.connection(m['id']+'-STITCH'+str(i),'review_canopy_primary',add(aa,mul(u,s)),[m],['members/frame-raf'],
                    parameters=dict(purpose='stitch',actual_canopy_primary=True),title='CANOPY / SOURCE RAFTER SPACERS AND STITCHES')
        elif m['id'].startswith('F') and m['kind']=='knee_brace':
            aa,dd=axis(m);b.connection(m['id']+'-TIE','review_canopy_primary',mul(add(aa,dd),.5),[m],['members/frame-kb'],
                parameters=dict(purpose='brace_tie',actual_canopy_primary=True),title='CANOPY / SOURCE BRACE MID-LENGTH TIE')
        elif m['kind']=='column':
            aa,dd=axis(m);b.connection(m['id']+'-SEAMS','review_canopy_primary',mul(add(aa,dd),.5),[m],['members/frame-col'],
                parameters=dict(purpose='seams',actual_canopy_primary=True),title='CANOPY / CONTINUOUS SOURCE BOX SEAMS')
    b.note('CANOPY-PRIMARY','S:2x1400S350118 toe-to-toe column,2x1400S25097 rafter one channel per actual column web,2x600S25068 transverse brace, source base/knee/brace bolt and plate selections. Source rafter No12 stitches at24in and brace mid-length tie shown. A: exact separated ply placement,6in brace end extensions,0.1017in column-end packs, pipe OD/wall, washers, spacer blocks and local notches/access require verification. Original gold capacities do not verify the adopted fit. Column seam faces retain the nominal7in source designation; the sharp-corner profile envelope is7.1242in.')


def washers(a,label,q,n,dia):
    # Design envelopes deliberately omit clearance holes; source F436 governs
    # procurement. Separate washers avoid attributing every bolt to all rings.
    a.cylinder(label,q,n,dia*2,.125,'S F436 / A envelope','ASTM F436 hardened washer; A outer diameter and thickness envelope')


def pipe(a,label,q,n,length,description):
    pid='A-CANOPY-PIPE-OD1.05-T.113'
    a.profiles[pid]=dict(id=pid,family='chs',dimensions=dict(d=1.05,t=.113),basis='S3/4in pipe spacer; A OD/wall and exact cut length')
    return a.member(label,pid,q,add(q,mul(n,length)),y=[1,0,0] if abs(n[0])<.5 else [0,1,0],basis='S pipe / A fit',description=description,representation_role='assembly_component')


def through(a,label,pts,n,dia,near,far,joined,pipes=None):
    pipe_ids=[]
    for i,q in enumerate(pts):
        start=add(q,mul(n,near-.125));end=add(q,mul(n,far));w0=label+'-WA'+str(i);w1=label+'-WB'+str(i)
        washers(a,w0,start,n,dia);washers(a,w1,end,n,dia)
        a.parts[-2]['annotation_group']=label+'-WASHERS';a.parts[-1]['annotation_group']=label+'-WASHERS'
        a.fastener(label+str(i),[start],n,dia,far-near+.25,[*joined,w0,w1],
            f'S {dia:g}in A325-N through bolt and F436 washers; A exact grip and washer envelopes')
        a.parts[-1]['annotation_group']=label+'S'
        if pipes:
            lo,hi=pipes;pid=label+'-PIPE'+str(i);pipe(a,pid,add(q,mul(n,lo)),n,hi-lo,'Source3/4in hollow pipe spacer inside actual column; A exact OD/wall/cut length')
            a.parts[-1]['annotation_group']=label+'-PIPES';pipe_ids.append(pid)
    if pipe_ids:a.interfaces.append(dict(id=label+'-PIPE-BEARING',kind='compression_spacer',connects=[*pipe_ids,joined[0]],basis='S pipe / A contact fit',description='Each hollow spacer bears on the actual column inside faces; its own bolt passes through the bore.'))


def draw(ctx):
    purpose=ctx.params['purpose'];a=ctx.a
    a.title={'base':'CANOPY / SOURCE FIXED BASE','knee':'CANOPY / SOURCE THROUGH-BOX KNEE','brace':'CANOPY / SOURCE TRANSVERSE BRACE ENDS','stitch':'CANOPY / SOURCE RAFTER SPACERS','brace_tie':'CANOPY / SOURCE BRACE MID-LENGTH TIE','seams':'CANOPY / SOURCE CONTINUOUS BOX SEAMS'}[purpose]
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,math.dist(*axis(m))/2+1 if purpose=='seams' else 32)
    if purpose=='base':base(ctx)
    elif purpose=='knee':
        pts=[[x,0,z] for x in (-3,3) for z in (-3,3)]
        through(a,'KNEE',pts,[0,1,0],.75,-RAF_HALF,RAF_HALF,['M0','M1'],(-3.5+CT/2,3.5-CT/2))
        a.dim([-3,0,-3],[3,0,-3],'S6in bolt square',basis='S');a.section_axis=2;a.section_at=3
    elif purpose=='brace':brace(ctx)
    elif purpose in ('stitch','brace_tie'):stitch(ctx)
    else:
        col=next(v for v in a.parts if v['id']=='M0');lo,hi=col['bounds'][2]
        pid='A-CANOPY-SEAM-FILL';a.profiles[pid]=dict(id=pid,family='flat',dimensions=dict(width=CT,thickness=CT/2),basis='A sharp-corner filled groove envelope; source ER70S-6 weld')
        for side in (-1,1):
            label='SEAM-METAL'+str(side);xx=side*(7-CT/4)
            bead=a.member(label,pid,[xx,0,lo],[xx,0,hi],basis='S weld / A sharp-corner fill',description='ER70S-6 filled-flush source seam; A square groove envelope between actual flange tips',representation_role='assembly_component')
            bead['material_category']='weld'
            a.weld('SEAM'+str(side),[side*7,-CT/2,lo],[side*7,-CT/2,hi],['M0',label],kind='CJP',description='S continuous filled-flush flare V-groove seam on this7in face; shop GMAW ER70S-6 AWS D1.3. Exact preparation requires shop verification.')
        a.section_axis=2;a.section_at=0
    a.notes.append('Actual finite source members are extracted without substituting a generic receiver. All unstated washer/pipe/packing geometry is A. Source member and connection capacities have not been rerun for adopted cuts, spacers or access requirements.')


def base(ctx):
    a=ctx.a;origin=ctx.c['point'];z=-origin[2]
    a.box('CONCRETE',[-18,-14,z-24],[36,28,24],'A','A foundation envelope; original pier handoff governs',kind='concrete')
    a.box('GROUT',[-12,-8,z],[24,16,1.5],'S','S1.5in non-shrink grout')
    a.box('BASE',[-12,-8,z+1.5],[24,16,1.25],'S','S1.25x24x16in A572Gr50 base plate')
    for sign in (-1,1):
        yy=-COL_HALF-.5 if sign<0 else COL_HALF;pid='SIDE'+str(sign)
        a.box(pid,[-7,yy,z+2.75],[14,.5,18],'S','S PL1/2x14x18in base side plate; A exact set-out')
        for face in (yy,yy+.5):a.weld(pid+'-W'+str(face),[-7,face,z+2.75],[7,face,z+2.75],['BASE',pid],.375,description='S3/8in fillets both sides')
    through(a,'BASE-BOLT',[[x,0,z+2.75+h] for x in (-3,3) for h in (3,6,9,12)],[0,1,0],.75,-COL_HALF-.5,COL_HALF+.5,['M0','SIDE-1','SIDE1'],(-3.5+CT/2,3.5-CT/2))
    for i,(x,y) in enumerate(( (x,y) for x in (-10,10) for y in (-6,6))):
        pid='ANCHOR-WASHER'+str(i);a.box(pid,[x-1.25,y-1.25,z+2.75],[2.5,2.5,.25],'S plate washer / A envelope','Source welded plate washer; A2.5in square x1/4in')
        a.parts[-1]['annotation_group']='ANCHOR-WASHERS'
        a.weld(pid+'-W',[x-1.25,y-1.25,z+2.75],[x+1.25,y-1.25,z+2.75],['BASE',pid],.1875,basis='A',description='S washer welded; A3/16in fillet representation')
        a.fastener('ANCHOR'+str(i),[[x,y,z-18]],[0,0,1],.75,21,['CONCRETE','GROUT','BASE',pid],'S3/4in F1554Gr55 rod at x+/-10,y+/-6; A18in embedment, source pier handoff governs')
        a.parts[-1]['annotation_group']='ANCHORS'
    a.dim([-12,0,z+1.5],[12,0,z+1.5],'S24in base',basis='S');a.section_axis=2;a.section_at=z+8.75


def brace(ctx):
    a=ctx.a;m,h=ctx.ms;origin=ctx.c['point'];end=ctx.params['end'];u=unit(sub(*axis(m)[::-1]));into=1 if end==0 else -1
    # End extension is6in; source1.5in end distance and3in pitch locate the
    # four bolt centres around the original workpoint at +/-4.5,+/-1.5in.
    pts=[mul(u,into*s) for s in (-4.5,-1.5,1.5,4.5)];joined=['M0','M1']
    if end==0:
        for sign in (-1,1):
            yy=-RAF_HALF if sign<0 else COL_HALF;pid='PACK'+str(sign)
            a.box(pid,[-6,yy,-6],[12,RT,12],'A','A97mil pack between actual column web and outside brace channel');joined.append(pid)
    through(a,'BRACE',pts,[0,1,0],.625,-BRACE_HALF,BRACE_HALF,joined)
    a.section_axis=2;a.section_at=pts[0][2]
    a.dim(pts[0],pts[1],'S3in pitch',basis='S')
    a.notes.append('S four5/8in through bolts at3in pitch with1.5in end distance. A brace extends6in past each workpoint; column ends use97mil packs to match the brace outside the actual rafter webs. Hollow column/rafter gaps remain visible; source does not select an additional brace-end pipe spacer.')


def stitch(ctx):
    a=ctx.a;m=ctx.ms[0];p=ctx.p[m['profile_id']];comp=ctx.p[p['components'][0]['profile_id']];t=comp['dimensions']['t']
    half=abs(p['components'][0]['offset'][0]);inner=half-t/2;outer=half+t/2
    # A hollow RHS block spans the source separated channel pair. Its end
    # plates are contacted by the source No12 screws from each actual web.
    u=unit(sub(*axis(m)[::-1]));v=cross(u,[0,1,0]);depth=2.;length=3.;wall=.125
    for sign in (-1,1):
        yy=-inner if sign<0 else inner-wall;pid='BLOCK-END'+str(sign)
        verts=[add(mul(u,s),add([0,yy,0],mul(v,h))) for s,h in ((-length/2,-depth/2),(length/2,-depth/2),(length/2,depth/2),(-length/2,depth/2))]
        a.polygon(pid,verts,wall,basis='A',description='A1/8in hollow spacer block end')
    pid='A-CANOPY-SPACER-3X2X.125';a.profiles[pid]=dict(id=pid,family='rhs',dimensions=dict(h=depth,b=length,t=wall),basis='A hollow spacer block')
    a.member('BLOCK-RETURN',pid,[0,-inner+wall,0],[0,inner-wall,0],y=u,basis='A',description='A hollow spacer return,1/8in walls',representation_role='assembly_component')
    a.interfaces.append(dict(id='FORMED-SPACER',kind='welded_spacer',connects=['BLOCK-END-1','BLOCK-END1','BLOCK-RETURN'],basis='A',description='A hollow welded spacer block; corner weld sizes and capacity require verification'))
    for sign in (-1,1):
        pts=[add(mul(u,s),[0,sign*outer,0]) for s in (-.75,.75)]
        a.fastener('STITCH'+str(sign),pts,[0,-sign,0],.216,t+wall,['M0','BLOCK-END'+str(sign)],'S No12 stitches at24in on rafter; A two screws per web and hollow spacer' if ctx.params['purpose']=='stitch' else 'S mid-length brace tie; A twoNo12 screws per web and hollow spacer',basis='S' if ctx.params['purpose']=='stitch' else 'A',screw=True)
    a.dim(mul(u,-length/2),mul(u,length/2),'A3in spacer',basis='A')
    a.section_axis=0;a.section_at=0
