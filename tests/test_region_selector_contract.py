from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from ibl_anatomy.region_selector_contract import load_region_selector_contract
from ibl_anatomy.region_selector_contract.sync import sync


def test_bundled_contract_schema_hashes_and_action_snapshots() -> None:
    contract = load_region_selector_contract()
    jsonschema.validate(contract.traces, contract.schema)
    assert contract.manifest["contract"] == contract.traces["contract"]
    for name, digest in contract.manifest["files"].items():
        payload = (Path(__file__).parents[1] / "src/ibl_anatomy/region_selector_contract/v1" / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest
    for scenario in contract.traces["scenarios"]:
        assert len(scenario["actions"]) == len(scenario["expected"])


def test_selector_bundle_sync_and_explicit_check(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "src/ibl_anatomy/region_selector_contract/v1"
    destination = tmp_path / "consumer" / "contract-v1"
    sync(source, destination)
    sync(source, destination, check=True)
    assert (destination / "traces.json").read_bytes() == (source / "traces.json").read_bytes()

    (destination / "traces.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        sync(source, destination, check=True)


def test_selector_bundle_sync_rejects_extra_files(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "src/ibl_anatomy/region_selector_contract/v1"
    destination = tmp_path / "bundle"
    sync(source, destination)
    (destination / "unexpected.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file graph differs"):
        sync(source, destination, check=True)
