"""Index verification must reject tampering before installing a candidate."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from scripts.verify_testpypi import verify_index_artifacts


@pytest.mark.parametrize("tamper", [False, True])
def test_testpypi_artifact_bytes_match_verified_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: bool
) -> None:
    names = ["prompt_contracts-0.2.0-py3-none-any.whl", "prompt_contracts-0.2.0.tar.gz"]
    entries = []
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
        entries.append(
            {
                "filename": name,
                "url": f"https://test-files.pythonhosted.org/{name}",
                "digests": {"sha256": hashlib.sha256(name.encode()).hexdigest()},
            }
        )

    def fetch(url: str, *, timeout: int) -> io.BytesIO:
        if url.endswith("/json"):
            return io.BytesIO(json.dumps({"urls": entries}).encode())
        content = b"tampered" if tamper else url.rsplit("/", 1)[1].encode()
        return io.BytesIO(content)

    monkeypatch.setattr("scripts.verify_testpypi.urlopen", fetch)
    if tamper:
        with pytest.raises(ValueError, match="Downloaded TestPyPI bytes"):
            verify_index_artifacts("0.2.0", tmp_path)
    else:
        assert len(verify_index_artifacts("0.2.0", tmp_path)) == 2
