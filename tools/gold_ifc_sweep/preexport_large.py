"""Prepare large IFC sources while smaller Hub round trips run."""
import subprocess
import sys
from pathlib import Path
from gold_case import OUT,ROOT,read

for row in sorted(read(OUT/'product_inventory.json'),key=lambda r:r['members']):
    if row['members']<10000:continue
    case=row['case']
    print('Preparing '+case,flush=True)
    with (OUT/case/'preexport.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,str(Path(__file__).with_name('gold_case.py')),'export',case],cwd=ROOT,
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('Prepared '+case,flush=True)
