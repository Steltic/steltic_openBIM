"""Closed section-transition envelopes, preserving hollow interiors."""


def rings(profile):
    d=profile['dimensions']
    if profile['family']=='i':
        h,b,tf,tw=(d[k] for k in ('d','bf','tf','tw'))
        return [[[-b/2,-h/2],[b/2,-h/2],[b/2,-h/2+tf],
                 [tw/2,-h/2+tf],[tw/2,h/2-tf],[b/2,h/2-tf],
                 [b/2,h/2],[-b/2,h/2],[-b/2,h/2-tf],
                 [-tw/2,h/2-tf],[-tw/2,-h/2+tf],[-b/2,-h/2+tf]]]
    if profile['family']=='rhs':
        h,b,t=(d[k] for k in ('h','b','t'))
        return [[[-x,-y],[x,-y],[x,y],[-x,y]] for x,y in ((b/2,h/2),(b/2-t,h/2-t))]
    raise ValueError('Unsupported transition profile')


def loft(lower,upper,height):
    if lower['family']!=upper['family'] or height<=0:raise ValueError('Incompatible transition')
    levels=[[[[-v,u,z] for u,v in ring] for ring in rings(profile)]
            for profile,z in ((lower,-height),(upper,0))]
    faces=[]
    for index,(bottom,top) in enumerate(zip(*levels)):
        for i in range(len(bottom)):
            j=(i+1)%len(bottom);face=[bottom[i],bottom[j],top[j],top[i]]
            faces.append(face if index==0 else face[::-1])
    for level,reverse in zip(levels,(True,False)):
        if len(level)==1:
            faces.append(level[0][::-1] if reverse else level[0])
        else:
            outer,inner=level
            for i in range(4):
                j=(i+1)%4;face=[outer[i],outer[j],inner[j],inner[i]]
                faces.append(face[::-1] if reverse else face)
    return faces
