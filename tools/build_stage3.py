"""Rebuild the three pilots from immutable Stage 2/3 replay packages.

Run with --sources DIR containing hr22/cfs16/cfs8/bim_package.json.
No original job or source repository is executed or written by this command.
"""
import argparse
import json
from pathlib import Path
from steltic_openbim.pilots import hr22,cfs16,cfs8
from steltic_openbim.pilots.presentation import write_viewer,render
from steltic_openbim.pilots.checks import inspect
from steltic_openbim.review import questions


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--sources',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--render',action='store_true')
    args=ap.parse_args(); catalog=json.loads((Path(hr22.__file__).parent/'catalog.json').read_text())
    for key,recipe in [('hr22',hr22),('cfs16',cfs16),('cfs8',cfs8)]:
        source=json.loads((args.sources/key/'bim_package.json').read_text(encoding='utf-8'))
        p=recipe.build(source,catalog); dest=args.output/key; dest.mkdir(parents=True,exist_ok=True)
        report=inspect(p,source,key)
        (dest/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        (dest/'coordination_questions.json').write_text(json.dumps(questions(p),indent=2)+'\n',encoding='utf-8')
        if not report['passed']: raise ValueError('Pilot checks failed: '+str([q for q in report['checks'] if not q['passed']]))
        (dest/'bim_package.json').write_text(json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        write_viewer(p,key,dest)
        if args.render: render(p,key,dest)
        print(key,p['readiness']['status'],p['readiness']['counts'])
        print('findings',[(f['code'],f['message'],len(f['entity_ids'])) for f in p['readiness']['findings'] if f['code']!='coordination_required'])
        print('unmapped',p['review']['unmapped_drawing_records'])


if __name__=='__main__': main()
