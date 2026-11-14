"""Identify the exact openBIM source used by a delivered artifact."""
import hashlib
from pathlib import Path


VERSION = '0.8.108'


def generator_identity():
    root = Path(__file__).resolve().parent
    files = {}
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        files[relative] = value
        digest.update(relative.encode() + b'\0' + value.encode() + b'\n')
    return {'name': 'steltic-openbim', 'version': VERSION, 'source_sha256': digest.hexdigest(),
            'files': files}
