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
    elif action=='export_import':
        from .ifc_export import export_import
        result=export_import(source,Path(output).with_name('model.ifc'),json.loads(Path(args[0]).read_text(encoding='utf-8')))
    else:raise ValueError('Unknown IFC worker action')
    Path(output).write_text(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')),encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception as ex:
        print(type(ex).__name__+': '+str(ex)[:1000],file=sys.stderr)
        sys.exit(1)
