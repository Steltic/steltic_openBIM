"""Declared floor footprints take precedence over incomplete legacy viewer cells."""

def cells(b,levels):
    from .review_final_hr import KEYS,floor_cells
    if b.key in KEYS:return floor_cells(b,levels)
    c=b.config;g=c.get('G',c.get('GEO',{}));present=c.get('PRESENT',g.get('present'));nx,ny=c.get('NX'),c.get('NY')
    xs=c.get('XS',g.get('xs'));ys=c.get('YS',g.get('ys'))
    if not xs and nx is not None:xs=[i*c.get('SX',c.get('S_',336)) for i in range(nx+1)]
    if not ys and ny is not None:ys=[j*c.get('SY',c.get('S_',336)) for j in range(ny+1)]
    if b.key=='hr9':present={str(k):c['PENT'] if k==13 else c['FLANGE']+c['STEM'] for k in range(1,len(levels))}
    if b.key=='hr12':present={str(k):c['FULL'] if k<=9 else c['TOWER'] for k in range(1,len(levels))}
    if b.key in ('hr27','hr28'):present={str(k):[(i,j) for i in range(nx+1) for j in range(ny+1)] for k in range(1,len(levels))}
    if b.key in ('hr14','hr16','hr18','hr20','hr21','hr24','hr25','hr30','hr35'):
        from .review_next_hr import floor_cells
        return floor_cells(b,levels)
    if not present or not xs or not ys:return b.source['viewer'].get('slabs',[])
    result=[]
    for k,z in enumerate(levels[1:],1):
        points={tuple(p) for p in present.get(str(k),present.get(k,[]))}
        for i in range(len(xs)-1):
            for j in range(len(ys)-1):
                if not {(i,j),(i+1,j),(i,j+1),(i+1,j+1)}<=points:continue
                if b.key=='hr27' and 360<=xs[i]<xs[i+1]<=1080 and 360<=ys[j]<ys[j+1]<=720:continue
                result.append([xs[i],xs[i+1],ys[j],ys[j+1],z])
    b.note('FLOOR-FOOTPRINT','Source level-by-level presence declarations define occupied floor cells, including stepped wings and courtyard voids. Legacy viewer slab cells are incomplete around segmented braced/moment frames and are not treated as the floor boundary. Infill set-out uses source spacing; local cutbacks remain A.')
    return result

def thickness(key,k):
    if key=='hr4':return 7.5
    if key=='hr6':return 1.5 if k==6 else 5.5
    if key in ('hr19','hr29'):return 6
    if key=='hr26':return 4.5
    if key in ('hr34a','hr34b'):return 1.5 if k==(14 if key=='hr34a' else 10) else 9 if k==2 else 6.25
    if key=='hr16' and k==3 or key=='hr21':return 1.5
    if key=='hr35':return 1.5
    if key=='hr20' and k==3:return 6.25
    if key=='hr9':return 4.5
    if key=='hr13':return 1.5 if k in (4,6) else 9 if k==2 else 5
    if key=='hr32':return 4 if k<=3 else 4.5
    return 1.5 if key=='hr33' else 6.25

def interval(vertices,station,other,along):
    """Intersect a floor polygon with one infill workline, preserving chamfers."""
    hits=[]
    for a,d in zip(vertices,vertices[1:]+vertices[:1]):
        if abs(a[other]-d[other])<1e-8:continue
        if min(a[other],d[other])-1e-8<=station<=max(a[other],d[other])+1e-8:
            t=(station-a[other])/(d[other]-a[other]);hits.append(a[along]+t*(d[along]-a[along]))
    return (min(hits),max(hits)) if len(hits)>=2 else None
