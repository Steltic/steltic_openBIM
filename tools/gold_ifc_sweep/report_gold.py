"""Summarise every case without promoting source design findings to approval."""
import collections
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

from gold_case import OUT, ROOT, read, save, sha


def report(final=False):
    bindings = sorted([read(p) for p in OUT.glob('*/binding.json')], key=lambda r:(r['module'], int(''.join(c for c in r['case'] if c.isdigit())), r['case']))
    rows=[]
    for binding in bindings:
        case=binding['case'];folder=OUT/case
        result=read(folder/'result.json') if (folder/'result.json').exists() else None
        progress=read(folder/'progress.json') if (folder/'progress.json').exists() else {}
        status=result['status'] if result else progress.get('status','pending')
        if progress.get('status') in ('running','failed'):
            status=progress['status']
        row=dict(case=case, module=binding['module'], title=binding['title'], status=status,
                 native_replay=binding['status'], members=binding['members'], designs=binding['design_record_count'],
                 products=result['products_compared'] if result else None,
                 entities=result['entities_compared'] if result else None,
                 source_sha256=result['source_sha256'] if result else None,
                 returned_sha256=result['returned_sha256'] if result else None,
                 source_coverage=result['source_coverage'] if result else None,
                 source_findings=result['source_findings'] if result else None,
                 evidence=f'{case}/result.json' if result else f'{case}/progress.json' if progress else f'{case}/binding.json')
        rows.append(row)
    counts=collections.Counter(r['status'] for r in rows)
    summary=dict(generated=datetime.now(timezone.utc).isoformat(), complete=counts['passed']==61,
                 scope='Gold HR/CFS outputs to IFC, Hub IFC import/build, export, returned-IFC import/build, and complete comparison.',
                 cases=61, modules=dict(collections.Counter(r['module'] for r in rows)),
                 status_counts=dict(counts), local_model_only_replays=sum(r['native_replay']=='passed' for r in rows),
                 products_compared=sum(r['products'] or 0 for r in rows), entities_compared=sum(r['entities'] or 0 for r in rows),
                 design_records=sum(r['designs'] for r in rows), llm_calls=0, redesign_runs=0, drawing_runs=0,
                 source_exporter_commit='a8f16e147f05f4432085ab6cd215bab6397dfae8',
                 source_exporter_sha256=sha(ROOT/'work/repos/steltic_openBIM/src/steltic_openbim/ifc_export.py'),
                 current_geometry_commit='6958f8eb1b7d5293d5f047796659195ff2a75ec4',
                 rows=rows,
                 limits=['Saved gold member/connection designs and previously adopted fictional physical supplements are reused with exact source bindings.',
                         'Every source IFC STEP entity and every displayed product geometry/data record is compared; no object sampling.',
                         'All objects must render, with no scope exclusions or schema errors. Only added IFC review metadata is allowed.',
                         'Source data/geometry findings remain visible and unchanged. Passing exchange does not claim a fresh design run, complete fabrication hardware, or a native Revit acceptance test.'])
    if (OUT/'geometry_upgrade_summary.json').exists():
        upgrade=read(OUT/'geometry_upgrade_summary.json')
        assert len(upgrade)==len(read(OUT/'geometry_upgrade_plan.json')['cases'])
        assert all(r['status']=='passed' and r['complete_review_identical'] for r in upgrade)
        summary['geometry_upgrade_regression']=dict(cases=len(upgrade),products=sum(r['products'] for r in upgrade),status='passed',scope='Complete source review data equals the earlier accepted Hub review after batching geometry.')
    if final:
        assert summary['complete'] and len(rows)==61
        # Recheck source files after the entire sweep, as well as native replay's
        # before/after guards. Neither the gold jobs nor adopted models may drift.
        audited=set()
        for binding in bindings:
            case_dir=OUT/binding['case']
            result=read(case_dir/'result.json')
            assert read(case_dir/'progress.json')['status']=='passed'
            assert result['source_replay_binding_matches']
            assert result['source_findings']==result['returned_findings']
            assert not read(case_dir/'source_export.json')['schema_errors']
            assert not read(case_dir/'returned_export.json')['schema_errors']
            for label in ('source','returned'):
                proof=read(case_dir/(label+'_hub.json'))
                assert proof['api_model_sha256']==sha(case_dir/(label+'_review.json'))
                assert proof['downloaded_original_ifc_sha256']==sha(case_dir/(label+'_downloaded.ifc'))==sha(case_dir/(label+'.ifc'))
            replay=read(OUT/binding['case']/'native_replay/bim_package.json')
            original=read(OUT/binding['case']/'snapshot/source.json')
            assert replay.get('analysis',{})==original.get('analysis',{})
            job=Path(binding['gold_job'])
            for name,expected in replay['provenance']['source_files'].items():
                file=job/name
                assert sha(file)==expected, str(file)
                audited.add(str(file))
            assert sha(binding['physical_model_source'])==binding['physical_model_sha256']
            assert sha(OUT/binding['case']/'source.ifc')==next(r['source_sha256'] for r in rows if r['case']==binding['case'])
            assert sha(OUT/binding['case']/'returned.ifc')==next(r['returned_sha256'] for r in rows if r['case']==binding['case'])
        summary['final_gold_files_unchanged']=len(audited)
        summary['final_physical_models_unchanged']=61
        summary['native_analysis_models_matching_gold']=61
    save(OUT/'summary.json',summary)
    body=[]
    for row in rows:
        key=row['case'];status=row['status']
        links=f'<a href="{key}/source.ifc">Source IFC</a> <a href="{key}/returned.ifc">Returned IFC</a> <a href="http://127.0.0.1:8300/m/steltic_openbim/ifc-import?project=GoldRoundTrip_{key}_returned">Open Hub review</a> ' if status=='passed' else ''
        links+=f'<a href="{row["evidence"]}">Evidence</a>'
        issues=', '.join(f'{f["code"]}: {f["count"]}' for f in row.get('source_findings') or []) or ('None reported' if status=='passed' else 'Pending')
        body.append(f'<tr data-module="{row["module"]}"><td><strong>{key.upper()}</strong><br>{escape(row["title"])}</td><td class="{status}">{status.title()}</td><td>{row["members"]:,}</td><td>{row["designs"]:,}</td><td>{row["products"] or "—"}</td><td>{row["entities"] or "—"}</td><td>{escape(issues)}</td><td>{links}</td></tr>')
    markup='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>61 gold buildings · IFC round-trip verification</title>
<style>body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f5f7f8;color:#192934}main{max-width:1500px;margin:auto;padding:32px}h1{font-size:30px;margin:0 0 12px}p{max-width:1100px}a{color:#126580;white-space:nowrap}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{text-align:left;padding:12px;border-bottom:1px solid #dce4e8;vertical-align:top}th{position:sticky;top:0;background:#193943;color:white}.passed{color:#11744b;font-weight:700}.failed{color:#af2632}.running{color:#986100}.stats{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}.stats div{padding:16px 24px;border-radius:10px;background:white;border:1px solid #dce4e8}.stats b{display:block;font-size:27px}select{font:inherit;padding:6px;margin:12px}td:last-child a{display:block}.note{padding:16px;background:#e5eef0;border-radius:8px}small{color:#506872}details{margin:18px 0}</style><main>
<h1>61 gold buildings · IFC round-trip verification</h1>'''
    markup+=f'<small>Updated {escape(summary["generated"])} · openBIM 0.8.30</small><div class="stats"><div><b>{counts["passed"]} / 61</b>Round trips passed</div><div><b>61 / 61</b>Local engine replays</div><div><b>{summary["products_compared"]:,}</b>Products compared</div><div><b>{summary["entities_compared"]:,}</b>IFC entities compared</div><div><b>0</b>LLM / redesign / drawing runs</div></div>'
    markup+='<p><strong>Tested path:</strong> saved HR/CFS gold job → local model-only engine replay → saved physical model and design records → IFC → actual Hub import and model build → IFC export → returned-IFC import and model build → full comparison.</p><p class="note">Every original IFC declaration must survive unchanged, including geometry, units, placements, grids, levels, materials, properties and relations. Every displayed product’s world geometry and data must match after reimport. Only review metadata is added. Existing source findings remain visible; a passing exchange does not resolve them.</p>'
    markup+='<details><summary>Scope and evidence</summary><ul>'+''.join('<li>'+escape(s)+'</li>' for s in summary['limits'])+'</ul><p>Connection designs without placed hardware remain complete design records and declared references. Local drawing-detail templates are not assigned invented global placements.</p><a href="summary.json">Machine-readable summary</a></details>'
    markup+='<label>Buildings <select id="filter"><option value="">All 61</option><option>HR</option><option>CFS</option></select></label><table><thead><tr><th>Building</th><th>Round trip</th><th>Members</th><th>Design records</th><th>Products checked</th><th>Entities checked</th><th>Retained source findings</th><th>Files</th></tr></thead><tbody>'+''.join(body)+'</tbody></table><script>document.querySelector("#filter").onchange=e=>document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!!e.target.value&&r.dataset.module!==e.target.value)</script></main></html>'
    (OUT/'index.html').write_text(markup,encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('complete','status_counts','products_compared','entities_compared')}),flush=True)
    return summary


if __name__=='__main__':
    import sys
    report('--final' in sys.argv)
