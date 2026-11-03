"""Isolate native IFC parsing/meshing from the Hub's module server."""
import json
from pathlib import Path
import sys


def main():
    action,source,output,*args=sys.argv[1:]
    if action=='inspect':
        from .ifc_import import open_model,metadata
        result=metadata(open_model(source))
    elif action=='build':
        from .ifc_import import build_review
        result=build_review(source,json.loads(Path(args[0]).read_text(encoding='utf-8')))
    elif action=='export':
        from .ifc_export import export_drawing
        result=export_drawing(source,Path(output).with_name('model.ifc'))
    elif action=='export_structural':
        from .ifc_export import export_structural
        result=export_structural(source,Path(output).with_name('model.ifc'))
    elif action=='export_import':
        from .ifc_export import export_import
        result=export_import(source,Path(output).with_name('model.ifc'),json.loads(Path(args[0]).read_text(encoding='utf-8')))
    elif action=='handoff':
        from .ifc_handoff import prepare
        folder=Path(source);dest=Path(output).parent
        read=lambda p:json.loads(p.read_text(encoding='utf-8'))
        request=read(Path(args[0]));target=request.get('target_module','HR')
        geometry,brief=prepare(folder/'original.ifc',read(folder/'model.json'),read(folder/'state.json'),request['brief'],target)
        brief_filename=target.lower()+'_brief.txt'
        (dest/brief_filename).write_text(brief,encoding='utf-8')
        (dest/'architectural_geometry.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
        result=dict(source_sha256=geometry['source_sha256'],import_revision=geometry['import_revision'],target_module=target,brief_filename=brief_filename,warnings=geometry['warnings'])
    else:raise ValueError('Unknown IFC worker action')
    Path(output).write_text(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')),encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception as ex:
        print(type(ex).__name__+': '+str(ex)[:1000],file=sys.stderr)
        sys.exit(1)
