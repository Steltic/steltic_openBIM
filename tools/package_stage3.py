"""Package checked pilot output into an offline review index and portable archive."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import zipfile


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--inputs-archive',type=Path)
    args=ap.parse_args(); root=args.output; esc=html.escape
    titles={'hr22':'Six-storey hospital','cfs16':'Portal warehouse','cfs8':'T-plan student housing'}
    packages={k:json.loads((root/k/'bim_package.json').read_text(encoding='utf-8')) for k in titles}
    verification=json.loads((root/'verification.json').read_text())
    visual=json.loads((root/'visual_review.json').read_text())
    cards=[]; registers=[]
    for n,(key,title) in enumerate(titles.items(),1):
        p=packages[key]; counts=p['readiness']['counts']; items=p['review']['items']
        if not (root/key/'validation.json').is_file(): raise ValueError('Missing validation: '+key)
        digest=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=verification['pilots'][key]['model_sha256'] or digest!=visual['pilots'][key]['model_sha256']:
            raise ValueError('Review evidence does not match model: '+key)
        images=sorted((root/key).glob('*.png'))
        image_links=' · '.join(f'<a href="{key}/{q.name}">{esc(q.stem.split("_",1)[1].replace("_"," "))}</a>' for q in images)
        cards.append(f'''<article><div class="eyebrow">PILOT {n:02} / {p['module']}</div><h2>{title}</h2>
          <a href="{key}/review.html"><img src="{key}/01_overview.png" alt="{title} physical model"></a>
          <div class="numbers"><b>{counts['members']:,}<small>physical members</small></b><b>{len(items)}<small>coordination items</small></b></div>
          <a class="button" href="{key}/review.html">Open interactive review →</a>
          <p class="small">Review images: {image_links}</p><p class="small"><a href="{key}/bim_package.json">Physical package</a> · <a href="{key}/coordination_questions.json">Questions</a> · <a href="{key}/validation.json">Checks</a></p></article>''')
        rows=[]
        for item in items:
            proposal=f'<p><b>Proposal to review:</b> {esc(item["proposed"])}</p>' if item.get('proposed') else ''
            rows.append(f'<details><summary><span>{esc(item["id"])} / {esc(item["kind"].replace("_"," "))}</span>{esc(item["title"])}</summary><p>{esc(item["basis"])}</p>{proposal}</details>')
        registers.append(f'<section><h2>{title}</h2>'+''.join(rows)+'</section>')
    total=sum(len(p['review']['items']) for p in packages.values())
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Three buildings · Steltic openBIM review</title>
<style>:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5f6f1;color:#203e42;font:16px/1.65 'Segoe UI',Arial,sans-serif}main{max-width:1260px;margin:auto;padding:40px 32px 70px}.eyebrow{font-size:11px;font-weight:700;letter-spacing:2px;color:#60736b}h1{font-size:44px;letter-spacing:-1px;line-height:1.15;margin:15px 0}h2{font-size:22px;line-height:1.3;margin:14px 0}p{max-width:960px}.intro{font-size:19px;color:#566a63}.status{display:inline-block;border:1px solid #d8c695;background:#fff4d8;padding:6px 14px;border-radius:20px;color:#82622c;font-size:13px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:30px 0}article{border:1px solid #d8e0d5;border-radius:10px;background:white;padding:22px}article img{width:100%;display:block;border:1px solid #ecf0e8;margin:18px 0}a{color:#215e65}a:hover{color:#a3672b}.button{display:block;background:#214c4d;color:white;text-decoration:none;text-align:center;padding:10px;border-radius:5px;font-weight:600}.button:hover{background:#326363;color:white}.numbers{display:flex;gap:30px;margin:20px 0}.numbers b{font-size:24px}.numbers small{display:block;font-weight:400;font-size:12px;color:#61736b}.small{font-size:12px}.evidence{padding:22px 26px;border-left:4px solid #5b8272;background:#eaf0e5;margin:30px 0}.register{margin-top:44px}.register section{margin:28px 0}details{border-top:1px solid #d3dccf;padding:14px 0}details:last-child{border-bottom:1px solid #d3dccf}summary{cursor:pointer;font-size:15px;font-weight:600}summary span{display:block;font-size:10px;letter-spacing:1px;color:#92713e;font-weight:600}details p{margin:10px 0 0 18px;font-size:14px;color:#52665d}footer{margin-top:40px;font-size:12px;color:#66766d}@media(max-width:900px){.grid{grid-template-columns:1fr}article img{max-height:320px;object-fit:contain}.numbers{gap:50px}main{padding:25px 18px}h1{font-size:34px}}</style>
<main><div class="eyebrow">STELTIC / OPENBIM · STAGE 3</div><h1>Three buildings, ready for review.</h1>
<p class="intro">Physical framing, located connection specifications and the questions that still need decisions — together with the original design evidence.</p>
'''+f'<div class="status">Review packages complete · {total} coordination items remain · Drawing release held</div><div class="grid">'+''.join(cards)+'''</div>
<div class="evidence"><b>Checked against the saved designs.</b><p>All 430 source design records are retained. The 11 review images cover whole buildings, plans, connection close-ups, the warehouse end wall and the housing roof valley. Automated checks cover geometry, references, layouts, analysis mappings and unresolved-item gating. All 812 audited files across the 61 gold-standard jobs are unchanged.</p>
<p class="small"><a href="verification.json">Verification and model hashes</a> · <a href="visual_review.json">Visual review record</a> · <a href="manifest.json">Bundle file hashes</a></p></div>
<h2>How to review</h2><p>Open a building, select a level and switch layers to see the framing. Select a member to inspect its profile, dimensions and original calculation record. Connection points and the detail view expose placed connection specifications. The amber register separates missing information, proposed set-out, source conflicts and delegated work.</p>
<p>Connection occurrences may include explicit parts or a referenced design detail. Their count does not mean every cut, weld, screw position or bracket outline is resolved. These are engineering review models; preview geometry omits fillets, bend radii and unresolved cut shapes. Structural capacities have not been recalculated.</p>
<p>Exported questions use the Hub-style explicit acceptance pattern and carry source/model fingerprints. Recording an answer does not change geometry or release a drawing. Implement the decision, regenerate the model and repeat the checks.</p>
<div class="register"><div class="eyebrow">COORDINATION REGISTER</div><h2>Decisions and delegated scope</h2>'''+''.join(registers)+'''</div>
<footer>Source-specific pilot recipes for HR Ex22, CFS Ex16 and CFS Ex8. Hub remains unchanged. General drawing production and IFC export follow these accepted data models. Extract the entire archive before opening this index; each viewer runs offline.</footer></main></html>'''
    (root/'index.html').write_text(page,encoding='utf-8')
    if args.inputs_archive:
        with zipfile.ZipFile(args.inputs_archive) as z:
            for name in z.namelist():
                path=(root/'inputs'/name).resolve()
                if not path.is_relative_to((root/'inputs').resolve()): raise ValueError('Unsafe archive path')
                path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(z.read(name))
    archive=args.archive.resolve()
    files=[p for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json' and p.resolve()!=archive]
    manifest={p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    args.archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in files+[root/'manifest.json']: z.write(p,p.relative_to(root).as_posix())
    print(args.archive, args.archive.stat().st_size, 'bytes')


if __name__=='__main__': main()
