"""Offline review viewer and reproducible visual review sheets."""
import html
import json
from pathlib import Path
from .model import add,sub,mul
from .geometry import COLORS,layer,member_faces,part_faces,clip_axis,strips

TITLES={'hr22':('01','Six-storey hospital','HR / Perimeter special moment frames'),
        'cfs16':('02','Portal warehouse','CFS / 23 frames, 60 ft span, 275 ft length'),
        'cfs8':('03','T-plan student housing','CFS / Four storeys, 88 strap-braced bays')}


def scene(package,key):
    from ..review import questions
    ph=package['physical']; profiles={p['id']:p for p in ph['profiles']}; joints={j['id']:j for j in ph['joints']}
    members=[]
    for m in ph['members']:
        a,b=[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])]
        members.append(dict(id=m['id'],a=a,b=b,kind=m['kind'],profile=m['profile_id'],level=m.get('level',1),layer=layer(m['kind']),
            refs=m.get('design_record_ids',[]),y=m['local_y'],rbs=m.get('rbs'),cope=m.get('cope'),studs=m.get('stud_assembly')))
    return dict(key=key,title=TITLES[key][1],subtitle=TITLES[key][2],number=TITLES[key][0],building=package['building_id'],
        counts=package['readiness']['counts'],review=package['review'],questions=questions(package),members=members,profiles=profiles,
        panels=ph['panels'],openings=ph['openings'],colors=COLORS,
        connections=[dict(id=c['id'],point=joints[c['joint_id']]['point'],refs=c['design_record_ids'],parts=c.get('parts',[]),
            scope=c.get('geometry_scope',c.get('representation','Source design detail')),ends=joints[c['joint_id']]['member_ends'],attachments=joints[c['joint_id']].get('attachments',[])) for c in ph['connections']],
        records={r['id']:r for r in package['design_records']},interfaces=ph['interfaces'])


def write_viewer(package,key,dest):
    s=scene(package,key)
    raw=json.dumps(s,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('&','\\u0026')
    template=Path(__file__).with_name('viewer.html').read_text(encoding='utf-8')
    (dest/'review.html').write_text(template.replace('__DATA__',raw).replace('__TITLE__',html.escape(s['title'])),encoding='utf-8')


def render(package,key,dest):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from mpl_toolkits.mplot3d.art3d import Line3DCollection,Poly3DCollection
    from matplotlib.lines import Line2D
    ph=package['physical']; profiles={p['id']:p for p in ph['profiles']}; title=TITLES[key][1]
    members=ph['members']; allpts=[add(p,o) for m in members for p,o in zip(m['axis'],m['end_offsets'])]+[v for p in ph['panels'] for v in p['vertices']]
    limits=[(min(p[i] for p in allpts),max(p[i] for p in allpts)) for i in range(3)]
    def base(label,note):
        fig=plt.figure(figsize=(15,10),facecolor='#fafaf7')
        fig.text(.055,.955,'STELTIC  /  PHYSICAL MODEL REVIEW',fontsize=11,color='#52615c',weight='bold')
        fig.text(.055,.91,title+'  ·  '+label,fontsize=23,color='#213e43',weight='bold')
        fig.text(.055,.875,TITLES[key][2],fontsize=11,color='#52615c')
        fig.text(.055,.055,note,fontsize=9,color='#74633c')
        fig.text(.055,.027,'Coordination required  ·  Source dimensions preserved  ·  Design-review geometry; no fabrication release',fontsize=9,color='#74633c')
        return fig
    fig=base('whole building',f'{len(members):,} physical members  /  {len(ph["connections"]):,} connection occurrences  /  {len(package["review"]["items"])} coordination items')
    ax=fig.add_axes([.035,.105,.93,.75],projection='3d',computed_zorder=False)
    bounds=[(a/12,b/12) for a,b in limits]
    ax.set(xlim=bounds[0],ylim=bounds[1],zlim=bounds[2])
    ax.set_autoscale_on(False)
    groups={}
    for m in members:
        a,b=[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])]; groups.setdefault(layer(m['kind']),[]).append([[v/12 for v in a],[v/12 for v in b]])
    for k,lines in groups.items(): ax.add_collection3d(Line3DCollection(lines,colors=COLORS[k],linewidths=.65 if k!='bracing' else .9,alpha=.8))
    for p in ph['panels']:
        if p['kind'] in ('truss_envelope','roof'):
            v=[[c/12 for c in q] for q in p['vertices']]; ax.add_collection3d(Line3DCollection([v+[v[0]]],colors=COLORS['roof'],linewidths=.4,alpha=.7))
    ax.set(xlim=bounds[0],ylim=bounds[1],zlim=bounds[2],xlabel='X / ft',ylabel='Y / ft',zlabel='Z / ft')
    ax.set_box_aspect([b-a for a,b in bounds]); ax.view_init(24,-60 if key!='cfs16' else -36)
    ax.set_facecolor('#fafaf7'); ax.grid(False)
    for axis in [ax.xaxis,ax.yaxis,ax.zaxis]: axis.pane.set_alpha(0); axis.label.set_color('#52615c')
    fig.legend([Line2D([0],[0],color=COLORS[k],lw=3) for k in groups],list(groups),loc='lower right',bbox_to_anchor=(.94,.055),ncol=3,frameon=False,fontsize=9)
    fig.savefig(dest/'01_overview.png',dpi=150); plt.close(fig)
    # Floor/roof set-out plan at source level 1, as orthographic linework.
    fig=base('set-out plan', 'Level 1 framing and braced-wall positions. Roof plan shown for the single-storey portal building.')
    ax=fig.add_axes([.07,.12,.86,.72]); ax.set_facecolor('#fafaf7')
    segments=[]; colors=[]
    for m in members:
        if m.get('level',1)!=1: continue
        if key=='cfs16' and m['kind'] not in ('rafter','purlin','eave_strut','strap'): continue
        a,b=[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])]
        if a[:2]==b[:2]:
            if m['kind'] in ('column','chord','endwall_post'): ax.plot(a[0]/12,a[1]/12,'s',ms=3,color=COLORS[layer(m['kind'])])
            continue
        segments.append([[a[0]/12,a[1]/12],[b[0]/12,b[1]/12]]); colors.append(COLORS[layer(m['kind'])])
    ax.add_collection(LineCollection(segments,colors=colors,linewidths=.6))
    ax.autoscale(); ax.set_aspect('equal'); ax.set_xlabel('X / ft'); ax.set_ylabel('Y / ft'); ax.grid(alpha=.12)
    fig.savefig(dest/'02_plan.png',dpi=150); plt.close(fig)
    center={'hr22':[360,0,192],'cfs16':[0,0,240],'cfs8':[588,0,107.256]}[key]
    sizes={'hr22':[95,55,60],'cfs16':[65,45,60],'cfs8':[42,22,34]}[key]
    crop=[(v-r,v+r) for v,r in zip(center,sizes)]
    fig=base('connection X-ray',{'hr22':'RBS beam / continuous column / continuity and doubler plates. Transparent context exposes source-dimensioned parts.',
        'cfs16':'Knee bolt groups and four-channel arrangement. Gold plates are group envelopes; final gusset outlines need coordination.',
        'cfs8':'Chord pack, rod, bearing plate and floor squash blocks. Spaced-pack and floor-stack interfaces require resolution.'}[key])
    ax=fig.add_axes([.035,.1,.93,.75],projection='3d',computed_zorder=False); count=0
    ax.set(xlim=crop[0],ylim=crop[1],zlim=crop[2])
    ax.set_autoscale_on(False)
    for m in members:
        faces=member_faces(m,profiles,crop)
        if faces:
            ax.add_collection3d(Poly3DCollection(faces,facecolors=COLORS[layer(m['kind'])],edgecolors='#33484e',linewidths=.16,alpha=.22,zorder=1)); count+=1
    js={j['id']:j for j in ph['joints']}
    for c in ph['connections']:
        p=js[c['joint_id']]['point']
        if all(a<=v<=b for v,(a,b) in zip(p,crop)):
            for part in c.get('parts',[]):
                faces=part_faces(part,profiles)
                if faces: ax.add_collection3d(Poly3DCollection(faces,facecolors=COLORS['connections'],edgecolors='#695b32',linewidths=.3,alpha=.95,zorder=20))
    ax.set(xlim=crop[0],ylim=crop[1],zlim=crop[2],xlabel='X / in',ylabel='Y / in',zlabel='Z / in'); ax.set_box_aspect([b-a for a,b in crop]); ax.view_init(24,-55)
    ax.set_facecolor('#fafaf7'); ax.grid(False)
    for axis in [ax.xaxis,ax.yaxis,ax.zaxis]: axis.pane.set_alpha(0)
    fig.savefig(dest/'03_connection.png',dpi=160); plt.close(fig)
    if key=='cfs16':
        fig=base('end-wall elevation','Both ends use this source layout: jambs at 23 ft and 37 ft, header at the 16 ft door opening; girts stop at the opening.')
        ax=fig.add_axes([.07,.13,.86,.7]); seg=[]; colors=[]
        for m in members:
            a,b=[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])]
            if abs(a[1])<16 and abs(b[1])<16:
                seg.append([[a[0]/12,a[2]/12],[b[0]/12,b[2]/12]]); colors.append(COLORS[layer(m['kind'])])
        ax.add_collection(LineCollection(seg,colors=colors,linewidths=1.2)); ax.plot([23,37,37,23,23],[0,0,16,16,0],color='#b75661',lw=1.8)
        ax.text(30,8,'14′ × 16′\nOVERHEAD DOOR',ha='center',va='center',color='#a04c51'); ax.autoscale(); ax.set_aspect('equal'); ax.set_xlabel('X / ft'); ax.set_ylabel('Z / ft'); ax.grid(alpha=.15)
        fig.savefig(dest/'04_endwall.png',dpi=150); plt.close(fig)
    if key=='cfs8':
        fig=base('roof and valley plan','3:12 pitch gives a 5.75 ft rise. Valley/girder-truss internals are delegated; no crossing trusses are fabricated in the model.')
        ax=fig.add_axes([.1,.13,.8,.7]); ax.set_facecolor('#fafaf7')
        for p in ph['panels']:
            if p['kind'] not in ('roof','truss_envelope'): continue
            v=p['vertices']+[p['vertices'][0]]; ax.plot([q[0]/12 for q in v],[q[1]/12 for q in v],color=COLORS['bracing'] if p['kind']=='roof' else '#9eaaa4',lw=1.6 if p['kind']=='roof' else .45)
        ax.annotate('Supplier valley / girder-truss zone',xy=(70,96),xytext=(5,55),arrowprops={'arrowstyle':'->','color':'#a36440'},color='#a36440')
        ax.set_aspect('equal'); ax.set_xlabel('X / ft'); ax.set_ylabel('Y / ft'); ax.grid(alpha=.12)
        fig.savefig(dest/'04_roof.png',dpi=150); plt.close(fig)
