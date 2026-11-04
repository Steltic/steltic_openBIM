"""Read physical exports only from configured HR/CFS job directories."""
from pathlib import Path
import json

from .drawing_workflow import name


class JobSources:
    def __init__(self, roots=None):
        self.roots = {k: Path(v).resolve() for k, v in (roots or {}).items() if v}

    def path(self, module, job):
        if module not in self.roots:
            raise ValueError('Source module is not configured')
        root = self.roots[module]
        folder = (root / name(job)).resolve()
        if not folder.is_relative_to(root):
            raise ValueError('Invalid source job path')
        for relative in ('design/bim_package.json', 'bim_package.json'):
            path = (folder / relative).resolve()
            if path.is_relative_to(folder) and path.is_file():
                return path
        raise ValueError('No physical export exists for this job yet')

    def load_current(self, module, job):
        """Bind a new job snapshot to the exact source files its exporter recorded."""
        from .validation import inspect_package, PackageValidationError
        path = self.path(module, job)
        package = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(package, dict) or package.get('module') != module:
            raise ValueError('The physical export does not match the selected module')
        folder = (self.roots[module] / name(job)).resolve()
        verdict = inspect_package(package, folder)
        evidence_errors = [f for f in verdict['findings'] if f['code'] in ('source_path', 'source_missing', 'source_stale')]
        if evidence_errors:
            raise PackageValidationError(evidence_errors)
        # Geometry errors remain the caller's validation responsibility, keeping
        # its existing diagnostic. Missing physical information stays provisional.
        provenance=package.get('provenance')
        files=provenance.get('source_files') if isinstance(provenance,dict) else None
        tracked_files=len(files) if isinstance(files,dict) else 0
        return package, dict(source_freshness_checked=verdict['source_freshness_checked'] and bool(tracked_files),
                             tracked_files=tracked_files)

    def list(self):
        result = []
        for module, root in self.roots.items():
            if not root.is_dir():
                continue
            for folder in sorted(root.iterdir()):
                if not folder.is_dir():
                    continue
                try:
                    self.path(module, folder.name)
                except ValueError:
                    continue
                result.append(dict(module=module, job=folder.name))
        return result
