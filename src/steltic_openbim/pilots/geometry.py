"""Design-review meshes. Section strips omit rolled fillets and bend radii.

Source radii remain in profile data. These meshes are deliberately not shop
solids: holes, weld preparations and unresolved plate outlines are not invented.
"""
import math
from .model import add,sub,mul,cross,unit,length

COLORS={'primary':'#315b72','secondary':'#668fa1','walls':'#557f73','bracing':'#ce7844','connections':'#b89335','roof':'#a0aca5','floor':'#c2cbc4','interface':'#b75661'}


def layer(kind):
    if kind in ('column','girder','moment_beam','rafter','endwall_post','door_header'): return 'primary'
    if kind in ('strap','hold_down_rod','chord','collector','junction_collector'): return 'bracing'
    if kind in ('stud','top_track','bottom_track','stud_bridging','squash_block'): return 'walls'
    if 'roof' in kind or 'truss' in kind: return 'roof'
    if kind in ('floor','deck_envelope'): return 'floor'
    if kind in ('strap_wall_zone','cladding_envelope'): return 'interface'
    return 'secondary'


def rect(x0,y0,x1,y1): return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]


def strips(profile,profiles):
    d=profile['dimensions']; family=profile['family']
    if family in ('i','i_tapered'):
        h,b,tf,tw=[d[k] for k in ['d','bf','tf','tw']]
        if family=='i_tapered':
            tip=d.get('tf_tip',max(.1,tf-b/24));root=d.get('tf_root',tf+b/24)
            return [[[-b/2,-h/2],[b/2,-h/2],[b/2,-h/2+tip],[tw/2,-h/2+root],[-tw/2,-h/2+root],[-b/2,-h/2+tip]],rect(-tw/2,-h/2+root,tw/2,h/2-root),[[-b/2,h/2],[b/2,h/2],[b/2,h/2-tip],[tw/2,h/2-root],[-tw/2,h/2-root],[-b/2,h/2-tip]]]
        return [rect(-b/2,-h/2,b/2,-h/2+tf),rect(-tw/2,-h/2+tf,tw/2,h/2-tf),rect(-b/2,h/2-tf,b/2,h/2)]
    if family in ('channel','z'):
        h,b,t,lip=[d[k] for k in ['d','b','t','lip']]
        result=[rect(-t/2,-h/2+t,t/2,h/2-t)]
        for sign in [-1,1]:
            direction=1 if family=='channel' else sign
            x0,x1=sorted([-direction*t/2,direction*(b-t/2)])
            y0,y1=sorted([sign*(h/2-t),sign*h/2])
            result.append(rect(x0,y0,x1,y1))
            if lip:
                angle=math.radians(profile.get('lip_angle_deg',90)); a=[direction*(b-t/2),sign*(h/2-t/2)]
                v=[-direction*math.cos(angle)*lip,-sign*math.sin(angle)*lip]; n=unit([-v[1],v[0]])
                result.append([add(a,mul(n,-t/2)),add(a,mul(n,t/2)),add(add(a,v),mul(n,t/2)),add(add(a,v),mul(n,-t/2))])
        return result
    if family=='built_up':
        out=[]
        for c in profile['components']:
            ang=math.radians(c['rotation_deg']); co,si=math.cos(ang),math.sin(ang)
            out += [[[co*x-si*y+c['offset'][0],si*x+co*y+c['offset'][1]] for x,y in p] for p in strips(profiles[c['profile_id']],profiles)]
        return out
    if family=='flat': return [rect(-d['width']/2,-d['thickness']/2,d['width']/2,d['thickness']/2)]
    if family=='angle': return [rect(0,0,d['b'],d['t']),rect(0,d['t'],d['t'],d['h'])]
    if family=='rhs':
        h,b,t=d['h'],d['b'],d['t']; return [rect(-b/2,-h/2,b/2,-h/2+t),rect(-b/2,h/2-t,b/2,h/2),rect(-b/2,-h/2+t,-b/2+t,h/2-t),rect(b/2-t,-h/2+t,b/2,h/2-t)]
    if family=='round': return [[[d['d']/2*math.cos(i*math.pi/8),d['d']/2*math.sin(i*math.pi/8)] for i in range(16)]]
    if family=='chs':
        outer=d['d']/2;inner=outer-d['t'];n=32
        return [[[r*math.cos(j*2*math.pi/n),r*math.sin(j*2*math.pi/n)] for r,j in ((outer,i),(outer,i+1),(inner,i+1),(inner,i))] for i in range(n)]
    if family=='box_envelope': return [rect(-d['width']/2,-d['depth']/2,d['width']/2,d['depth']/2)]
    raise ValueError('Unsupported preview profile '+family)


def extrude(poly,a,b,y):
    x=unit(sub(b,a)); z=cross(x,y)
    rings=[[add(p,add(mul(y,u),mul(z,v))) for u,v in poly] for p in [a,b]]
    out=[rings[0][::-1],rings[1]]
    out.extend([rings[0][i],rings[0][(i+1)%len(poly)],rings[1][(i+1)%len(poly)],rings[1][i]] for i in range(len(poly)))
    return out


def clip_axis(a,b,limits):
    if limits is None: return 0,1
    low,high=0.,1.
    for i,(lo,hi) in enumerate(limits):
        v=b[i]-a[i]
        if abs(v)<1e-10:
            if not lo<=a[i]<=hi: return None
        else:
            t0,t1=sorted([(lo-a[i])/v,(hi-a[i])/v]); low=max(low,t0); high=min(high,t1)
    return (low,high) if high>low+1e-9 else None


def member_faces(member,profiles,limits=None):
    a,b=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]; vector=sub(b,a); extent=length(vector)
    clip=clip_axis(a,b,limits)
    if clip is None: return []
    lo,hi=[v*extent for v in clip]; d=unit(vector); y=member['local_y']; profile=profiles[member['profile_id']]
    base=strips(profile,profiles); rbs=member.get('rbs'); cope=member.get('cope')
    stations={lo,hi}
    from ..member_slots import validated,cut_sections
    slots=validated(member.get('slots',[]),extent)
    if slots and (rbs or cope):raise ValueError('Combined slots and flange cuts require an explicit selected solid')
    for slot in slots:
        for station in (slot['start_in'],slot['end_in']):
            if lo<station<hi:stations.add(station)
    cuts=[]
    if rbs:
        cuts=rbs.get('cuts') or [dict(rbs,end=end) for end in rbs.get('ends',[0,1])]
        for cut in cuts:
            if cut['end'] not in (0,1) or cut['a_in']<0 or cut['b_in']<=0 or cut['c_in']<=0:
                raise ValueError('An RBS cut needs an explicit end and positive source cut dimensions')
            for s in [cut['a_in']+cut['b_in']*i/12 for i in range(13)]:
                pos=s if cut['end']==0 else extent-s
                if lo<pos<hi:stations.add(pos)
    if cope:
        for s in [cope['length_in'],extent-cope['length_in']]:
            if lo<s<hi: stations.add(s)
    stations=sorted(stations); faces=[]
    def shape(at,index):
        poly=[p[:] for p in base[index]]
        if cuts and index in (0,2):
            reduction=0.
            for selected in cuts:
                s=(at if selected['end']==0 else extent-at)-selected['a_in']; b0=selected['b_in']; c=selected['c_in']; radius=(b0*b0+4*c*c)/(8*c)
                amount=max(0,math.sqrt(max(0,radius*radius-(s-b0/2)**2))-(radius-c)) if 0<=s<=b0 else 0
                reduction=max(reduction,amount)
            for p in poly:p[0]+=-reduction if p[0]>0 else reduction
        return poly
    z=cross(d,y)
    for s,t in zip(stations,stations[1:]):
        coped=cope and ((0 in cope.get('ends',[0,1]) and (s+t)/2<cope['length_in']) or (1 in cope.get('ends',[0,1]) and extent-(s+t)/2<cope['length_in']))
        for index in range(len(base)):
            if coped and index==2: continue
            if slots:
                for poly in cut_sections([base[index]],slots,(s+t)/2):
                    faces.extend(extrude(poly,add(a,mul(d,s)),add(a,mul(d,t)),y))
                continue
            rings=[]
            for at in [s,t]:
                poly=shape(at,index)
                if coped and index==1:
                    ceiling=profile['dimensions']['d']/2-cope['depth_in']
                    for p in poly: p[1]=min(p[1],ceiling)
                rings.append([add(add(a,mul(d,at)),add(mul(y,u),mul(z,v))) for u,v in poly])
            faces.extend([rings[0][::-1],rings[1]])
            faces.extend([rings[0][i],rings[0][(i+1)%len(rings[0])],rings[1][(i+1)%len(rings[0])],rings[1][i]] for i in range(len(rings[0])))
    return faces


def part_lines(part):
    """Keep explicitly declared reference polylines; never infer a solid from them."""
    g = part.get('geometry', {})
    return [g['points']] if g.get('type') == 'polyline' else []


def part_faces(part,profiles):
    g=part['geometry']; kind=g['type']; a=g.get('origin')
    if kind=='mesh':return g['faces']
    if kind=='box':
        x,y=g['x_axis'],g['y_axis']; z=cross(x,y); sx,sy,sz=g['size']; b=add(a,mul(z,sz))
        return extrude([[0,0],[sx,0],[sx,sy],[0,sy]],a,b,x)  # local z cross x == y
    if kind=='cylinder':
        axis=g['axis']; y=unit(cross([0,0,1],axis)) if abs(axis[2])<.99 else [1,0,0]
        poly=[[g['radius']*math.cos(i*math.pi/6),g['radius']*math.sin(i*math.pi/6)] for i in range(12)]
        return extrude(poly,a,add(a,mul(axis,g['length'])),y)
    if kind=='extruded_profile':
        return [f for poly in strips(profiles[g['profile_id']],profiles) for f in extrude(poly,a,add(a,mul(g['axis'],g['length'])),g['local_y'])]
    return []
