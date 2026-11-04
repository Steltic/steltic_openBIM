"""Do not copy a fixed-end RBS detail onto the same beam's released end."""
import copy,math,re
from .review_rbs import selection


def major_releases(arguments):
    if len(arguments)<11 or arguments[0]!='elasticBeamColumn':return set()
    flag='-releasey' if arguments[8]>arguments[9] else '-releasez'
    if flag not in arguments:return set()
    code=arguments[arguments.index(flag)+1]
    return {0} if code==1 else {1} if code==2 else {0,1} if code==3 else set()


def apply(builder):
    if not builder.key.startswith('hr'):return
    members={m['id']:m for m in builder.members}
    analysis={a['id']:a for a in builder.package['analysis']['elements']}
    axes={m['id']:m['axis'] for m in builder.package['physical']['members']}
    for c in builder.connections:
        if c['detail_ref']['id']!='review_beam':continue
        primary=members[c['member_ids'][0]];source_ids=primary.get('analysis_ids',[])+[s['analysis_id'] for s in primary.get('analysis_segments',[])]
        release=[]
        for mid in source_ids:
            row=analysis.get(mid,{});ends=major_releases(row.get('builder_arguments',[]))
            for end in ends:
                if mid in axes and math.dist(axes[mid][end],c['point'])<.01:release.append(dict(analysis_id=mid,end=end))
        if not release:continue
        physical_fr=[rid for rid in c['design_record_ids'] if 'fully restrained' in str(builder.records[rid]['data'].get('components','')).lower() and re.search(r'F(?:2\.6|4\.6b)',str(builder.records[rid]['data'])) and not selection(str(builder.records[rid]['data'].get('components','')))]
        if physical_fr:
            c.setdefault('parameters',{}).update(source_releases=release,analysis_release_with_prescriptive_fr=True)
            builder.changes.append(dict(kind='analysis_release_with_physical_fr',connection_id=c['id'],source_records=physical_fr,
                basis='S: source braced-frame prescriptive fully restrained CJP connection is retained although the source analysis assigns no joint moment; this is not an RBS carried across a released end'))
            continue
        par=c.setdefault('parameters',{});par.update(moment=False,released_major_end=True,source_releases=release)
        original=copy.deepcopy(c['design_record_ids']);selected=[]
        for rid in original:
            row=builder.records[rid]['data'];text=str(row.get('components',''))
            if 'J10' in rid or 'column-webs' in rid:
                # This is a column-local strength check, not moment-transfer
                # hardware. Retain it at the selected column flange joint.
                from .pilots.model import unit,sub,cross,dot
                support=next((members[mid] for mid in c['member_ids'][1:] if members[mid]['kind']=='column'),None)
                if support:
                    flange_normal=cross(unit(sub(support['axis'][1],support['axis'][0])),support['local_y'])
                    beam_axis=unit(sub(primary['axis'][1],primary['axis'][0]))
                    if abs(dot(flange_normal,beam_axis))>.99:selected.append(rid)
                continue
            if selection(text) or 'joint' in rid.lower() or 'rbs' in text.lower():continue
            if any(w in text.lower() for w in ('single plate','shear plate','two plates','two-plate','clip angle','end connection')):selected.append(rid)
        c['design_record_ids']=selected
        c['source_context_records']=original
        if not selected:
            par['released_connection_proposal']=True
            c['basis']='A: accepted fictional simple-end fit; actual major-axis release is S; additional attachment capacity unverified'
        builder.changes.append(dict(kind='source_major_axis_release',connection_id=c['id'],source_releases=release,
            previous_design_record_ids=original,selected_design_record_ids=selected,
            basis='Retain source fixed-end design as context; do not draw RBS/CJP moment transfer at the released end. Missing simple-end attachment is an explicit A fit proposal, not a checked source design.'))
    if any(c.get('parameters',{}).get('released_connection_proposal') for c in builder.connections):
        builder.note('RELEASED-ENDS','A: source analysis releases the major-axis moment at identified beam ends. The source RBS remains on fixed ends only. Where no separate source simple-end selection exists, the drawn shear plate, bolts and welds are accepted fictional fit proposals requiring attachment capacity verification; the original gold connection record is retained as context.')
