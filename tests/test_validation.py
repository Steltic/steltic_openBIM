import copy
import hashlib
import json
from pathlib import Path

import pytest

from steltic_openbim import PackageValidationError, inspect_package, load_package
from steltic_openbim.__main__ import main

FIXTURE = Path(__file__).parent / "fixtures/synthetic_bim_package.json"


@pytest.fixture
def package():
    return json.loads(FIXTURE.read_text())


def test_complete_fixture_loads_without_engine():
    assert load_package(FIXTURE)["building_id"] == "synthetic_contract_fixture"


def test_readiness_is_recomputed(package):
    package["physical"]["coverage"].pop("openings")
    package["readiness"] = {"status": "ready"}
    assert inspect_package(package)["status"] == "needs_input"


def test_unresolved_is_available_only_for_inspection(package, tmp_path):
    package["physical"]["coverage"] = {}
    path = tmp_path / "bim_package.json"
    path.write_text(json.dumps(package))
    with pytest.raises(PackageValidationError): load_package(path)
    assert load_package(path, require_ready=False)


def test_invalid_references_cannot_be_loaded(package, tmp_path):
    package["physical"]["members"][0]["material_id"] = "absent"
    path = tmp_path / "bim_package.json"
    path.write_text(json.dumps(package))
    with pytest.raises(PackageValidationError): load_package(path, require_ready=False)


def test_source_freshness_and_path_confinement(package, tmp_path):
    path = tmp_path / "cfg.py"
    path.write_text("cfg={}")
    package["provenance"]["source_files"] = {"cfg.py": hashlib.sha256(path.read_bytes()).hexdigest()}
    assert inspect_package(package, tmp_path)["status"] == "ready"
    path.write_text("cfg={'changed': True}")
    assert inspect_package(package, tmp_path)["findings"][0]["code"] == "source_stale"
    package["provenance"]["source_files"] = {"../outside.py": "0"*64}
    assert inspect_package(package, tmp_path)["findings"][0]["code"] == "source_path"


def test_cli_exit_status(package, tmp_path):
    assert main(["validate", str(FIXTURE)]) == 0
    package["physical"]["coverage"] = {}
    path = tmp_path / "bim_package.json"
    path.write_text(json.dumps(package))
    assert main(["validate", str(path)]) == 2


def test_contract_schema_distribution_matches():
    root=Path(__file__).resolve().parents[1]
    assert (root/"contracts/bim_package.schema.json").read_bytes()==(root/"src/steltic_openbim/bim_package.schema.json").read_bytes()
