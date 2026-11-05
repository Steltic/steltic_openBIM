"""Evidence-checked links from CFS schedules to already located physical walls.

An analysis-line name alone is insufficient. Verify every storey, actual segment
length and sheet thickness before recording schedule applicability. This does
not supply missing gravity framing, collectors or connection components.
"""
import re
from .review_model import MIL


def attach(b,item,rid,basis):
    if rid not in item.setdefault('design_record_ids',[]):item['design_record_ids'].append(rid)
    proof=dict(record_id=rid,basis=basis)
    if proof not in item.setdefault('design_mapping_evidence',[]):item['design_mapping_evidence'].append(proof)
    b.used_records.add(rid)


def unresolved(b,rid,reason):
    b.changes.append(dict(kind='source_wall_schedule_unbound',record_id=rid,reason=reason,
        basis='S: physical geometry must satisfy the complete source schedule before this record can be mapped. No completeness override.'))


def apply(b):
    # These exact table schemas belong to these saved gold examples. Do not
    # infer similarly named source tables on an unrelated production job.
    if b.key not in ('cfs2','cfs3','cfs5','cfs7','cfs12'):return
    walls={(w['line'],w['level']):w for w in b.walls};stories=len(b.cfg['heights_ft'])
    by_wall={}
    for m in b.members:
        match=re.match(r'^([XY][A-Z0-9]+)-L(\d+)-B\d+-(?:S\d+|BT|TT)$',m['id'])
        if match and m['kind'] in ('stud','bottom_track','top_track'):
            by_wall.setdefault((match[1],int(match[2])),[]).append(m)
    for rid,record in b.records.items():
        data=record['data'];table=record['table']
        if table=='segment_framing':
            line=data['line']
            values=[int(data[f's{k}']) for k in range(1,stories+1)] if b.key=='cfs7' else [int(v.strip()) for v in data['framing_mil_stories_1_to_8'].split('/')]
            if len(values)!=stories:
                unresolved(b,rid,'Source framing schedule does not enumerate every storey');continue
            matches=[];valid=True
            for k,mil in enumerate(values,1):
                actual=by_wall.get((line,k),[])
                if not actual or not any(m['kind']=='stud' for m in actual):valid=False;break
                for m in actual:
                    profile=b.profiles[m['profile_id']]
                    selected=re.fullmatch(r'\d{3,4}[ST]\d{3}-(\d+)',m['profile_id'])
                    if (profile['family']!='channel' or not selected or int(selected[1])<mil or
                        int(selected[1]) not in MIL or abs(profile['dimensions']['t']-MIL[int(selected[1])])>1e-6):valid=False;break
                if not valid:break
                matches.extend(actual)
            if not valid:
                unresolved(b,rid,'A required stud/track occurrence or its source framing thickness is missing');continue
            for m in matches:attach(b,m,rid,'Source segment-framing minimum at this exact line and storey, verified against each actual stud/track thickness. Independent gravity section and attachment checks remain separate.')
        elif table=='braced_wall_layout':
            if b.key=='cfs7':
                cfs7_layout(b,rid,data,walls,by_wall,stories)
                continue
            lines=re.findall(r'\b[XY][A-Z0-9]+\b',data['line'])
            if b.key in ('cfs2','cfs5') and data['line']=='Y1-Y5':lines=['Y'+str(i) for i in range(1,6)]
            if b.key=='cfs3' and data['line']=='Y28 to Y168':lines=['Y'+str(i) for i in range(28,169,28)]
            selection=re.fullmatch(r'(\d+)(?: discrete bays)? x (\d+(?:\.\d+)?) ft',data['walls'])
            continuous=re.fullmatch(r'(\d+) continuous walls? of (\d+) bays x (\d+(?:\.\d+)?) ft',data['walls'])
            if not lines or not (selection or continuous):
                unresolved(b,rid,'No explicit line list and segment count/length selection');continue
            count=int(selection[1]) if selection else int(continuous[1])*int(continuous[2])
            length=float(selection[2] if selection else continuous[3])*12;matches=[];valid=True
            for line in lines:
                for k in range(1,stories+1):
                    wall=walls.get((line,k));actual=by_wall.get((line,k),[])
                    if (wall is None or not actual or len(wall['runs'])!=count or
                        any(abs(r['end_in']-r['start_in']-length)>.001 for r in wall['runs']) or
                        abs(sum(r['end_in']-r['start_in'] for r in wall['runs'])-data['per_line_ft']*12)>.001):
                        valid=False;break
                    if continuous:
                        groups=[];previous=None
                        for run in sorted(wall['runs'],key=lambda r:r['start_in']):
                            if previous is None or abs(run['start_in']-previous)>.001:groups.append(0)
                            groups[-1]+=1;previous=run['end_in']
                        if groups!=[int(continuous[2])]*int(continuous[1]):valid=False;break
                    matches.extend(actual)
                if not valid:break
            if not valid:
                unresolved(b,rid,'Located wall runs do not match every source line, storey, segment count and length');continue
            for m in matches:attach(b,m,rid,'Source braced-wall layout: every named line/storey and actual segment count, length and total run verified. This is a layout link, not a member capacity or collector design.')
    # The 97 mil segment check expressly applies inside these braced segments;
    # the ordinary party-wall check expressly applies outside them.
    rid='studs/stud-segments-97'
    source=b.records.get(rid,{}).get('data',{})
    if source.get('section')=='600S162-97 stories 1-8' and 'inside the shear-wall segments' in source.get('label',''):
        for items in by_wall.values():
            for m in items:
                if m['kind']!='stud' or m['profile_id']!='600S162-97':continue
                previous=list(m['design_record_ids'])
                m['design_record_ids']=[r for r in previous if r!='studs/stud-party-walls']
                attach(b,m,rid,'Exact source 600S162-97 selection inside the located shear-wall segment; separate from the ordinary party-wall tiers.')
                if previous!=m['design_record_ids']:
                    b.changes.append(dict(kind='source_segment_stud_binding',member_id=m['id'],previous_record_ids=previous,
                        record_ids=list(m['design_record_ids']),basis='Source explicitly distinguishes 97 mil segment studs from ordinary party-wall studs; physical section and position retained.'))


def cfs7_layout(b,rid,data,walls,by_wall,stories):
    text=data['line'];lines=[]
    for token in re.split(r'\s*[,/]\s*',text):
        match=re.fullmatch(r'([XY][A-Z]+)(\d+)-\1(\d+)',token)
        lines.extend([match[1]+str(n) for n in range(int(match[2]),int(match[3])+1)] if match else [token])
    segments={'6 x 18 ft per corridor wall':[216]*6,'2 x 26 ft':[312]*2,
              '2 x 14 ft':[168]*2,'2 x 14 ft + 10 ft':[168,168,120],'3 x 10 ft':[120]*3}.get(data['walls'])
    if segments is None:raise ValueError('Unknown CFS7 source segment layout')
    # The named throat-end row is more specific than the range row. The two
    # ordinary 14 ft runs are still represented, alongside its third 10 ft run.
    expected_special=data['walls']=='2 x 14 ft'
    matches=[]
    for line in lines:
        for k in range(1,stories+1):
            wall=walls.get((line,k));actual=by_wall.get((line,k),[])
            expected=segments+([120] if expected_special and line in ('YN7','YS5') else [])
            lengths=sorted(round(r['end_in']-r['start_in'],6) for r in wall['runs']) if wall else []
            if not actual or lengths!=sorted(expected):
                unresolved(b,rid,'Actual CFS7 segment count/length differs at '+line+' storey '+str(k));return
            if abs(sum(segments)-data['per_line_ft']*12)>.001:raise ValueError('Source CFS7 segment total changed')
            matches.extend(actual)
    for m in matches:attach(b,m,rid,'Exact source line/storey and segment lengths verified. YN7/YS5 retain their more-specific additional 10 ft throat segment; the generic 28 ft row describes their two ordinary 14 ft runs only.')
