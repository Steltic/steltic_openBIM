"""Place a selected full-length support fillet on each named gusset face."""


def place_faces(assembly,selected,horizontal_role):
    gusset=next((part for part in assembly.parts if part['id']=='GUSSET'),None)
    if not gusset:return
    ys=[p[1] for face in gusset['faces'] for p in face]
    runs=[]
    for weld in assembly.welds:
        logical=weld.get('source_weld_id',weld['id'])
        role={'WGC':'gusset_column_weld','WGB':horizontal_role}.get(logical)
        if (not role or weld['kind']!='fillet' or 'GUSSET' not in weld['connects'] or
                selected.get((role,'faces'))!=2):
            runs.append(weld)
            continue
        for side,face in ((-1,min(ys)),(1,max(ys))):
            near,far=list(weld['a']),list(weld['b']);near[1]=far[1]=face
            runs.append(dict(weld,id=weld['id'] if side==-1 else weld['id']+'-FACE2',
                             source_weld_id=logical,source_weld_side=side,source_weld_leaf='GUSSET',
                             attachment_role=role,a=near,b=far,
                             description=weld['description']+'; '+('first' if side<0 else 'opposite')+' gusset face'))
    assembly.welds=runs
