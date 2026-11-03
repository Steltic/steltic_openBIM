"""Read physical exports only from configured HR/CFS job directories."""
from pathlib import Path

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
