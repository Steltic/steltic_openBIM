"""A 61-row audit, explicitly separating availability, completeness and transport."""
import collections
import html
import json
from pathlib import Path
from audit_sources import ROOT,OUT,read,save

def optional(path):return read(path) if path.is_file() else {}
def codes(verdict):return sorted({f['code'] for f in verdict.get('findings',[])})
def result_for(row):
    key=row['key'];folder=OUT/key;audit=read(folder/'source_audit.json');replay=read(folder/'replay_result.json')
    variants={}
    for variant in ('saved','replay'):
        dest=folder/('exchange_'+variant);exchange=optional(dest/'result.json');comparison=optional(dest/'architectural_comparison.json');import_check=optional(dest/'readiness_import_verification.json')
        variants[variant]=dict(transport=exchange.get('status','pending'),source_validation=exchange.get('validation',{}).get('status'),
            source_finding_codes=codes(exchange.get('validation',{})),architectural_comparison=comparison.get('status','not_tested'),
            comparison_issue_codes=[i['code'] for i in comparison.get('issues',[])],
            products_compared=exchange.get('products_compared',0),entities_compared=exchange.get('entities_compared',0),
            package_sha256=exchange.get('package_sha256'),source_ifc_sha256=exchange.get('source_sha256'),returned_ifc_sha256=exchange.get('returned_sha256'),
            source_files_unchanged=exchange.get('original_job_unchanged'),schema_errors=exchange.get('schema_errors'),
            import_readiness_verified=import_check.get('status')=='passed' and import_check.get('binding',{}).get('returned_ifc_sha256')==exchange.get('returned_sha256'),
            error=exchange.get('error'),stage=exchange.get('stage'))
    saved=variants['saved'];replayed=variants['replay']
    automatic=(audit['source_run_status']=='done' and audit['current_completion_gate_passed'] and
               saved['transport']=='passed' and saved['source_validation']=='ready' and saved['architectural_comparison']=='passed')
    replay_ready=(replayed['transport']=='passed' and replayed['source_validation']=='ready' and replayed['architectural_comparison']=='passed')
    if automatic:status='saved_job_passed'
    elif replay_ready:status='reexport_checks_passed_producer_not_complete'
    elif replayed['transport']=='passed':status='transport_passed_source_needs_resolution'
    elif replayed['transport']=='blocked_source':status='invalid_source'
    elif replayed['transport']=='unavailable':status='no_own_package'
    elif replayed['transport']=='failed':status='exchange_failed'
    else:status='pending'
    changed=[name for f in audit.get('source_freshness',{}).get('findings',[]) if f['code'] in ('source_stale','source_missing') for name in f['entity_ids']]
    return dict(case=row['case'],key=key,title=row['title'],module=row['module'],primary=row['primary'],source_run_status=audit['source_run_status'],
        original_package_present=audit['package_present'],original_native_completion_passed=audit['current_completion_gate_passed'],
        producer_completion_problems=audit['completion_problems'],saved_readiness=audit.get('stored_readiness'),
        original_validation=audit.get('current_validation',{}).get('status'),original_freshness=audit.get('source_freshness',{}).get('status'),
        changed_recorded_files=changed,native_reexport=replay['status'],native_reexport_readiness=replay.get('stored_readiness'),
        native_reexport_finding_codes=sorted({f['code'] for f in replay.get('findings',[])}),
        exporter_revision=replay.get('producer'),original_producer_revision=audit.get('provenance',{}).get('producer_revision'),
        variants=variants,status=status,saved_job_acceptance=automatic,reexport_model_checks_passed=replay_ready)

def main():
    rows=[result_for(r) for r in read(OUT/'candidates.json')];primary=[r for r in rows if r['primary']];earlier=[r for r in rows if not r['primary']]
    counts=dict(cases=len(primary),modules=dict(collections.Counter(r['module'] for r in primary)),
        original_packages=sum(r['original_package_present'] for r in primary),original_packages_absent=sum(not r['original_package_present'] for r in primary),
        recorded_run_status=dict(collections.Counter(r['source_run_status'] for r in primary)),
        native_completion_passes=sum(r['original_native_completion_passed'] for r in primary),
        native_reexport=dict(collections.Counter(r['native_reexport'] for r in primary)),
        saved_transport=dict(collections.Counter(r['variants']['saved']['transport'] for r in primary)),
        replay_transport=dict(collections.Counter(r['variants']['replay']['transport'] for r in primary)),
        saved_job_acceptance=sum(r['saved_job_acceptance'] for r in primary),reexport_model_checks_passed=sum(r['reexport_model_checks_passed'] for r in primary),
        status=dict(collections.Counter(r['status'] for r in primary)),
        replay_products_compared=sum(r['variants']['replay']['products_compared'] for r in primary),
        replay_entities_compared=sum(r['variants']['replay']['entities_compared'] for r in primary),
        earlier_control_runs=len(earlier),earlier_control_transport=dict(collections.Counter(r['variants']['replay']['transport'] for r in earlier)))
    report=dict(scope='Completed/partial updated-producer jobs: own saved outputs and read-only native re-export only. No supplements or legacy gold substitution.',
        complete_audit=all(r['variants'][v]['transport']!='pending' and (r['variants'][v]['transport']!='passed' or
            (r['variants'][v]['architectural_comparison'] in ('passed','needs_resolution','unverifiable_input') and r['variants'][v]['import_readiness_verified'])) for r in rows for v in ('saved','replay')),
        counts=counts,cases=primary,earlier_controls=earlier,
        openbim_fix=dict(version='0.8.32',commit='b3a50f068a5b0401f47f1bd3ce958d009ef8e6db',prs=['https://github.com/Steltic/steltic_openBIM/pull/41','https://github.com/Steltic/steltic_openBIM/pull/42']),
        upstream_mutation_policy='HR/CFS/Hub: review-only fix list; no changes, PRs or merges.',
        llm_calls=0,redesign=False,analysis_solve=False,drawings=False,supplements=False,
        limitations=['All 61 identities are audited; missing or invalid job outputs cannot become successful IFC round trips.',
            'A local own-input re-export is recovery evidence, not proof that the saved production job automatically exported complete data.',
            'The previous gold sweep used physical supplements and is not counted here.',
            'Original producer revisions were not recorded. Existing source/engine hashes are preserved; replay exporter revisions are recorded separately.',
            'Geometry/data checks and IFC transport do not recheck structural capacity, fabrication fit, engineering approval or native Revit operation.',
            'Input comparisons flag unexplained differences for review. Architectural finished surfaces, physical reference planes/thickness and legitimately added structural panels need explicit correspondence; a difference is not automatically a structural defect.',
            'The production openBIM API was tested in isolated local projects; the Hub embedded dependency remains unchanged pending review.'])
    save(OUT/'report.json',report)
    lines=['# Own-output audit of all 61 buildings','',report['scope'],'',
        f"Audit status: {'complete' if report['complete_audit'] else 'in progress'}. {counts['original_packages']} primary saved packages; {counts['original_packages_absent']} absent. Recorded runs: {counts['recorded_run_status']}.",'',
        f"Saved-job acceptance: **{counts['saved_job_acceptance']}/61**. Original native completion gates: {counts['native_completion_passes']}/61. These counts require actual saved source evidence; an old done flag is insufficient.",'',
        f"Native own-input re-export: {counts['native_reexport']}. Re-exported IFC exchange: {counts['replay_transport']}. {counts['reexport_model_checks_passed']} primary re-exports pass both source-completeness and independent architectural checks; this does not make their original producer runs complete.",'',
        f"Every product's full geometry/data and every original STEP entity are compared. Primary re-export comparisons cover {counts['replay_products_compared']:,} products and {counts['replay_entities_compared']:,} entities. Earlier controls ({len(earlier)} runs) are recorded separately and do not increase the 61-case count.",'',
        'openBIM 0.8.32 is merged in [PR #41](https://github.com/Steltic/steltic_openBIM/pull/41) and [PR #42](https://github.com/Steltic/steltic_openBIM/pull/42). HR, CFS and Hub are unchanged; see [the review-only fix list](upstream-fix-list.md). No LLM calls, redesign, analysis solves, drawing generation or physical supplements were used.','',
        '| Case | Building | Saved run | Saved package / native gate | Own-input re-export | IFC exchange | Independent input check | Outcome |',
        '|---|---|---|---|---|---|---|---|']
    for r in primary:
        v=r['variants']['replay'];lines.append(f"| {r['case']} | {r['title']} | {r['source_run_status']} | {'present' if r['original_package_present'] else 'absent'} / {'pass' if r['original_native_completion_passed'] else 'fail'} | {r['native_reexport_readiness'] or r['native_reexport']} | {v['transport']} | {v['architectural_comparison']} | {r['status']} |")
    lines+=['','## Limits','']+['- '+x for x in report['limitations']]
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    esc=html.escape
    body=f'''<!doctype html><html><head><meta charset="utf-8"><title>Own-output IFC audit · 61 buildings</title><style>body{{font:15px system-ui;margin:30px;color:#132e38;background:#f4f7f6}}h1{{font-size:26px}}table{{border-collapse:collapse;background:white;width:100%}}th,td{{padding:9px;border-bottom:1px solid #dbe4e2;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#163b43;color:white}}a{{color:#0a6970}}.pass{{color:#176540}}.gap{{color:#973e26}}details{{margin:10px 0}}.cards{{display:flex;gap:16px;margin:20px 0}}.cards div{{background:white;padding:18px;flex:1}}strong{{font-size:24px}}</style></head><body><h1>Own-output IFC audit · 61 buildings</h1><p>{esc(report['scope'])}</p><div class="cards"><div><strong>{counts['saved_job_acceptance']}/61</strong><br>Saved-job acceptance</div><div><strong>{counts['replay_transport'].get('passed',0)}/61</strong><br>Own-input re-export round trips</div><div><strong>{counts['reexport_model_checks_passed']}</strong><br>Re-exports pass physical + input checks</div><div><strong>{counts['native_reexport'].get('unavailable',0)}</strong><br>No model/calculation pair to replay</div></div><p><a href="upstream-fix-list.md">HR/CFS/Hub review-only fix list</a> · <a href="report.json">Full machine-readable results</a> · <a href="https://github.com/Steltic/steltic_openBIM/pull/41">Merged openBIM fix</a></p><p>Transport success preserves supplied data. It does not fill missing framing/connections or clear source geometry findings. Original jobs and upstream repositories are unchanged.</p><table><tr><th>Case</th><th>Building / saved run</th><th>Native completion</th><th>Own-input re-export</th><th>IFC exchange</th><th>Independent checks</th><th>Evidence</th></tr>'''
    for r in rows:
        v=r['variants']['replay'];key=r['key'];links=[f'<a href="{key}/source_audit.json">Source audit</a>',f'<a href="{key}/exchange_saved/result.json">As saved</a>',f'<a href="{key}/exchange_replay/result.json">Re-export</a>']
        if v['transport']=='passed':links +=[f'<a href="{key}/exchange_replay/architectural_comparison.json">Input comparison</a>',f'<a href="{key}/exchange_replay/returned.ifc">Returned IFC</a>']
        body+=f'<tr><td>{esc(key)}'+(' <small>(earlier control)</small>' if not r['primary'] else '')+f'</td><td>{esc(r["title"])}<br>{r["source_run_status"]}</td><td>{"passed" if r["original_native_completion_passed"] else "failed / unavailable"}</td><td>{r["native_reexport_readiness"] or r["native_reexport"]}</td><td>{v["transport"]}<br>{v["products_compared"]:,} products</td><td>{v["architectural_comparison"]}<details><summary>Findings</summary>{esc(", ".join(v["source_finding_codes"]+v["comparison_issue_codes"]) or "None recorded / not checked")}</details></td><td>'+ '<br>'.join(links)+'</td></tr>'
    body+='</table><h2>Limits</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in report['limitations'])+'</ul></body></html>'
    (OUT/'index.html').write_text(body,encoding='utf-8')
    print(json.dumps(counts),flush=True)

if __name__=='__main__':main()
