"""Shared immutable evidence lookup for the model-only 61-building sweep."""
import hashlib,json,os,sys,zipfile
from pathlib import Path
ROOT=Path(os.environ.get('STELTIC_SWEEP_WORKSPACE',Path(__file__).resolve().parents[2])).resolve()
REPO=ROOT/'work/repos/steltic_openBIM'
sys.path[:0]=[str(REPO/'src'),str(REPO/'tools/architect_demo')]
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cases():return read(ROOT/'outputs/workflow_61/sweep_plan.json')['cases']
def folder(row):
    return ROOT/'outputs/workflow_61'/f'batch{row["batch"]:02}'/row['id']
def input_folder(row):
    return ROOT/'outputs/workflow_six'/row['baseline_case'] if row['batch']==0 else folder(row)
def evidence(row):
    from steltic_openbim.drawing_workflow import fingerprint
    path=ROOT/row['existing_coordination_model'];model=read(path)
    package=read(path.parent/'bim_package.json');location=str(path.parent/'bim_package.json')
    if fingerprint(package)!=model['source_sha256']:
        matched=False
        for bundle in [REPO/'docs/stage3/pilots.zip',REPO/'src/steltic_openbim/review_data/inputs.zip']:
            with zipfile.ZipFile(bundle) as z:
                for name in z.namelist():
                    if not name.endswith('/bim_package.json') or row['id'] not in name.split('/'):continue
                    candidate=json.loads(z.read(name))
                    if fingerprint(candidate)==model['source_sha256']:
                        package=candidate;location=str(bundle)+'!'+name;matched=True;break
            if matched:break
    assert fingerprint(package)==model['source_sha256'],row['id']+' immutable source mismatch'
    return model,package,location
def job_source(row,package):
    default=Path.home()/'drawings'/('jobs' if row['module']=='HR' else 'gold_cfs_jobs_2026-10-31/jobs_cfs')
    base=Path(os.environ.get('STELTIC_'+row['module']+'_GOLD_ROOT',default))
    path=base/package['building_id'];assert (path/'cfg.py').is_file(),str(path)
    return path
