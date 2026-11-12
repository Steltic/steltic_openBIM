"""Fit the loaded free edge of a bolted BRB gusset to its specified block-shear path."""
from shapely.geometry import LineString,Polygon


def fit_loaded_edge(outline, bolt_corners, axis, welds):
    """Keep the bolt tongue square to the brace and the selected support welds intact."""
    ux,_,uz=axis

    def project(x,z):
        return (ux*x+uz*z,-uz*x+ux*z)

    def unproject(s,t):
        return (ux*s-uz*t,uz*s+ux*t)

    plate=Polygon([project(x,z) for x,z in outline])
    tongue=[project(x,z) for x,z in bolt_corners]
    far=max(s for s,t in tongue)
    if plate.bounds[2]<=far+1.e-7:
        return outline
    left=min(t for s,t in tongue)
    right=max(t for s,t in tongue)
    # Outside the full width of the bolt tongue the free edges can return
    # towards a support. Compute the least slope that retains every attachment.
    returns=[1.,1.]
    support_lines=[]
    for weld in welds:
        if 'GUSSET' not in weld['connects']:
            continue
        pa,pb=[project(weld[k][0],weld[k][2]) for k in ('a','b')]
        support_lines.append(LineString([pa,pb]))
        stations=[pa,pb]
        for bound in (left,right):
            if min(pa[1],pb[1])<bound<max(pa[1],pb[1]):
                f=(bound-pa[1])/(pb[1]-pa[1])
                stations.append((pa[0]+f*(pb[0]-pa[0]),bound))
        for s,t in stations:
            if s<=far+1.e-7:
                continue
            if left-1.e-7<=t<=right+1.e-7:
                raise ValueError('Selected gusset weld crosses the loaded edge of the BRB bolt group')
            i=0 if t<left else 1
            margin=left-t if i==0 else t-right
            returns[i]=max(returns[i],(s-far)/margin)
    start,low,_,high=plate.bounds
    start-=1.;low-=1.;high+=1.
    boundary=Polygon([(start,low),(far+returns[0]*(left-low),low),(far,left),(far,right),
                      (far+returns[1]*(high-right),high),(start,high)])
    # The intersection can generate a sub-microinch edge where two fitted
    # corners coincide. Remove it before the plate is drilled and triangulated.
    trimmed=plate.intersection(boundary).simplify(1.e-5,preserve_topology=True)
    if (trimmed.geom_type!='Polygon' or not trimmed.is_valid or
            any(not trimmed.buffer(1.e-5).covers(line) for line in support_lines)):
        raise ValueError('Fitting the BRB loaded edge would remove a selected gusset attachment')
    return [unproject(s,t) for s,t in list(trimmed.exterior.coords)[:-1]]
