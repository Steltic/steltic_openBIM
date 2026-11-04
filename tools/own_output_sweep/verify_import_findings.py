"""Check final import readiness parsing on every actual source/returned IFC."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import subprocess
from audit_sources import ROOT,OUT,read,save,sha
CODE=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'work/stage15/openbim_importfix/src'
sys.path.insert(0,str(CODE))
import ifcopenshell
import ifcopenshell.util.element
from steltic_openbim.ifc_import import declared_readiness

def function_hash(source,name):
    text=source.read_text(encoding='utf-8') if isinstance(source,Path) else source
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()

def main():
    repo=ROOT/'work/repos/steltic_openBIM';new=CODE/'steltic_openbim'
    baseline='f24c08a74006376ed995294c213147d74d9a6154'
    original=lambda file:subprocess.check_output(['git','show',baseline+':src/steltic_openbim/'+file],cwd=repo,text=True,encoding='utf-8')
    geometry_same=function_hash(original('ifc_import.py'),'build_review')==function_hash(new/'ifc_import.py','build_review')
    export_same=original('ifc_export.py')==(new/'ifc_export.py').read_text()
    assert geometry_same
    values=[]
    for path in OUT.glob('*/exchange_*/result.json'):
        result=read(path)
        if result['status']!='passed':continue
        dest=path.parent;target=dest/'readiness_import_verification.json'
        binding=dict(baseline_commit=baseline,importer_sha256=sha(new/'ifc_import.py'),source_ifc_sha256=sha(dest/'source.ifc'),returned_ifc_sha256=sha(dest/'returned.ifc'))
        if target.is_file() and read(target).get('binding')==binding:values.append(read(target));continue
        findings=[]
        for name in ('source','returned'):
            model=ifcopenshell.open(str(dest/(name+'.ifc')))
            props=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
            original=json.loads(props['SourceFindings']);parsed=declared_readiness(props)
            expected=[dict(code='declared_source_'+f['code'],message=f['message'],ids=f.get('entity_ids',[]),severity=f['severity']) for f in original]
            actual=[dict(code=f['code'],message=f['title'].removeprefix('Exported source information: '),ids=f['source_entity_ids'],severity=f['severity']) for f in parsed if f['code'].startswith('declared_source_')]
            assert expected==actual,(result['key'],name)
            warnings=json.loads(props.get('GeometryWarnings','[]'))
            assert [f['title'].removeprefix('Exported geometry warning: ') for f in parsed if f['code']=='declared_geometry_warning']==[w['message'] for w in warnings]
            findings.append(parsed);del model
        assert findings[0]==findings[1]
        value=dict(key=result['key'],variant=result['variant'],status='passed',binding=binding,
                   declared_findings_retained=len(findings[0]),geometry_builder_unchanged=geometry_same,exporter_unchanged=export_same)
        save(target,value);values.append(value)
        print(json.dumps(dict(key=result['key'],variant=result['variant'],findings=len(findings[0]))),flush=True)
    save(OUT/'import_readiness_verification.json',dict(status='passed',variants_checked=len(values),
        geometry_builder_unchanged=geometry_same,exporter_unchanged=export_same,results=values))

if __name__=='__main__':main()
