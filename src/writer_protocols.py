"""
Writer Protocols (T1, ARCH-2007E0A1).

Defines the Interface Segregation contracts for the routing layer:

* ``BackendWriterProtocol`` — anything that writes to project paths
  (``dev/proposals/``, ``dev/decisions/``, ``dev/failed_routings/``).
  The ``OutputRouter`` depends on THIS protocol only.

* ``VaultWriterProtocol`` — anything that writes to the Obsidian vault.
  ONLY ``proposal_sync.py`` (and the existing ``obsidian_writer``) are
  permitted to implement this. The ``OutputRouter`` is forbidden from
  importing or instantiating any ``VaultWriterProtocol``.

The two protocols are deliberately disjoint so that:

1. Static analysis (mypy / pyright) catches misuse at type-check time.
2. A runtime guard (``assert_no_vault_writer``) catches misuse at import
   time if a caller smuggles a vault writer in via duck-typing.

VETO COMPLIANCE:
- T1: Interface Segregation between project-path and vault-path writers
- T-V2: No direct vault writes from OutputRouter (runtime guard below)
- E4: Single-writer rule enforced via runtime check, not just CI grep
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


# ════════════════════════════════════════════════════════════════════
#  PROTOCOLS
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class BackendWriterProtocol(Protocol):
    """Contract for writers that target project paths (``dev/...``).

    Implementers MUST NOT write to the Obsidian vault. The
    ``OutputRouter`` depends on this protocol; ``ProposalSync`` consumes
    the resulting project files and mirrors them to the vault.
    """

    def write(self, destination: Path, content: str) -> Path:
        """Persist ``content`` at ``destination`` and return the final path.

        ``destination`` is always a project-relative path under ``dev/``.
        Implementations should write atomically (temp + rename).
        """
        ...


@runtime_checkable
class VaultWriterProtocol(Protocol):
    """Contract for writers that target the Obsidian vault.

    The ``OutputRouter`` MUST NOT import or instantiate any class
    implementing this protocol. ``assert_no_vault_writer`` enforces this
    at runtime; the gate ``phase2_single_writer_guard`` enforces it at
    review time by scanning ``output_router.py`` for forbidden imports.
    """

    def write_to_vault(self, vault_destination: Path, content: str) -> Path:
        """Persist ``content`` at ``vault_destination`` inside the vault."""
        ...


# ════════════════════════════════════════════════════════════════════
#  RUNTIME GUARD (E4)
# ════════════════════════════════════════════════════════════════════


class SingleWriterRuleViolation(RuntimeError):
    """Raised when a caller smuggles a vault writer into a backend slot."""


def assert_no_vault_writer(candidate: object) -> None:
    """Guard used by ``OutputRouter`` to refuse any ``VaultWriterProtocol``.

    Call this on every writer dependency before storing it. Because
    ``VaultWriterProtocol`` is decorated with ``@runtime_checkable``, the
    isinstance check works structurally — even classes that don't import
    this module will be rejected if they happen to expose
    ``write_to_vault``.

    Raises:
        SingleWriterRuleViolation: when ``candidate`` looks like a vault
            writer.
    """
    if isinstance(candidate, VaultWriterProtocol):
        raise SingleWriterRuleViolation(
            "OutputRouter received a VaultWriterProtocol "
            f"(type={type(candidate).__name__!r}). Vault writes are the "
            "exclusive responsibility of ProposalSync. See "
            "docs/CONSTRAINT_PREMATURE_SYNCHRONIZATION.md and the T1 "
            "refinement of ARCH-2007E0A1."
        )


__all__ = [
    "BackendWriterProtocol",
    "VaultWriterProtocol",
    "SingleWriterRuleViolation",
    "assert_no_vault_writer",
]
