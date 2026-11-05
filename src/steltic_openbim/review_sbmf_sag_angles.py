"""Located CFS18 girt sag angles, with explicit adopted terminal restraints."""
from collections import defaultdict
from .review_receiver_geometry import extract
from .review_sbmf_girts import cross_section
from .review_cfs_occurrences import axis
from .pilots.model import add,sub,mul,dot,cross


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members};groups=defaultdict(list)
    for girt in b.members:
        if girt['id'].startswith(('SIDE-GIRT-','END-GIRT-')):groups[girt['id'].rsplit('-',1)[0]].append(girt)
    pid=b.custom('A-SBMF-SAG-L2X2X1-8','angle',dict(b=2,h=2,t=.125),basis='A sag-angle section absent from source selection')
    for label,girts in groups.items():
        g=girts[0];along=0 if g['id'].startswith('SIDE-') else 1;normal=1-along
        u=[1,0,0] if along==0 else [0,1,0];v=cross([0,0,1],u);axes=(u,v,[0,0,1])
        side=int(label.split('-')[2]);outward=-1 if side==0 else 1;sg=outward*v[normal]
        mid=[(a+d)/2 for a,d in zip(*g['axis'])];mid[2]=0
        beam=lookup[f'HEADER-{side}-{label.split("-")[-1]}'] if along==0 else lookup[f'FRAME-{0 if side==0 else 16}-BEAM']
        section=cross_section(beam,b.profiles,axes);bottom=min(q[2] for poly in section for q in poly)
        flanges=[]
        for poly in section:
            low,high=min(q[2] for q in poly),max(q[2] for q in poly)
            if abs(low-bottom)<1e-6 and .001<high-low<.3:
                aa,dd=min(q[1] for q in poly),max(q[1] for q in poly)
                if dd-aa>1:flanges.append((sg*(aa+dd)/2,(aa+dd)/2,high-low))
        if not flanges:raise ValueError('Sag angle lacks a finite beam bottom flange '+label)
        _,gauge,bt=max(flanges);gauge+=dot(sub(beam['axis'][0],mid),v)
        top=beam['axis'][0][2]+bottom
        heel=add(add(mid,mul(u,sg)),mul(v,-sg*4));a=[*heel[:2],.25];d=[*heel[:2],top-.25]
        rid='framing/girt-side-walls' if along==0 else 'framing/post-end-walls'
        sag=b.member(label+'-SAG',pid,'girt_restraint',a,d,3,'A',local_y=mul(u,-sg),records=[rid])
        for end,purpose,z in (('start','foot',0),('end','cap',top)):
            point=[*mid[:2],z];members=[sag] if purpose=='foot' else [sag,beam]
            c=b.connection(sag['id']+'-'+purpose.upper(),'review_sbmf_sag',point,members,[rid],
                parameters=dict(actual_sbmf_wall=True,purpose=purpose,along=along,sg=sg,beam_gauge_in=gauge,beam_flange_thickness_in=bt),basis='A')
            b.endpoint_links.append(dict(member_id=sag['id'],end=end,connection_id=c['id'],basis='Adopted continuous sag angle has an anchored base plate and welded cap bolted to the actual receiving beam bottom flange; terminal capacity remains unverified.'))
        for girt in sorted(girts,key=lambda m:m['axis'][0][2]):
            point=[*mid[:2],girt['axis'][0][2]]
            b.connection(girt['id']+'-MIDSPAN','review_sbmf_sag',point,[sag,girt],[rid],
                parameters=dict(actual_sbmf_wall=True,purpose='girt',along=along,sg=sg),basis='A')
            girt['midspan_restraint_member_id']=sag['id']
            girt['midspan_restraint_basis']='S midspan sag-angle condition (sidewall Lb75in); A continuous L2x2x1/8, two No12 to actual inner flange, anchored foot and real beam cap. Restraint stiffness/strength and support capacity require verification.'
            for mapping in girt.get('design_mapping_evidence',[]):
                if 'sag-angle' in mapping.get('basis',''):mapping['basis']='Exact source girt section,12.5ft workline span and6ft vertical stations; midspan sag angle and its real terminal connections are explicit adopted geometry.'
    b.changes.append(dict(kind='cfs18_girt_sag_angles',angles=len(groups),girt_attachments=sum(map(len,groups.values())),basis='S sidewall midspan sag-angle requirement. A L2x2x1/8 and endwall extension, two No12 per girt,1/4in welded plates, two1/2in cap bolts and four1/2in x4in anchors. Local and restraint capacity not certified.'))
    b.note('SBMF-GIRT-SAG-ANGLES','S: sidewall800S200-54 girts require a midspan sag angle for Lb75in. A:40 continuous L2x2x1/8 angles include the analogous end-wall girts, with two No12 screws at each actual inside flange,1/4in welded terminal plates, two1/2in cap bolts into the actual eave-header/end-frame bottom flange, and four1/2in anchors with4in embedment into adopted slab support. Plate set-out, welds, anchors, receiving-flange local behavior and restraint stiffness/strength require checking. Source girt capacity does not certify this adopted restraint system or foundation.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;u=[1,0,0] if par['along']==0 else [0,1,0];axes=(u,cross([0,0,1],u),[0,0,1]);sg=par['sg'];purpose=par['purpose']
    sag=ctx.ms[0];extract(ctx,sag,'SAG',axes,16)
    heel=[sg,-sg*4];toe=[-sg,-sg*6]
    if purpose=='girt':
        girt=ctx.ms[1];extract(ctx,girt,'GIRT',axes,18);gt=p[girt['profile_id']]['dimensions']['t']
        a.fastener('GIRT-S',[[x,-sg*(4+.125),1] for x in (-.5,.5)],[0,sg,0],.216,.125+gt,['SAG','GIRT'],
            'A two No12 screws through sag-angle leg and actual inside girt flange',basis='A',screw=True)
        a.dim([0,0,0],[0,-sg*4,0],'S actual girt half-depth',basis='S');a.section_axis=0;a.section_at=.5
    else:
        cap=purpose=='cap';gauge=par['beam_gauge_in'];ys=[heel[1],toe[1]]+([gauge-1.25,gauge+1.25] if cap else [])
        lo,hi=min(ys)-(.25 if cap else 1),max(ys)+(.25 if cap else 1)
        wide=2.5 if cap else 3;z=-.25 if cap else 0
        a.box('PLATE',[-wide,lo,z],[2*wide,hi-lo,.25],'A','A1/4in terminal plate at actual sag-angle end')
        wz=-.25 if cap else .25
        for i,(first,last) in enumerate(((add([*heel,wz],[-sg*.125,0,0]),add([*heel,wz],[-sg*2,0,0])),
                                         (add([*heel,wz],[0,-sg*.125,0]),add([*heel,wz],[0,-sg*2,0])))):
            a.weld('W'+str(i),first,last,['SAG','PLATE'],.125,basis='A',description='A1/8in end fillet along each actual angle leg')
        if cap:
            extract(ctx,ctx.ms[1],'BEAM',axes,18)
            a.fastener('CAP-B',[[x,gauge,-.25] for x in (-1.5,1.5)],[0,0,1],.5,.25+par['beam_flange_thickness_in'],['PLATE','BEAM'],
                'A two1/2in bolts through cap and actual receiving bottom flange',basis='A')
            a.dim([0,heel[1],0],[0,gauge,0],'A actual terminal projection',basis='A')
        else:
            concrete=a.box('SUPPORT',[-5,lo-2,-10],[10,hi-lo+4,10],'A','A local10in concrete support context; foundation and anchors unverified',kind='concrete')
            a.fastener('ANCHORS',[[x,y,.25] for x in (-2,2) for y in (lo+.75,hi-.75)],[0,0,-1],.5,4.25,['PLATE','SUPPORT'],
                'A four1/2in anchors with4in embedment; concrete support/capacity requires verification',basis='A')
        a.section_axis=0;a.section_at=-1.5 if cap else -2
    a.notes.append('S sidewall girt midspan sag-angle requirement. A actual L2x2x1/8 and located flange/terminal attachments; endwall extension is adopted. The angle is restrained at real beam and ground interfaces. No verified capacity is inferred for the angle, terminal plates, welds, fasteners, receiving beam flange, anchors or foundation; source Lb capacity remains conditional on the required restraint performance.')
