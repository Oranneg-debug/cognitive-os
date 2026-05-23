"""
Stateful Markdown fence parser (T2, ARCH-2007E0A1).

Strips fenced code blocks from Markdown text so downstream marker matching
(e.g. routing rules looking for `#boardroom`) only sees content OUTSIDE
fences. Implements CommonMark-style fence toggling: every triple-backtick
line flips the "inside fence" state. There is no nesting — a code block
is opened by the first `` ``` `` line and closed by the next one.

Used by output_router.py per the T2 binding refinement: replace naive
regex matching with a state machine that tracks fence boundaries.

VETO COMPLIANCE:
- T2: stateful parser, not regex
- T-V4: no fragile regex for fence stripping
- CSTR-PREMATURE-SYNC: no concurrency primitives
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


# A line is considered a fence boundary if it consists of optional
# whitespace followed by three or more backticks (CommonMark §4.5), with
# only optional whitespace + an optional info string after. A line that
# happens to *contain* a triple backtick mid-line (e.g. inline ``` `` `)
# is NOT a fence — only standalone fence lines toggle state.
_BACKTICK = "`"


def _is_fence_line(line: str) -> bool:
    """Return True iff ``line`` is a fence boundary (CommonMark §4.5).

    A fence line:
      - has up to 3 leading spaces of indent,
      - then a run of 3+ backticks,
      - then optional info string (any text not containing more backticks).

    This implementation is deliberately conservative: it does not attempt
    to track varying fence lengths for nested fences. CommonMark allows
    nesting only via fences of DIFFERENT lengths (e.g. ```` outer, ``` inner).
    For the marker-stripping use case in OutputRouter, any 3+ backtick
    line toggles the boolean state, which is the standard interpretation
    used by most parsers and matches the chairman's intent.
    """
    stripped = line.lstrip(" ")
    # Reject lines with > 3 leading spaces (CommonMark indent rule).
    if len(line) - len(stripped) > 3:
        return False
    if not stripped.startswith(_BACKTICK * 3):
        return False
    # Count opening backticks
    i = 0
    while i < len(stripped) and stripped[i] == _BACKTICK:
        i += 1
    if i < 3:
        return False
    # The info string (after the backticks) must not contain a backtick.
    info = stripped[i:].rstrip("\n\r")
    return _BACKTICK not in info


@dataclass(frozen=True)
class FenceSegment:
    """A contiguous slice of text classified as either inside or outside a fence."""

    text: str
    inside_fence: bool


def iter_segments(text: str) -> Iterable[FenceSegment]:
    """Yield (text, inside_fence) segments for ``text``.

    Each segment ends at a fence boundary line. The fence boundary lines
    themselves are emitted with the state they CLOSE (i.e. the opening
    fence belongs to the "outside" segment, the closing fence belongs to
    the "inside" segment), which matches how most editors highlight them.
    """
    inside = False
    buf: List[str] = []
    # Keep line terminators by splitting with keepends=True.
    for line in text.splitlines(keepends=True):
        buf.append(line)
        if _is_fence_line(line):
            yield FenceSegment(text="".join(buf), inside_fence=inside)
            buf = []
            inside = not inside
    if buf:
        yield FenceSegment(text="".join(buf), inside_fence=inside)


def strip_fences(text: str) -> str:
    """Return ``text`` with fenced code blocks (and the fence lines) removed.

    Useful for marker matching: feed the result to a regex search so that
    a marker like ``#boardroom`` inside a code block does not trigger a
    false routing decision.
    """
    return "".join(seg.text for seg in iter_segments(text) if not seg.inside_fence)


def outside_fence_text(text: str) -> str:
    """Alias for ``strip_fences``. Provided for grep-friendly naming."""
    return strip_fences(text)
