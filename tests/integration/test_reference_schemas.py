"""Editor schemas must recognize the same published formats as the runtime."""

from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from prompt_contracts.loading.manifest import parse_manifest_bytes
from prompt_contracts.types import CONTRACT_NAME_RE, CONTRACT_VERSION_RE


def test_reference_schemas_accept_all_bundled_manifests_and_locks(repo_root: Path) -> None:
    for schema_name, asset_name in (
        ("contract-manifest.schema.json", "contract.toml"),
        ("contract-lock.schema.json", "contracts.lock.json"),
    ):
        schema = json.loads((repo_root / "schemas" / schema_name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        roots = (repo_root / "examples", repo_root / "tests" / "fixtures" / "consumers")
        assets = [asset for root in roots for asset in root.rglob(asset_name)]
        assert assets
        for asset in assets:
            raw = asset.read_text(encoding="utf-8")
            validator.validate(tomllib.loads(raw) if asset.suffix == ".toml" else json.loads(raw))

        properties = schema["properties"]
        if asset_name.endswith(".json"):
            properties = properties["contracts"]["items"]["properties"]
        assert properties["name"]["pattern"] == CONTRACT_NAME_RE.pattern
        assert properties["version"]["pattern"] == CONTRACT_VERSION_RE.pattern


@pytest.mark.parametrize(
    "output",
    [
        {"mode": "json"},
        {"mode": "json", "schema": "output.schema.json", "min_length": 1},
        {"mode": "text"},
        {"mode": "text", "min_length": 1},
        {"mode": "text", "min_length": 1, "max_length": 10, "schema": "output.schema.json"},
    ],
)
def test_reference_manifest_rejects_incomplete_or_mixed_output_modes(
    repo_root: Path, output: dict[str, object]
) -> None:
    schema = json.loads(
        (repo_root / "schemas" / "contract-manifest.schema.json").read_text(encoding="utf-8")
    )
    manifest_path = repo_root / "examples/contracts/career.application-answer/1.0.0/contract.toml"
    raw = manifest_path.read_bytes()
    parse_manifest_bytes(raw)
    manifest = copy.deepcopy(tomllib.loads(raw.decode("utf-8")))
    manifest["output"] = output
    assert not Draft202012Validator(schema).is_valid(manifest)
