"""Tests for src.writer_protocols (T1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.writer_protocols import (
    BackendWriterProtocol,
    SingleWriterRuleViolation,
    VaultWriterProtocol,
    assert_no_vault_writer,
)


class _GoodBackend:
    """A duck-typed backend writer (matches BackendWriterProtocol)."""

    def write(self, destination: Path, content: str) -> Path:
        return destination


class _RogueVault:
    """A vault writer that should be rejected by the guard."""

    def write_to_vault(self, vault_destination: Path, content: str) -> Path:
        return vault_destination


class _AmbiguousBoth:
    """A class that implements BOTH protocols — must still be rejected."""

    def write(self, destination: Path, content: str) -> Path:
        return destination

    def write_to_vault(self, vault_destination: Path, content: str) -> Path:
        return vault_destination


class _Unrelated:
    """A class with no relevant methods — irrelevant to either protocol."""

    def do_something_else(self) -> None:
        pass


# ---- structural isinstance --------------------------------------------------


def test_backend_protocol_recognises_duck_typed_writer() -> None:
    assert isinstance(_GoodBackend(), BackendWriterProtocol)


def test_vault_protocol_recognises_duck_typed_writer() -> None:
    assert isinstance(_RogueVault(), VaultWriterProtocol)


def test_protocols_are_disjoint_for_single_purpose_classes() -> None:
    assert not isinstance(_GoodBackend(), VaultWriterProtocol)
    assert not isinstance(_RogueVault(), BackendWriterProtocol)


def test_unrelated_class_matches_neither_protocol() -> None:
    u = _Unrelated()
    assert not isinstance(u, BackendWriterProtocol)
    assert not isinstance(u, VaultWriterProtocol)


def test_ambiguous_class_matches_both_protocols() -> None:
    # Structural typing: a class that exposes both methods satisfies both.
    a = _AmbiguousBoth()
    assert isinstance(a, BackendWriterProtocol)
    assert isinstance(a, VaultWriterProtocol)


# ---- runtime guard ----------------------------------------------------------


def test_guard_accepts_backend_only_writer() -> None:
    # No exception → pass
    assert_no_vault_writer(_GoodBackend())


def test_guard_accepts_unrelated_object() -> None:
    # No exception for a class with neither method
    assert_no_vault_writer(_Unrelated())


def test_guard_rejects_vault_writer() -> None:
    with pytest.raises(SingleWriterRuleViolation) as exc:
        assert_no_vault_writer(_RogueVault())
    # The error message should name the rejected type and reference the
    # constraint document so debugging is one grep away.
    assert "_RogueVault" in str(exc.value)


def test_guard_rejects_ambiguous_writer() -> None:
    # If a class exposes write_to_vault at all, it is forbidden in the
    # OutputRouter's writer slot — even if it also implements `write`.
    with pytest.raises(SingleWriterRuleViolation):
        assert_no_vault_writer(_AmbiguousBoth())
