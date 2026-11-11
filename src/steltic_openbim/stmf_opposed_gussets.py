"""Fit the unsized free edges of opposite source-selected truss gussets together."""
from shapely.geometry import LineString,Polygon
from .assembly_scene import Assembly,bounds
from .bim_assemblies import transformed
from .pilots.model import dot,sub,cross


def protected_lines(scene):
    return [LineString([(w['a'][0],w['a'][2]),(w['b'][0],w['b'][2])])
            for w in scene['welds'] if 'GUSSET' in w['connects']]+[
                LineString(line) for line in scene.get('checked_transfer_sections_xz_in',[])]


def fit_opposed(ends,profiles):
    """Keep all selected load-transfer sections and welds on their actual plates."""
    for pair in ends.values():
        if len(pair)!=2:continue
        for (first,frm),(second,other) in (pair,pair[::-1]):
            pa=next(p for p in first['parts'] if p['id']=='GUSSET')
            pb=next(p for p in second['parts'] if p['id']=='GUSSET')
            axes=(frm['x_axis'],frm['y_axis'],cross(frm['x_axis'],frm['y_axis']))
            if abs(abs(dot(other['y_axis'],axes[1]))-1)>1e-7:
                break
            pts=[sub(transformed(p,other),frm['origin']) for p in pb['polygon']]
            ay=pa['polygon'][0][1];by=dot(pts[0],axes[1])
            # Plates lying on separate physical faces already have no common steel.
            bfinish=by+dot(other['y_axis'],axes[1])*pb['thickness']
            if min(ay+pa['thickness'],max(by,bfinish))-max(ay,min(by,bfinish))<1e-6:break
            own=Polygon([(q[0],q[2]) for q in pa['polygon']])
            neighbour=Polygon([(dot(q,axes[0]),dot(q,axes[2])) for q in pts])
            if own.intersection(neighbour).area<1e-6:break
            proposed=own.difference(neighbour.buffer(1/32,join_style='mitre'))
            if proposed.geom_type!='Polygon' or proposed.interiors:continue
            if any(not proposed.buffer(1e-5).covers(edge) for edge in protected_lines(first)):continue
            # A selected attachment would prevent this cut. Leaving the competing
            # shapes in the review delivery keeps a true source conflict visible.
            ring=[[x,ay,z] for x,z in list(proposed.exterior.coords)[:-1]]
            made=Assembly(first['title'],profiles).polygon('GUSSET',ring,pa['thickness'],
                normal=pa['normal'],basis=pa['basis'],description=pa['description'])
            for key in ('polygon','faces','bounds'):pa[key]=made[key]
            if 'bounds' in first:first['bounds']=bounds([f for p in first['parts'] for f in p['faces']])
            first.setdefault('notes',[]).append('A: opposing gusset free edges have 1/32 in separation outside the source welds and effective sections.')
            break
