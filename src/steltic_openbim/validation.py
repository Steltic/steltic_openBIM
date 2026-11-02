"""Recompute data readiness and optionally verify the original source files."""
import hashlib
import json
from pathlib import Path

from .bim_contract import issue, validate


class PackageValidationError(ValueError):
    def __init__(self, findings):
        self.findings = findings
        super().__init__("; ".join(f["code"] + ": " + f["message"] for f in findings))


def inspect_package(package, source_root=None):
    findings = validate(package)
    if source_root is not None and not any(f["severity"] == "error" for f in findings):
        root = Path(source_root).resolve()
        for relative, expected in package["provenance"]["source_files"].items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                findings.append(issue("source_path", "Source path escapes the job directory", [relative], "error"))
            elif not path.is_file():
                findings.append(issue("source_missing", "Source evidence is missing", [relative], "error"))
            elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                findings.append(issue("source_stale", "Source evidence changed after export", [relative], "error"))
    return {"status": "invalid" if any(f["severity"] == "error" for f in findings) else ("needs_input" if findings else "ready"),
            "source_freshness_checked": source_root is not None, "findings": findings}


def load_package(path, *, require_ready=True, source_root=None):
    package = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    verdict = inspect_package(package, source_root)
    if verdict["status"] == "invalid" or (require_ready and verdict["status"] != "ready"):
        raise PackageValidationError(verdict["findings"])
    return package
