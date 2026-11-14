"""Integration tests for importlib.resources package loading outside repo checkout (T13, AC-15)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from prompt_contracts import Contract, PromptRegistry


@pytest.mark.parametrize("extra_bundle", [False, True])
def test_locked_package_catalog_from_real_zip_import(
    examples_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra_bundle: bool
) -> None:
    import zipfile

    from prompt_contracts import LockMismatchError

    package_name = "pc_zip_consumer_" + str(extra_bundle).lower()
    source = examples_dir / "packaged_consumer/src/example_consumer"
    archive = tmp_path / "consumer.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for asset in source.rglob("*"):
            if not asset.is_file() or "__pycache__" in asset.parts:
                continue
            relative = asset.relative_to(source).as_posix()
            output.writestr(f"{package_name}/{relative}", asset.read_bytes())
            if extra_bundle and relative.startswith("contracts/"):
                output.writestr(
                    f"{package_name}/{relative.replace('/1.0.0/', '/1.1.0/')}", asset.read_bytes()
                )
    monkeypatch.syspath_prepend(str(archive))
    if extra_bundle:
        with pytest.raises(LockMismatchError):
            PromptRegistry.from_package_resources(package_name)
    else:
        registry = PromptRegistry.from_package_resources(package_name)
        contract = registry.get("career.application-answer@1.0.0")
        assert len(contract.render({"question": "Q?", "verified_facts": "Fact"}).messages) == 2


def test_package_registry_rejects_unlocked_bundles(
    examples_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from prompt_contracts import LockMismatchError

    package_root = tmp_path / "consumer"
    shutil.copytree(examples_dir / "packaged_consumer/src/example_consumer", package_root)
    bundle = package_root / "contracts/career.application-answer/1.0.0"
    shutil.copytree(bundle, package_root / "contracts/career.application-answer/1.1.0")
    monkeypatch.setattr("importlib.resources.files", lambda package: package_root)
    with pytest.raises(LockMismatchError):
        PromptRegistry.from_package_resources("consumer")


def test_package_lock_is_read_with_a_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prompt_contracts import ResourceLimitError, RuntimePolicy

    (tmp_path / "contracts.lock.json").write_bytes(b" " * 1000)
    monkeypatch.setattr("importlib.resources.files", lambda package: tmp_path)
    with pytest.raises(ResourceLimitError):
        PromptRegistry.from_package_resources("consumer", policy=RuntimePolicy(max_schema_bytes=64))


def test_load_packaged_consumer_from_package_resources(
    examples_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_src = examples_dir / "packaged_consumer" / "src"
    monkeypatch.syspath_prepend(str(pkg_src))

    dir_reg = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    dir_contract = dir_reg.get("career.application-answer@1.0.0")

    pkg_reg = PromptRegistry.from_package_resources(
        "example_consumer",
        lock_resource="contracts.lock.json",
    )
    pkg_contract = pkg_reg.get("career.application-answer@1.0.0")
    assert pkg_contract.bundle_digest == dir_contract.bundle_digest

    single = Contract.from_package_resource(
        "example_consumer",
        "contracts/career.application-answer/1.0.0",
    )
    assert single.bundle_digest == dir_contract.bundle_digest

    inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )
    assert (
        pkg_contract.render(inputs).to_messages_list()
        == dir_contract.render(inputs).to_messages_list()
    )


def test_packaged_consumer_runs_from_outside_repository_checkout(
    examples_dir: Path, tmp_path: Path
) -> None:
    pkg_src = examples_dir / "packaged_consumer" / "src"
    inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                f"import sys, json; sys.path.insert(0, {str(pkg_src)!r}); "
                "from example_consumer import load_consumer_registry, generate_for_evaluation; "
                "reg = load_consumer_registry(); "
                "c = reg.get('career.application-answer@1.0.0'); "
                f"res = generate_for_evaluation(inputs={inputs!r}); "
                "ok = res.safe_metadata['output_valid']; "
                "print(json.dumps({'digest': c.bundle_digest, 'output_valid': ok}))"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip())
    assert result["output_valid"] is True
    assert result["digest"].startswith("sha256:")


def test_non_path_traversable_package_resource_reader(
    examples_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io
    import os
    from importlib.resources.abc import Traversable

    from prompt_contracts.errors import PathPolicyError, ResourceLimitError
    from prompt_contracts.loading.resources import PackageResourceBundleReader
    from prompt_contracts.types import RuntimePolicy

    class FakeTraversable(Traversable):
        def __init__(
            self,
            name: str,
            children: dict[str, FakeTraversable] | None = None,
            data: bytes | None = None,
        ) -> None:
            self._name = name
            self._children = children
            self._data = data

        @property
        def name(self) -> str:
            return self._name

        def is_dir(self) -> bool:
            return self._children is not None

        def is_file(self) -> bool:
            return self._data is not None

        def iterdir(self):  # type: ignore[no-untyped-def]
            assert self._children is not None
            return iter(self._children.values())

        def joinpath(self, *descendants: str | os.PathLike[str]) -> FakeTraversable:
            cur = self
            for part in descendants:
                for seg in os.fspath(part).split("/"):
                    if cur._children is not None and seg in cur._children:
                        cur = cur._children[seg]
                    else:
                        return FakeTraversable(seg, children=None, data=None)
            return cur

        def __truediv__(self, child: str | os.PathLike[str]) -> FakeTraversable:
            return self.joinpath(child)

        def open(self, mode: str = "r", *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            assert self._data is not None
            if "b" in mode:
                return io.BytesIO(self._data)
            return io.StringIO(self._data.decode("utf-8"))

        def read_bytes(self) -> bytes:
            assert self._data is not None
            return self._data

        def read_text(self, encoding: str | None = "utf-8") -> str:
            assert self._data is not None
            return self._data.decode(encoding or "utf-8")

    bundle_dir = examples_dir / "contracts" / "career.application-answer" / "1.0.0"
    files_map = {
        p.name: FakeTraversable(p.name, data=p.read_bytes())
        for p in sorted(bundle_dir.iterdir())
        if p.is_file()
    }
    sub_dir = FakeTraversable(
        "nested",
        children={"note.txt": FakeTraversable("note.txt", data=b"note")},
    )
    files_map["nested"] = sub_dir
    root_trav = FakeTraversable(
        "pkg", children={"bundle": FakeTraversable("bundle", children=files_map)}
    )

    monkeypatch.setattr("importlib.resources.files", lambda pkg: root_trav)
    reader = PackageResourceBundleReader("synthetic_pkg", "bundle")
    listed = reader.list_files()
    assert "contract.toml" in listed
    assert "nested/note.txt" in listed

    raw_toml = reader.read_bytes("contract.toml", max_bytes=4096)
    assert b"format_version = 1" in raw_toml

    with pytest.raises(PathPolicyError):
        reader.read_bytes("missing.txt", max_bytes=100)

    with pytest.raises(ResourceLimitError):
        reader.read_bytes("contract.toml", max_bytes=4)

    with pytest.raises(ResourceLimitError):
        reader.list_files(policy=RuntimePolicy(max_bundle_files=2))

    with pytest.raises(PathPolicyError):
        PackageResourceBundleReader("")
