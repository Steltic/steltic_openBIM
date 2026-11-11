"""One real gusset per distinct plate plane and one screw group per web ply."""
from collections import defaultdict
from .assembly_templates import web_faces
from .pilots.model import add,mul
from .review_assemblies import hull


def gussets(assembly,profiles,ends,layouts):
    planes=defaultdict(list)
    contour=[(-4.,-4.),(4.,-4.),(4.,4.),(-4.,4.)]
    for n,direction,member in ends:
        across=[-direction[2],0.,direction[0]]
        tip=layouts[n][0][-1]+2
        for side in (-3.,3.):
            q=add(mul(direction,tip),mul(across,side))
            contour.append((q[0],q[2]))
        for i,(face,side,thickness) in enumerate(web_faces(profiles,member['profile_id'])):
            mid=round(face+side*.125/2,6)
            planes[mid].append((n,i,face,side,thickness,direction))
    outline=hull(contour)
    for index,(mid,plies) in enumerate(sorted(planes.items()),1):
        label='P'+str(index)
        assembly.polygon(label,[[x,mid-.0625,z] for x,z in outline],.125,basis='A',
                         description='One continuous 1/8 in gusset shared by the actual adjoining web plies')
        for n,i,face,side,thickness,direction in plies:
            stations,offsets=layouts[n];across=[-direction[2],0.,direction[0]]
            # Opposed screws land at distinct stations in the common plate.
            # Drive from the outer channel web face through the gusset.
            shift=side*.1875 if sum(item[0]==n for item in plies)>1 else 0.
            points=[add(mul(direction,s+shift),add(mul(across,w),[0.,face-side*thickness,0.]))
                    for s in stations for w in offsets]
            assembly.fastener(f'F{index}-{n}-PLY{i+1}',points,[0.,side,0.],.25,.125+thickness,
                ['M'+str(n),label],f'{len(points)} No.14 screws through one channel web ply and shared gusset',
                'A',screw=True)
