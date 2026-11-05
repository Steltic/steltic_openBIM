"""Stitches cross the actual two post webs through an explicit fit pack."""
from .review_receiver_geometry import extract
AXES=([1,0,0],[0,1,0],[0,0,1])


def draw(ctx):
    a=ctx.a;m=ctx.ms[0];p=ctx.p[m['profile_id']];t=ctx.p[p['components'][0]['profile_id']]['dimensions']['t'];gap=.125
    extract(ctx,m,'POST',AXES,16);gauge=2 if m['kind']=='opening_jamb' else .75
    pid='A-CFS27-STITCH-PACK-'+str(gauge)
    a.profiles[pid]=dict(id=pid,family='flat',dimensions=dict(width=2*gauge+1,thickness=gap),basis='A solid fit pack, not a new supporting member')
    a.member('PACK',pid,[0,0,-.5],[0,0,.5],y=[0,1,0],basis='A',description='A solid1/8in pack between the actual paired post webs',representation_role='assembly_component')
    a.fastener('STITCH',[[gap/2+t,y,0] for y in (-gauge,gauge)],[-1,0,0],.216,gap+2*t,['POST','PACK'],'A twoNo12 C1513 through-web stitches; source24in jamb spacing',basis='S spacing / A screw group',screw=True)
    a.title='SINGLE CHANNEL / PAIRED POST STITCH';a.front_axes=(1,2);a.section_axis=2;a.section_at=0
    a.notes.append('S jamb stitching at24in and C1513 screws. A twoNo12 screws, gauge,1/8in web pack and exact end offset; centre-post24in pitch adopted. Both real webs are engaged; the source built-up-member calculation is not assigned to the adopted local fit.')

    if ctx.model['pilot']=='cfs28':a.title='AG END WALL / PAIRED POST STITCH'
