import argparse
import json
from pathlib import Path

from .validation import inspect_package


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate an HR/CFS physical-data package without loading either engine")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("package", type=Path)
    check.add_argument("--source-root", type=Path, help="Also verify exported fingerprints against the source job")
    args = parser.parse_args(argv)
    try:
        package = json.loads(args.package.read_text(encoding="utf-8-sig"))
        verdict = inspect_package(package, args.source_root)
    except (OSError, ValueError) as ex:
        parser.exit(1, str(ex) + "\n")
    print(json.dumps(verdict, indent=2))
    return {"ready": 0, "needs_input": 2, "invalid": 1}[verdict["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
