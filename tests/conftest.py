"""Shared pytest fixtures and network-egress guards."""

from __future__ import annotations

import socket
import urllib.request
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def block_network_egress(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Block all external network socket connections unless a test is marked ``live``."""
    if request.node.get_closest_marker("live") is not None:
        return

    def _blocked_connect(self: Any, address: Any) -> Any:
        raise RuntimeError(
            f"External network egress blocked in offline test suite (attempted {address!r})"
        )

    def _blocked_create_connection(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"External network egress blocked in offline test suite (args={args!r})")

    def _blocked_urlopen(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("External urllib.request.urlopen blocked in offline test suite")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_connect)
    monkeypatch.setattr(socket, "create_connection", _blocked_create_connection)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)


@pytest.fixture
def repo_root() -> Path:
    """Return the absolute path to the repository root."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def examples_dir(repo_root: Path) -> Path:
    """Return the absolute path to ``examples/``."""
    return repo_root / "examples"
