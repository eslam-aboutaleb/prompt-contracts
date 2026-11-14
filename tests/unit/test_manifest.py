"""Unit tests for contract.toml manifest parser and format v1 validation (T06)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import (
    ErrorCode,
    ManifestError,
    UnsupportedFormatError,
)
from prompt_contracts.loading.manifest import parse_manifest_bytes
from prompt_contracts.types import MessageRole, OutputMode


def _valid_manifest_toml() -> str:
    return (
        "format_version = 1\n"
        'name = "career.application-answer"\n'
        'version = "1.0.0"\n'
        'description = "Answer a question."\n'
        'renderer = "placeholders-v1"\n'
        'input_schema = "input.schema.json"\n\n'
        "[output]\n"
        'mode = "json"\n'
        'schema = "output.schema.json"\n\n'
        "[[messages]]\n"
        'role = "system"\n'
        'file = "system.md"\n\n'
        "[[messages]]\n"
        'role = "user"\n'
        'file = "user.md"\n'
    )


def test_parse_manifest_bytes_accepts_valid_manifest() -> None:
    parsed = parse_manifest_bytes(_valid_manifest_toml().encode("utf-8"))
    assert str(parsed.ref) == "career.application-answer@1.0.0"
    assert parsed.output_mode is OutputMode.JSON
    assert parsed.output_schema == "output.schema.json"
    assert len(parsed.messages) == 2
    assert parsed.messages[0][0] is MessageRole.SYSTEM


def test_parse_manifest_bytes_rejects_unknown_top_level_fields() -> None:
    raw = _valid_manifest_toml() + '\nextra_key = "forbidden"\n'
    with pytest.raises(ManifestError) as exc_info:
        parse_manifest_bytes(raw.encode("utf-8"))
    assert exc_info.value.code == ErrorCode.MANIFEST_UNKNOWN_FIELD


def test_parse_manifest_bytes_rejects_unsupported_format_version_or_renderer() -> None:
    raw_ver = _valid_manifest_toml().replace("format_version = 1", "format_version = 2")
    with pytest.raises(UnsupportedFormatError):
        parse_manifest_bytes(raw_ver.encode("utf-8"))

    raw_eng = _valid_manifest_toml().replace('renderer = "placeholders-v1"', 'renderer = "jinja2"')
    with pytest.raises(UnsupportedFormatError):
        parse_manifest_bytes(raw_eng.encode("utf-8"))


def test_parse_manifest_bytes_supports_text_output_with_length_bounds() -> None:
    raw = (
        "format_version = 1\n"
        'name = "demo.summary"\n'
        'version = "1.0.0"\n'
        'description = "Summarize text."\n'
        'renderer = "placeholders-v1"\n'
        'input_schema = "input.schema.json"\n\n'
        "[output]\n"
        'mode = "text"\n'
        "min_length = 10\n"
        "max_length = 500\n\n"
        "[[messages]]\n"
        'role = "user"\n'
        'file = "user.md"\n'
    )
    parsed = parse_manifest_bytes(raw.encode("utf-8"))
    assert parsed.output_mode is OutputMode.TEXT
    assert parsed.output_min_length == 10
    assert parsed.output_max_length == 500


def test_parse_manifest_bytes_validation_error_branches() -> None:
    from prompt_contracts.errors import ResourceLimitError
    from prompt_contracts.types import RuntimePolicy

    base = _valid_manifest_toml()
    with pytest.raises(ResourceLimitError):
        parse_manifest_bytes(base.encode("utf-8"), policy=RuntimePolicy(max_manifest_bytes=16))

    with pytest.raises(ManifestError):
        parse_manifest_bytes(b"\xff\xfeinvalid")

    with pytest.raises(ManifestError):
        parse_manifest_bytes(b"not valid = [toml")

    for invalid_toml in [
        'format_version = 1\nname = "a.b"\n',
        base.replace("format_version = 1", 'format_version = "1"'),
        base.replace('name = "career.application-answer"', "name = 123"),
        base.replace('description = "Answer a question."', 'description = ""'),
        base.replace('renderer = "placeholders-v1"', "renderer = 1"),
        base.replace('input_schema = "input.schema.json"', "input_schema = 1"),
        base.replace('[output]\nmode = "json"\nschema = "output.schema.json"', 'output = "json"'),
        base.replace('schema = "output.schema.json"', 'schema = "output.schema.json"\nextra = 1'),
        base.replace('schema = "output.schema.json"', "schema = 123"),
        base.replace(
            'mode = "json"\nschema = "output.schema.json"',
            'mode = "text"\nmin_length = 1\nmax_length = 5\nextra = 1',
        ),
        base.replace(
            'mode = "json"\nschema = "output.schema.json"',
            'mode = "text"\nmin_length = 10\nmax_length = 5',
        ),
        base.replace('mode = "json"', 'mode = "xml"'),
        base.replace(
            '[[messages]]\nrole = "system"\nfile = "system.md"\n\n'
            '[[messages]]\nrole = "user"\nfile = "user.md"',
            "messages = []",
        ),
        base.replace(
            '[[messages]]\nrole = "system"\nfile = "system.md"\n\n'
            '[[messages]]\nrole = "user"\nfile = "user.md"',
            'messages = ["bad"]',
        ),
        base.replace('file = "system.md"', 'file = "system.md"\nextra = 1'),
        base.replace('file = "system.md"', ""),
        base.replace('role = "system"', 'role = "tool"'),
        base.replace('file = "system.md"', "file = 123"),
        base.replace('file = "system.md"', 'file = "contract.toml"'),
        base.replace('schema = "output.schema.json"', 'schema = "input.schema.json"'),
    ]:
        with pytest.raises(ManifestError):
            parse_manifest_bytes(invalid_toml.encode("utf-8"))

    with pytest.raises(ResourceLimitError):
        parse_manifest_bytes(base.encode("utf-8"), policy=RuntimePolicy(max_messages=1))
