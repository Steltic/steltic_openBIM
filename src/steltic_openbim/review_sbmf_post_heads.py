"""Located vertical-slip heads of CFS18's six source end-wall wind posts."""
from .review_receiver_geometry import extract

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members}
    beams=[m for m in b.members if m['id'].startswith('FRAME-') and m['kind']=='moment_beam']
    for c in b.connections:
        if c['detail_ref']['id']!='review_sbmf_wall_slide' or not c['id'].startswith('END-POST-'):continue
        post=lookup[c['member_ids'][0]];x,y,z=c['point']
        beam=next(m for m in beams if abs(m['axis'][0][0]-x)<.01)
        c['member_ids']=[post['id'],beam['id']];c['detail_ref']['id']='review_sbmf_post_head'
        c.setdefault('parameters',{}).update(actual_sbmf_wall=True)
        b.endpoint_links.append(dict(member_id=post['id'],end='end',connection_id=c['id'],
            basis='Actual boxed wind post fits between the real end-frame channel webs; located flange bolts use vertical slots and transfer no roof gravity support.'))
        b.changes.append(dict(kind='sbmf_post_head_slip_fit',member_id=post['id'],receiver_id=beam['id'],
            basis='S post section,24ft height and vertical-slip requirement. A four1/2in bolts through actual post flanges/end-frame webs,1.5in slots,1in travel, washers and local attachment capacity unverified.'))
    b.note('SBMF-WIND-POST-HEADS','S: six24ft boxed1000S250-97 wind posts and their vertical-slip end-frame interface. A: two1/2in bolts per face through the actual end-frame web and post flange,1.5in vertical slots and1in travel. The post fits between the actual paired beam webs and does not bear on a generic roof track. Receiving-web and slotted-flange capacity, bolt access and required movement remain subject to engineering verification.')


def draw(ctx):
    a,p=ctx.a,ctx.p;post,beam=ctx.ms
    extract(ctx,post,'POST',AXES,28);extract(ctx,beam,'END-FRAME',AXES,24)
    pp=p[post['profile_id']];pd=p[pp['components'][0]['profile_id']]['dimensions']
    bp=p[beam['profile_id']];bd=p[bp['components'][0]['profile_id']]['dimensions'];half=pd['d']/2
    for side in (-1,1):
        a.fastener('SLIDE'+str(side),[[side*(half+bd['t']),y,-2] for y in (-1.25,1.25)],[-side,0,0],.5,bd['t']+pd['t'],
            ['POST','END-FRAME'],'A two1/2in bolts through actual post flanges and end-frame web; washers bridge vertical slots',basis='A')
        a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=1.5,width_in=.5625,travel_in=1.,basis='A')
    a.interfaces.append(dict(id='SLIP',kind='vertical_slotted_connection',connects=['POST','END-FRAME'],travel_in=1.,basis='A',
        description='Source vertical movement; A slot size/travel. The wind post does not support roof gravity loads.'))
    a.dim([0,-1.25,-2],[0,1.25,-2],'A2.5in bolt gauge',basis='A');a.section_axis=2;a.section_at=-2
    a.notes.append('Source boxed wind post at its actual24ft top and actual paired end-frame channels. A four local bolts, washer bridging and vertical slots provide the depicted slip fit. Source post bending checks do not certify this attachment or modification of the receiving beam webs.')
