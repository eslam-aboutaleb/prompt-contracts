"""Hypothesis property tests for single-pass non-re-entrant rendering (T07, AC-06)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from prompt_contracts.rendering.parser import parse_template
from prompt_contracts.rendering.renderer import render_message_template
from prompt_contracts.types import MessageRole, MessageTemplate

_RAW = "Prefix [{{untrusted}}] Middle {{{{literal}}}} Suffix [{{secondary}}]"
_TEMPLATE = MessageTemplate(
    role=MessageRole.USER,
    file="user.md",
    raw_text=_RAW,
    tokens=parse_template(_RAW, source_path="user.md"),
)


@settings(max_examples=75, deadline=None)
@given(
    untrusted_parts=st.lists(
        st.sampled_from(
            [
                "plain",
                "{{secondary}}",
                "{{untrusted}}",
                "{{{{",
                "}}}}",
                "{single}",
                '{"json": 1}',
                "\n",
            ]
        ),
        min_size=0,
        max_size=15,
    ),
    secondary=st.text(min_size=0, max_size=60),
)
def test_single_pass_rendering_never_evaluates_injected_tokens(
    untrusted_parts: list[str], secondary: str
) -> None:
    untrusted = "".join(untrusted_parts)
    rendered = render_message_template(
        _TEMPLATE,
        {"untrusted": untrusted, "secondary": secondary},
    )
    expected = f"Prefix [{untrusted}] Middle {{{{literal}}}} Suffix [{secondary}]"
    assert rendered.content == expected
