"""Tests for src.markdown_fence_parser (T2)."""

from __future__ import annotations

import pytest

from src.markdown_fence_parser import (
    FenceSegment,
    _is_fence_line,
    iter_segments,
    strip_fences,
)


# ---- _is_fence_line -------------------------------------------------


def test_is_fence_line_recognises_bare_triple_backtick() -> None:
    assert _is_fence_line("```")
    assert _is_fence_line("```\n")


def test_is_fence_line_recognises_with_info_string() -> None:
    assert _is_fence_line("```python\n")
    assert _is_fence_line("```yaml")


def test_is_fence_line_recognises_four_or_more_backticks() -> None:
    assert _is_fence_line("````")
    assert _is_fence_line("`````\n")


def test_is_fence_line_rejects_two_or_fewer_backticks() -> None:
    assert not _is_fence_line("``")
    assert not _is_fence_line("`")
    assert not _is_fence_line("")


def test_is_fence_line_rejects_inline_backticks() -> None:
    # An inline-code line like `code` is not a fence.
    assert not _is_fence_line("`code`")
    assert not _is_fence_line("text with ``` inline")


def test_is_fence_line_rejects_info_string_with_backtick() -> None:
    # Per CommonMark, the info string must not contain a backtick.
    assert not _is_fence_line("```py`thon")


def test_is_fence_line_allows_up_to_three_spaces_indent() -> None:
    assert _is_fence_line("   ```")
    assert not _is_fence_line("    ```")  # 4 spaces = code block, not fence


# ---- iter_segments / strip_fences -----------------------------------


def test_strip_fences_removes_simple_block() -> None:
    text = "before\n```\ninside\n```\nafter\n"
    out = strip_fences(text)
    assert "inside" not in out
    assert "before" in out
    assert "after" in out


def test_strip_fences_removes_marker_inside_fence() -> None:
    text = "real #boardroom marker\n```\n#boardroom inside fence\n```\nend\n"
    out = strip_fences(text)
    # The OUTSIDE marker survives
    assert "real #boardroom marker" in out
    # The INSIDE one is gone
    assert "#boardroom inside fence" not in out


def test_strip_fences_handles_unclosed_fence() -> None:
    # An unclosed fence consumes everything after the opening ```.
    text = "before\n```\n#boardroom2\n"
    out = strip_fences(text)
    assert "before" in out
    assert "#boardroom2" not in out


def test_strip_fences_toggles_on_every_triple_backtick() -> None:
    # CommonMark: every triple-backtick line toggles. There is no depth.
    text = "\n".join([
        "#boardroom",        # 0 outside  → KEEP
        "```",               # toggle
        "nested",            #   inside   → DROP
        "```",               # toggle
        "inside outer",      # 0 outside  → KEEP (despite the name)
        "```",               # toggle
        "#boardroom2",       #   inside   → DROP
        "",
    ])
    out = strip_fences(text)
    assert "#boardroom" in out
    assert "inside outer" in out
    assert "nested" not in out
    assert "#boardroom2" not in out


def test_strip_fences_preserves_content_with_no_fences() -> None:
    text = "just\nplain\nmarkdown\n"
    assert strip_fences(text) == text


def test_iter_segments_classifies_correctly() -> None:
    text = "a\n```\nb\n```\nc\n"
    segs = list(iter_segments(text))
    # segments: ["a\n```\n" outside] + ["b\n```\n" inside] + ["c\n" outside]
    assert len(segs) == 3
    assert segs[0].inside_fence is False
    assert segs[1].inside_fence is True
    assert segs[2].inside_fence is False
    # Round-trip: concatenation is lossless.
    assert "".join(s.text for s in segs) == text


def test_iter_segments_yields_fence_segment_dataclass() -> None:
    segs = list(iter_segments("hello\n"))
    assert isinstance(segs[0], FenceSegment)
    assert segs[0].text == "hello\n"
    assert segs[0].inside_fence is False


# ---- regression case from Cline's stuck question --------------------


def test_nested_fence_case_from_design_review() -> None:
    """The case Cline asked about: confirm CommonMark toggle semantics.

    Input has 3 ``` lines and 2 visible 'inside' regions. Standard markdown
    treats every ``` as a toggle (no depth counter), so:
      - first  ```: open
      - second ```: close
      - third  ```: open (unclosed → consumes EOF)
    """
    text = (
        "#boardroom\n"
        "```\n"
        "nested\n"
        "```\n"
        "inside outer\n"
        "```\n"
        "#boardroom2\n"
    )
    out = strip_fences(text)
    assert "#boardroom" in out and "inside outer" in out
    assert "nested" not in out and "#boardroom2" not in out
