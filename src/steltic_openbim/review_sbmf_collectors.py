"""CFS18 nested collector ply, actual lap interfaces and retained floor datum."""
import copy,math
from .pilots.model import add
from .review_cfs_source_bindings import attach
from .review_receiver_geometry import extract,horizontal_frame


def prepare(b):
    if b.key!='cfs18':return
    t=b.profiles[b.profile('600T162-54')]['dimensions']['t']
    tracks={m['id']:m for m in b.members if m['id'].startswith('MEZZ-') and m['kind']=='top_track'}
    for track in tracks.values():
        for off in track['end_offsets']:off[2]-=t
    for m in b.members:
        if not m['id'].startswith('MEZZ-') or m['kind'] not in ('stud','chord'):continue
        label=m['id'].split('-ST-')[0] if m['kind']=='stud' else m['id'].split('-CH-')[0]
        track=tracks[label+'TT']
        if abs(m['axis'][1][2]-track['axis'][0][2])<.2:m['end_offsets'][1][2]-=t


def apply(b):
    if b.key!='cfs18':return
    original=b.profile('600T162-54');t=b.profiles[original]['dimensions']['t']
    for track in [m for m in b.members if m['id'].startswith('MEZZ-') and m['kind']=='top_track']:
        aa,bb=[add(q,o) for q,o in zip(track['axis'],track['end_offsets'])]
        along=0 if abs(bb[0]-aa[0])>1 else 1;normal=1-along;lo,hi=sorted((aa[along],bb[along]));z=track['axis'][0][2]
        rid=f'framing/mezz-collector-{ "XY"[along]}-L{track["level"]+1}'
        count=6 if track['level']==1 else 4;inner=b.profiles[track['profile_id']]['dimensions']
        pid='600T162-54-MEZZ-OUTER-'+str(track['level']);profile=copy.deepcopy(b.profiles[original])
        profile.update(id=pid,source_profile_id=original,basis='A formed nesting width; S54mil sheet and1.625in leg')
        profile['dimensions']['d']=inner['d']+2*t+.0625
        profile['fit_proposal']='A outer track widened to fit the required chord-track section plus1/32in leg clearance. Saved double600T162-54 capacity is not assigned to this altered pair.'
        b.profiles[pid]=profile
        def pt(x):return [x,aa[normal],z] if along==0 else [aa[normal],x,z]
        cuts=[lo,*[lo+144*j for j in range(1,math.ceil((hi-lo)/144))],hi];segments=[]
        for j,(a,d) in enumerate(zip(cuts,cuts[1:])):
            start=a+(.0625 if j else 0);end=d-(.0625 if j<len(cuts)-2 else 0)
            outer=b.member(track['id']+'-COLLECTOR'+str(j),pid,'top_track',pt(start),pt(end),track['level'],'A',records=[rid],local_y=[0,0,-1])
            for off in outer['end_offsets']:off[2]=-t/2
            segments.append(outer)
            xs=[start+12]
            while xs[-1]+24<end-12:xs.append(xs[-1]+24)
            if end-12-xs[-1]>.01:xs.append(end-12)
            stitches=[]
            for n,x in enumerate(xs):
                c=b.connection(outer['id']+'-STITCH'+str(n),'review_sbmf_collector',pt(x),[track,outer],[rid],
                    parameters=dict(purpose='stitch',along=along),basis='A')
                stitches.append(c)
            for e,c in (('start',stitches[0]),('end',stitches[-1])):
                b.endpoint_links.append(dict(member_id=outer['id'],end=e,connection_id=c['id'],
                    basis='Actual outer collector ply is stitched to the continuous underlying chord track; physical source wall transfer remains separately detailed.'))
        for j,(left,right) in enumerate(zip(segments,segments[1:])):
            c=b.connection(track['id']+'-COLLECTOR-SPLICE'+str(j),'review_sbmf_collector',pt(cuts[j+1]),[track,left,right],[rid],
                parameters=dict(purpose='splice',along=along,screws_per_interface=count),basis='S')
            for member,end in ((left,'end'),(right,'start')):
                b.endpoint_links[:]=[e for e in b.endpoint_links if not(e['member_id']==member['id'] and e['end']==end)]
                b.endpoint_links.append(dict(member_id=member['id'],end=end,connection_id=c['id'],
                    basis='Each finite collector end laps the actual continuous lower track; the source6/4 No.12 screws occur at each distinct transfer interface.'))
        attach(b,track,rid,'Located double-ply collector with source54mil outer track and source6/4 No.12 per lap interface. The separate chord-track selection governs the lower ply; widened outer fit and continuous lower length are adopted, with source capacity unverified for the altered pair.')
    b.note('MEZZ-NESTED-COLLECTORS','S: second54mil top-track ply and6 No.12 at each L2 lap interface /4 atL3. A: source chord-track selection governs the lower ply (97mil deep track atL2;54mil2in-leg track atL3), including its adopted extension through field runs. The outer1.625in-leg track has a widened nesting fit;12ft outer segments have1/8in butt gaps and lap the continuous47/46ft lower track. Actual splice locations, two-row web screw distribution, continuous lower procurement length and No.12 web stitches at maximum24in are adopted. Lower tracks and stud/chord heads move downone54mil sheet, retaining the original floor bearing plane. These changed sections/fit require capacity verification; saved collector calculations are retained as source evidence only.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=horizontal_frame([1,0,0] if par['along']==0 else [0,1,0])
    for m,label in zip(ctx.ms,('LOWER','OUTER-L','OUTER-R')):
        extract(ctx,m,label,axes,18)['drawing_style']='outline_iso'
    lower=p[ctx.ms[0]['profile_id']]['dimensions'];upper=p[ctx.ms[1]['profile_id']]['dimensions'];grip=lower['t']+upper['t']
    if par['purpose']=='stitch':
        a.fastener('STITCH',[[0,0,0]],[0,0,-1],.216,grip,['LOWER','OUTER-L'],
            'A No.12 collector web stitch at maximum24in, both real sheets touch',basis='A',screw=True)
    else:
        count=par['screws_per_interface']
        for sign,label in ((-1,'OUTER-L'),(1,'OUTER-R')):
            pts=[[sign*(1.5+1.5*j),y,0] for j in range(count//2) for y in (-1,1)]
            a.fastener(label+'-SCREWS',pts,[0,0,-1],.216,grip,['LOWER',label],
                f'S{count} No.12 per lap interface; A two-row web distribution and changed lower-track selection',screw=True)
        a.dim([1.5,-1,0],[3,-1,0],'A screw pitch',basis='A',offset=-60)
        a.dim([1.5,-1,0],[1.5,1,0],'A row gauge',basis='A',offset=60)
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=0 if par['purpose']=='stitch' else 1.5
    a.notes.append('The outer ply is physically separate. Its finite ends lap the real continuous lower track; no generic receiver is substituted. A nesting width and lower-track selection differ from the saved idealized double600T162-54 pair, so source capacity is not assigned to this fit.')
    a.notes.append('Isometric track surfaces are shown as outlines to expose the screw groups. Plan and true section retain solid member faces.')
