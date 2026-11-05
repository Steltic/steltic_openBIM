"""Preserve the saved retrofit's explicit existing-structure boundary."""
from .review_receiver_geometry import extract
from .review_cfs_occurrences import axis
from .pilots.model import add,sub,mul,dot
from .drawing_workflow import fingerprint
import math

GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs25':return
    lookup={m['id']:m for m in b.members};existing=[]
    for m in b.members:
        if m['id'].startswith(('F','EXIST-','EAVE-')):
            m.update(scope='existing_context',engineering_status='not_checked',survey_status='A fictional survey stand-in; not an as-built survey')
            existing.append(m['id'])
    for c in b.connections:
        if not all(mid in existing for mid in c['member_ids']):continue
        if c['parameters'].get('existing_context') or c['member_ids'][0].startswith('EAVE-'):
            original=c['detail_ref']['id'];c['detail_ref']={'id':'review_retrofit_existing'}
            foundation=len(c['member_ids'])==1 and lookup[c['member_ids'][0]]['kind'] in ('column','endwall_post') and c['point'][2]<1
            if len(c['member_ids'])==1 and not foundation:
                choices=[]
                for member in b.members:
                    if member['id'] not in existing or member['id'] in c['member_ids'] or member['kind'] not in ('column','rafter','endwall_post'):continue
                    aa,dd=axis(member);delta=sub(dd,aa);s=max(0,min(1,dot(sub(c['point'],aa),delta)/dot(delta,delta)))
                    choices.append((math.dist(c['point'],add(aa,mul(delta,s))),member['id']))
                distance,mid=min(choices)
                if distance>1:raise ValueError('No located adjacent existing member '+c['id'])
                c['member_ids'].append(mid)
            refs=c.get('design_record_ids') or ['schedules/sched-strap' if 'rod_brace' in {lookup[mid]['kind'] for mid in c['member_ids']} else 'schedules/sched-girt']
            c.update(scope='delegated',responsible_party='Existing-building engineer / original frame supplier',
                representation='Actual fictional existing member extracts; original joint hardware was outside the saved retrofit design and is not fabricated here.',
                design_record_ids=refs,title='EXISTING STRUCTURE / SURVEY AND ENGINEER HANDOFF',
                parameters=dict(actual_retrofit_existing=True,original_family=original,foundation_context=foundation))
            for mid in c['member_ids']:
                for end in ('start','end'):
                    # Only a member's own endpoint connection may account for
                    # that endpoint. Other existing members in this view remain
                    # context and do not silently acquire a connection.
                    q=lookup[mid]['axis'][0 if end=='start' else 1]
                    if sum((a-d)**2 for a,d in zip(q,c['point']))<1e-8:
                        b.endpoint_links.append(dict(member_id=mid,end=end,connection_id=c['id'],basis='Saved retrofit explicitly excludes this existing joint; the existing-building engineer owns its survey and verification.'))
            b.used_records.update(refs)
    b.physical_interfaces=[dict(id='CFS25-EXISTING-STRUCTURE',kind='existing_structure',scope='existing',
        member_ids=existing,responsible_party='Existing-building engineer / original frame supplier',
        representation='A surveyed-envelope stand-ins for the original frames, end-wall posts, eave struts and rod bracing; not newly designed members or joints',
        detail_ref=dict(id='gold/cfs25/existing_structure_interface',revision=fingerprint(b.raw['existing_structure_interface'])),
        requirements=b.raw['existing_structure_interface'])]
    b.note('EXISTING-SCOPE','S: saved retrofit replaces purlins, girts and cladding attachments; existing frames, bases, eave struts and rods stay outside that design. A survey stand-ins remain visible. No invented existing bolt or weld design is issued. Their exact joint hardware, corrosion, support flange bearing and8kip roof-rod handoff belong to the existing-building engineer, as stated in the unchanged gold existing_structure_interface.')


def draw(ctx):
    a=ctx.a;a.title='EXISTING STRUCTURE / SURVEY AND ENGINEER HANDOFF'
    for i,m in enumerate(ctx.ms):extract(ctx,m,'EXISTING'+str(i),GLOBAL,36)
    connects=['EXISTING'+str(i) for i in range(len(ctx.ms))]
    if ctx.params['foundation_context']:
        context=a.box('FOUNDATION-SURFACE',[-12,-12,-1],[24,24,1],'A','Foundation surface context only; footing extent, base and anchors not surveyed',kind='concrete')
        context['representation_role']='context_only';connects.append('FOUNDATION-SURFACE')
    a.notes.append('S existing-structure scope exclusion: this joint is not part of the saved retrofit design. A fictional existing geometry is shown for coordination only. Existing-building engineer/original supplier must confirm actual joint hardware and receiving-member condition. No bolt, weld or capacity is invented from the frame outline.')
    a.interfaces.append(dict(id='EXISTING-SCOPE',kind='existing_structure',connects=connects,scope='existing',basis='S scope / A survey envelope',responsible_party='Existing-building engineer / original frame supplier',description='Original retrofit excludes existing primary/base/bracing joints; retain the source handoff and survey obligations.'))
    a.section_axis=2;a.section_at=0
