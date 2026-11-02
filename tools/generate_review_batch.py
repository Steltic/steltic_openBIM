"""Reproduce the 23 explicitly fictional design review sets without either engine."""
import argparse,json,zipfile
from pathlib import Path
from steltic_openbim.review_cases import CASES,evidence
from steltic_openbim.drawing_workflow import initial_state,write_json,DrawingStore
from steltic_openbim.design_scenarios import adopt_scenario
from steltic_openbim.drawing_pdf import generate

def main():
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--author',required=True)
    ap.add_argument('--confirm-fictional',action='store_true',required=True);ap.add_argument('--cases',nargs='*');args=ap.parse_args()
    keys=args.cases or ['hr22','cfs16','cfs8',*CASES];root=Path(__file__).resolve().parents[1];reports={}
    for key in keys:
        if key in CASES:package=evidence(key)['package']
        else:
            if key not in ('hr22','cfs16','cfs8'):raise ValueError('Unknown registered case '+key)
            with zipfile.ZipFile(root/'docs/stage3/pilots.zip') as z:package=json.loads(z.read(key+'/bim_package.json'))
        state=initial_state(package,1);state=adopt_scenario(package,state,dict(revision=1,source_model_sha256=state['source_model_sha256'],confirm_fictional=True,author=args.author))
        dest=args.output/key;report=generate(package,state,dest);write_json(dest/'state.json',state);write_json(dest/'information_requests.json',DrawingStore.questions(state));write_json(dest/'bim_package.json',package)
        reports[key]=dict(sheets=len(report['sheets']),counts=report['counts'],source_sha256=report['source_model_sha256'],pdf_sha256=report['pdf_sha256'])
        print(key,reports[key],flush=True)
    args.output.mkdir(parents=True,exist_ok=True)
    # Include previously generated cases when resuming a partial batch.
    reports={}
    for path in sorted(args.output.glob('*/drawing_manifest.json')):
        r=json.loads(path.read_text(encoding='utf8'))
        reports[path.parent.name]=dict(sheets=len(r['sheets']),counts=r['counts'],source_sha256=r['source_model_sha256'],pdf_sha256=r['pdf_sha256'])
    write_json(args.output/'batch_manifest.json',reports)

if __name__=='__main__':main()
