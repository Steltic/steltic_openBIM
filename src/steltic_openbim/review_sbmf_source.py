"""Evidence-checked SBMF analysis links and actual endpoint attachments."""
import math,re
from .review_cfs_source_bindings import attach


def apply(b):
    if b.key not in ('cfs10','cfs18'):return
    lookup={m['id']:m for m in b.members};nodes={n['id']:n['point'] for n in b.package['analysis']['nodes']}
    assigned=set()
    for e in b.package['analysis']['elements']:
        hit=re.fullmatch(r'cfs:frame:(\d+):element:(\d+)',e['id'])
        if not hit:continue
        frame=int(hit[1])-1;label=e['label']
        suffix={'col_L':'C0','col_R':'C1','raf_L':'BEAM','raf_R':'BEAM'}.get(label)
        if suffix is None:raise ValueError('Unknown source SBMF analysis member '+label)
        m=lookup[f'FRAME-{frame}-{suffix}'];points=[nodes[n] for n in e['node_ids']]
        # The source's two-dimensional frame convention uses X across the
        # hall and Y for frame stations. Drawings label these Y and X.
        expected=[[p[1],p[0],p[2]] for p in points]
        if any(abs(p[0]-m['axis'][0][0])>1e-6 for p in expected):raise ValueError('SBMF source frame station changed')
        if label.startswith('col'):
            if any(abs(p[1]-m['axis'][0][1])>1e-6 or not 0<=p[2]<=288 for p in expected):raise ValueError('SBMF source column axes changed')
        elif any(abs(p[2]-288)>1e-6 or not 0<=p[1]<=600 for p in expected):raise ValueError('SBMF source beam axes changed')
        m.setdefault('analysis_ids',[]).append(e['id']);assigned.add(e['id'])
        m['mapping_basis']='Exact saved frame index and col_L/col_R/raf_L/raf_R labels, with node coordinates verified. Source [span,frame-station,z] axes are relabelled [frame-station,span,z] in the accepted drawing grid. Column head extensions and beam end allowances remain explicit physical geometry.'
    expected={e['id'] for e in b.package['analysis']['elements'] if e['id'].startswith('cfs:frame:')}
    if assigned!=expected:raise ValueError('Incomplete source SBMF frame mapping')
    for m in b.members:
        if re.fullmatch(r'FRAME-\d+-C[01]',m['id']):
            rid=b.record('members','frame-col');assert m['profile_id']==b.profile(b.cfg['col_section'])
            attach(b,m,rid,'Exact source HSS column selection on the configured frame station; original288in analysis column and explicit head extension retained.')
            side=int(m['id'][-1]);cid=m['id'].rsplit('-C',1)[0]+'-BEAMJ'+str(side)
            # A heel closure, when present, is the more local end attachment.
            if not any(r['member_id']==m['id'] and r['end']=='end' for r in b.endpoint_links):
                b.endpoint_links.append(dict(member_id=m['id'],end='end',connection_id=cid,basis='The continuous HSS head extends12in above its actual SBMF joint; no separate cut-end connection is specified where no roof heel lands on it.'))
        elif re.fullmatch(r'FRAME-\d+-BEAM',m['id']):
            for end in (0,1):b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=m['id']+'J'+str(end),basis='The finite channel end projects beyond its own source eight-bolt column joint; that located joint serves this same member end.'))
        elif m['kind']=='column_cap' and m['id'].endswith('-ROOF-CAP'):
            for end in ('start','end'):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=m['id']+'-WELD',basis='This continuous closure plate is attached by its own four HSS edge welds; the outer plate edges have no separate end joint.'))
    if b.key=='cfs18':
        rid='schedules/sched-girt'
        for m in b.members:
            if m['id'].startswith('SIDE-GIRT-'):
                if m['profile_id']!='800S200-54':raise ValueError('Side-girt source selection changed')
                attach(b,m,rid,'Exact source side-wall girt section,12.5ft workline span and6ft vertical stations. Midspan sag-angle restraint remains a separate required physical input.')
            elif m['id'].startswith('END-POST-'):
                if m['profile_id']!='2X1000S250-97/BOX' or math.dist(*m['axis'])!=288:raise ValueError('Wind-post source selection changed')
                attach(b,m,rid,'Exact source boxed wind-post section,24ft height and12.5ft stations.')
    b.note('SBMF-ANALYSIS-MAPPING','S: every saved SBMF analysis element is linked once to its actual physical column or continuous paired beam, after checking frame stations and source node coordinates. Analysis span/station axes and accepted drawing X/Y axes are explicitly related; member ends, local fit and source calculations are unchanged by the mapping.')
