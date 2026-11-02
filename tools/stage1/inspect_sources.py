import ast
import argparse
import csv
import hashlib
import json
import pathlib
import re
from collections import Counter

parser=argparse.ArgumentParser(description='Snapshot supplied design evidence without executing job code.')
parser.add_argument('--root',type=pathlib.Path,default=pathlib.Path(r'C:\Users\mikea\drawings'))
parser.add_argument('--work-dir',type=pathlib.Path,default=pathlib.Path(__file__).parent)
args=parser.parse_args()
ROOT = args.root
OUT = args.work_dir
OUT.mkdir(parents=True,exist_ok=True)

def natural(value):
    return tuple(int(v) if v.isdigit() else v for v in re.split(r'(\d+)', str(value)))

def walks(obj, path='$'):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walks(value, path + '/' + str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walks(value, path + '/' + str(index))
    else:
        yield path, obj

def source_assignments(source):
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            name = ', '.join(ast.unparse(t) for t in node.targets)
            if name == 'cfg' or name.startswith('cfg[') or any(w in name.lower() for w in ['outline','coord','grid','height','frame','span','opening','layout','segs','levels','roof','plan','n_frames','length_ft','slope']):
                if name == 'cfg' and isinstance(node.value, ast.Call):
                    for kw in node.value.keywords:
                        if kw.arg: out.append((node.lineno, 'cfg.' + kw.arg, ast.unparse(kw.value)))
                elif name == 'cfg' and isinstance(node.value, ast.Dict):
                    for k,v in zip(node.value.keys,node.value.values):
                        out.append((node.lineno, 'cfg.' + ast.unparse(k), ast.unparse(v)))
                else: out.append((node.lineno,name,ast.unparse(node.value)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='cfg' and node.func.attr=='update':
            for kw in node.keywords:
                if kw.arg: out.append((node.lineno,'cfg.'+kw.arg,ast.unparse(kw.value)))
    return sorted(out)

manifest=[]; corpus=[]
for module, base, package in [('HR',ROOT/'jobs','calc_package.json'),('CFS',ROOT/'gold_cfs_jobs_2026-10-31/jobs_cfs','calc_package_cfs.json')]:
    for job in sorted([p for p in base.iterdir() if p.is_dir()],key=lambda p:natural(p.name)):
        p=json.loads((job/'design'/package).read_text(encoding='utf-8-sig'))
        cfg=(job/'cfg.py').read_text(encoding='utf-8-sig')
        txt=(job/'viewer_3d.html').read_text(encoding='utf-8-sig')
        marker=re.search(r'\b(?:const|let|var)\s+DATA\s*=\s*',txt)
        view,_=json.JSONDecoder().raw_decode(txt,marker.end())
        assigns=source_assignments(cfg)
        stem=('HR_' if module=='HR' else '')+job.name
        lines=[f'{module} {job.name}',str(ast.get_docstring(ast.parse(cfg)) or '')[:1800], 'CONFIG GEOMETRY:']
        geometry=[]
        for lineno,key,value in assigns:
            if any(w in key.lower() for w in ['arch','system','title','structure_kind','frame','height','coord','grid','span','outline','plan','layout','level','position','xpos','length_ft','stud','joist','opening','slope','spacing','base','roof']):
                geometry.append((lineno,key,value))
                lines.append(f'cfg.py:{lineno} {key} = {value[:300]}')
        lines.append('VIEWER: '+str(view['meta'].get('subtitle')))
        lines.append('CAVEAT: '+str(view['meta'].get('caveat')))
        secs=Counter(e['sec'] for e in view['elements'])
        lines.append('SECTIONS: '+str(list(secs)))
        lines.append('JSON TABLES: '+str({k:len(v) for k,v in p.items() if isinstance(v,list)}))
        for key in ['plan_geometry','braced_wall_layout','braced_bay_layout','segment_framing','design_model','drawing_notes','delegated_design','retrofit_scope','existing_structure_interface','podium_handoff','frame_layout','wall_to_floor_detail','framing','gravity_framing','schedules','detailing']:
            if key in p:
                lines.append(f'JSON {key}: '+json.dumps(p[key],ensure_ascii=False)[:3600])
        lines.append('CONNECTION RECORDS:')
        for i,c in enumerate(p.get('connections',[])):
            lines.append(f'[{i}] {c["id"]}: {c.get("type",c.get("joint",""))}\n  {c.get("components",c.get("selection",""))}')
        (OUT/(stem+'.txt')).write_text('\n'.join(lines),encoding='utf-8')
        files=[]
        for f in sorted(job.rglob('*')):
            if not f.is_file():continue
            relative=f.relative_to(job).as_posix()
            # Exclude reference-library extracts and generated figures: not design authorities.
            if relative.startswith(('rag/','figs/')):continue
            b=f.read_bytes()
            rec={'module':module,'building':job.name,'file':relative,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
            manifest.append(rec);files.append(rec)
        corpus.append({'module':module,'building':job.name,'folder':str(job),'root':str(ROOT),'package':p,'cfg':cfg,'assignments':assigns,'geometry_assignments':geometry,'viewer':view,'source_files':files})
(OUT/'source_manifest_before.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(OUT/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'buildings':len(corpus),'source_files':len(manifest),'bytes':sum(x['bytes'] for x in manifest)}))
