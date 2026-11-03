"""Build three actual HR/OpenSees geometry previews from IFC handoff geometry.

The separately recorded framing proposals are demonstration engineering inputs,
not architectural facts, analysis results or completed designs. No prior HR
design outputs are read. Actual HR engine calls create and export every member.
"""
import argparse
from collections import Counter,defaultdict
import json
import math
from pathlib import Path
import runpy
import sys

from shapely.geometry import Point,Polygon,LineString
from shapely.ops import unary_union


def proposal(geometry,key):
    grids=geometry['grids'];xs=sorted({round(r['points_m'][0][0]/.3048,5) for r in grids if r['direction']=='U'})
    ys=sorted({round(r['points_m'][0][1]/.3048,5) for r in grids if r['direction']=='V'})
    slabs=[]
    for item in geometry['surfaces']:
        for surface in item['top_surfaces']:
            ring=[[round(v/.3048,5) for v in p] for p in surface['boundary_m']]
            zvals=[p[2] for p in ring]
            if max(zvals)<=.01:continue
            slabs.append(dict(name=item['name'],ring=ring,poly=Polygon([(p[0],p[1]) for p in ring]),flat=max(zvals)-min(zvals)<.001,z=max(zvals)))
    members=[];seen=set()
    def add(kind,a,b,section,source,release='both',strong='X'):
        a=tuple(round(v,5) for v in a);b=tuple(round(v,5) for v in b)
        if math.dist(a,b)<.01:raise ValueError('Zero-length proposed member')
        k=(kind,tuple(sorted((a,b))))
        if k in seen:return
        seen.add(k);members.append(dict(kind=kind,a_ft=a,b_ft=b,section=section,release=release,strong_axis=strong,source=source))
    # Grid framing on each supplied architectural floor, preserving each outline.
    byz=defaultdict(list)
    for s in slabs:
        if s['flat']:byz[s['z']].append(s)
    for z,items in byz.items():
        for s in items:
            poly=s['poly'];inside=lambda x,y:poly.buffer(.0001).covers(Point(x,y))
            if key.startswith('02') and s['name'].startswith('Gym'):
                for x in xs:
                    if poly.bounds[0]-.01<=x<=poly.bounds[2]+.01:add('beam',(x,poly.bounds[1],z),(x,poly.bounds[3],z),'W36X150',s['name']+'; proposed long-span roof member',release='none')
                for y in (poly.bounds[1],poly.bounds[3]):
                    xg=[x for x in xs if inside(x,y)]
                    for a,b in zip(xg,xg[1:]):add('beam',(a,y,z),(b,y,z),'W24X76',s['name'],release='none')
                continue
            for y in ys:
                for a,b in zip(xs,xs[1:]):
                    if poly.buffer(.0001).covers(LineString([(a,y),(b,y)])):
                        add('beam',(a,y,z),(b,y,z),'W24X76',s['name'],release='none' if key.startswith('02') else 'both')
            for x in xs:
                yg=[y for y in ys if inside(x,y)]
                for a,b in zip(yg,yg[1:]):
                    if poly.buffer(.0001).covers(LineString([(x,a),(x,b)])):
                        add('beam',(x,a,z),(x,b,z),'W24X76',s['name'],release='none' if key.startswith('02') else 'both')
    # True gable rafters come from the two roof planes, not a level bounding box.
    if key.startswith('03'):
        for s in slabs:
            if s['flat']:continue
            y0,y1=s['poly'].bounds[1],s['poly'].bounds[3]
            def height(y):return next(p[2] for p in s['ring'] if abs(p[1]-y)<.001)
            for x in xs:add('beam',(x,y0,height(y0)),(x,y1,height(y1)),'W36X150',s['name']+'; proposed portal rafter',release='none')
            for y in (y0,y1):
                for a,b in zip(xs,xs[1:]):add('beam',(a,y,height(y)),(b,y,height(y)),'W18X50',s['name']+'; proposed eave/ridge member')
    # Column locations are grid points needed by the proposed primary framing.
    heights=defaultdict(set)
    for m in members:
        for x,y,z in (m['a_ft'],m['b_ft']):
            if key.startswith('03') and abs(y-40)<.01:continue  # ridge stays clear-span
            heights[x,y].add(z)
    for (x,y),zs in sorted(heights.items()):
        for a,b in zip([0,*sorted(zs)],sorted(zs)):
            strong='Y' if key.startswith('03') else 'X'
            add('col',(x,y,a),(x,y,b),'W14X90','Engineering preview column on architectural grid',release='base' if a==0 else 'none',strong=strong)
    # Office: explicit chevron core bays from the engineering brief. Split the
    # upper beam at the brace intersection so the OpenSees topology is connected.
    if key.startswith('01'):
        zlevels=sorted(byz)
        for low,high in zip([0,*zlevels],zlevels):
            for a,b in [((30,30),(30,60)),((120,30),(120,60)),((60,30),(90,30)),((60,60),(90,60))]:
                apex=((a[0]+b[0])/2,(a[1]+b[1])/2,high);aa=(*a,high);bb=(*b,high)
                members[:]=[m for m in members if not (m['kind']=='beam' and {m['a_ft'],m['b_ft']}=={aa,bb})]
                add('beam',aa,apex,'W24X76','SCBF chevron upper beam; proposed split',release='I')
                add('beam',apex,bb,'W24X76','SCBF chevron upper beam; proposed split',release='J')
                for end in (a,b):add('brace',(*end,low),apex,'HSS8X8X1/2','SCBF core bay proposal from engineering brief')
    # Split columns where a beam from an adjacent wing connects mid-height.
    # All such elevations were already collected above; no ghost floor is added.
    nodes={p for m in members for p in (m['a_ft'],m['b_ft'])};adj=defaultdict(set)
    for m in members:adj[m['a_ft']].add(m['b_ft']);adj[m['b_ft']].add(m['a_ft'])
    visited=set();components=[]
    for n in nodes:
        if n in visited:continue
        todo=[n];comp=set()
        while todo:
            q=todo.pop()
            if q in comp:continue
            comp.add(q);todo.extend(adj[q]-comp)
        visited.update(comp);components.append(len(comp))
    assert len(components)==1,components
    checks=dict(single_connected_component=True,zero_length_members=0,
        source_sha256=geometry['source_sha256'],source_surfaces=len(slabs),grid_x_ft=xs,grid_y_ft=ys,
        node_bounds_ft=[[min(p[i] for p in nodes),max(p[i] for p in nodes)] for i in range(3)])
    if key.startswith('01'):
        assert checks['node_bounds_ft']==[[0,150],[0,90],[0,67]]
        assert sum(m['kind']=='brace' for m in members)==40
        checks['five_storeys_and_40_core_braces']=True
    if key.startswith('02'):
        assert not any(m['kind']=='beam' and 140.01<(m['a_ft'][0]+m['b_ft'][0])/2<195.99 and 56.01<(m['a_ft'][1]+m['b_ft'][1])/2<111.99 and m['a_ft'][2]<25 for m in members)
        assert not any(m['kind']=='col' and m['a_ft'][0]==168 and m['a_ft'][1]==84 for m in members)
        checks.update(no_intermediate_gym_floor=True,no_interior_grid_D_gym_column=True,roof_heights_ft=[24,26,36])
    if key.startswith('03'):
        rafters=[m for m in members if 'portal rafter' in m['source']]
        assert len(rafters)==18 and all(sorted([m['a_ft'][2],m['b_ft'][2]])==[26,36] for m in rafters)
        assert not any(m['kind']=='col' and m['a_ft'][1]==40 for m in members)
        checks.update(true_roof_26_36_ft=True,office_roof_16_ft=True,no_ridge_columns=True,portal_rafter_segments=18)
    return dict(schema='steltic.architect_demo_framing_proposal',case=key,
        status='PRELIMINARY MODEL CREATION ONLY - not analysed, sized or connection-designed',
        sections_basis='Demonstration starting sections selected here by engineering; absent from the architectural IFC.',
        limits=['Loads, stability, diaphragm behaviour and member/connection capacities are not checked in this preview.',
                'The fresh full HR run is separate. These files are not completed design outputs.',
                'Warehouse longitudinal bracing and secondary purlins require HR design; no door-crossing braces are proposed.',
                'School moment-member releases are preliminary; HR must resolve the specified frame-line releases.'],
        checks=checks,members=members)


CFG_TEXT='''# Preliminary engineering geometry from the reviewed architectural IFC.
# Sections are explicit STARTING PROPOSALS, not architect-specified or checked.
import json
from pathlib import Path
import openseespy.opensees as ops
import engine3d as E
proposal=json.loads(Path(__file__).with_name("framing_proposal.json").read_text())
rows=proposal["members"]
points=sorted({tuple(p) for r in rows for p in (r["a_ft"],r["b_ft"])})
tags={p:i+1 for i,p in enumerate(points)}
def custom_build(cfg,transf):
    ops.wipe();ops.model("basic","-ndm",3,"-ndf",6)
    for p,t in tags.items():
        ops.node(t,*[v*12 for v in p])
        if p[2]==0:ops.fix(t,1,1,1,0,0,0)
    ops.uniaxialMaterial("Elastic",1,E.E)
    elements=[]
    for et,r in enumerate(rows,1):
        a=tags[tuple(r["a_ft"])];b=tags[tuple(r["b_ft"])]
        kind=r["kind"];sec=r["section"]
        if kind=="col":E.add_column(et,a,b,sec,r["strong_axis"])
        elif kind=="brace":ops.element("Truss",et,a,b,E.HSS[sec],1)
        else:E.add_beam(et,a,b,sec,releases=(r["release"],"none"))
        elements.append((et,kind,sec,a,b))
    zs=sorted({p[2]*12 for p in points})
    return dict(cm={},present={},z=zs,NF=len(zs)-1,ele=elements,diaphragm="not_assigned_in_geometry_preview")
cfg=dict(custom_build=custom_build,diaphragm_mass="builder",arch=proposal["status"])
'''


def build_case(folder,engine):
    geometry=json.loads((folder/'architectural_geometry.json').read_text());p=proposal(geometry,folder.name)
    out=folder/'hr_model_creation';out.mkdir(exist_ok=True)
    (out/'framing_proposal.json').write_text(json.dumps(p,indent=2))
    (out/'cfg.py').write_text(CFG_TEXT)
    sys.path.insert(0,str(engine));import engine3d as E;import openseespy.opensees as ops
    cfg=runpy.run_path(str(out/'cfg.py'))['cfg'];info=E.build(cfg,'Linear')
    assert len(ops.getEleTags())==len(p['members'])
    assert len(ops.getNodeTags())==len({tuple(x) for r in p['members'] for x in (r['a_ft'],r['b_ft'])})
    export=Path(E.export_model(cfg,str(out),name=folder.name,transf='Linear')[0])
    text=export.read_text();body=text[text.index('import math'):].split('# --- quick self-check ---')[0]
    export.write_text('"""PRELIMINARY HR GEOMETRY MODEL - no structural analysis or capacity checks.\nSections and restraints are engineering proposals, not architectural facts.\nNo masses/diaphragms assigned; this script checks model creation only.\n"""\n'+body+'\nprint("nodes:",len(ops.getNodeTags()),"elements:",len(ops.getEleTags()))\n')
    # Replay the exact exported commands; compare every real node and element.
    nodes={t:ops.nodeCoord(t) for t in ops.getNodeTags()};edges={t:ops.eleNodes(t) for t in ops.getEleTags()}
    runpy.run_path(str(export))
    assert nodes=={t:ops.nodeCoord(t) for t in ops.getNodeTags()}
    assert edges=={t:ops.eleNodes(t) for t in ops.getEleTags()}
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig=plt.figure(figsize=(11,8));ax=fig.add_subplot(111,projection='3d');colors={'col':'#2166ac','beam':'#239569','brace':'#c34747'}
    for r in p['members']:
        a,b=r['a_ft'],r['b_ft'];ax.plot([a[0],b[0]],[a[1],b[1]],[a[2],b[2]],color=colors[r['kind']],lw=.8)
    bb=p['checks']['node_bounds_ft'];ax.set_box_aspect([b-a for a,b in bb]);ax.view_init(22,-60)
    ax.set(xlabel='X (ft)',ylabel='Y (ft)',zlabel='Z (ft)',title=folder.name+' | HR/OpenSees geometry\nPreliminary engineering proposal - no analysis or capacity checks')
    fig.tight_layout();fig.savefig(out/'hr_geometry.png',dpi=160);plt.close(fig)
    result=dict(case=folder.name,nodes=len(nodes),elements=len(edges),member_types=dict(Counter(r['kind'] for r in p['members'])),
        exported_model_replay_exact=True,checks=p['checks'],design_status=p['status'])
    (out/'verification.json').write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--hr-engine',type=Path,required=True);parser.add_argument('--examples',type=Path,required=True);args=parser.parse_args()
    results=[]
    for folder in sorted(args.examples.iterdir()):
        if folder.is_dir() and (folder/'architectural_geometry.json').is_file():
            results.append(build_case(folder,args.hr_engine.resolve()));print(json.dumps(results[-1]),flush=True)
    (args.examples/'hr_model_verification.json').write_text(json.dumps(results,indent=2))
