"""
Access control tier layer.

OS-level ACLs are too coarse; this module enforces the governance tiers
specified in the proposal:

    Directory        | Read | Write | Approve
    Boardroom        |  ✓   |       |   ✓
    Technical        |  ✓   |   ✓   |   ✓
    Requests/Inbox   |  ✓   |   ✓   |
    Requests/Drafts  |  ✓   |   ✓   |
    Requests/Archive |  ✓   |       |

A `Principal` is identified by `roles` (a set). Tiers are configured in
`access_tiers.json`; defaults are baked in.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_TIERS: dict = {
    "Reports/Boardroom":  {"read": ["*"],         "write": ["board"],          "approve": ["board"]},
    "Reports/Technical":  {"read": ["*"],         "write": ["technical", "board"], "approve": ["board", "technical"]},
    "Reports/Creative":   {"read": ["*"],         "write": ["creative", "board"],  "approve": ["board"]},
    "Reports/Dev":        {"read": ["*"],         "write": ["dev", "board"],       "approve": ["board"]},
    "Requests/Inbox":     {"read": ["*"],         "write": ["*"],              "approve": []},
    "Requests/Drafts":    {"read": ["*"],         "write": ["*"],              "approve": []},
    "Requests/Archive":   {"read": ["*"],         "write": [],                 "approve": ["board"]},
}


class AccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Principal:
    name: str
    roles: frozenset[str] = field(default_factory=frozenset)


class AccessControl:
    def __init__(self, vault_root: str | Path, tiers: dict | None = None):
        self.vault_root = Path(vault_root).resolve()
        self.tiers = tiers if tiers is not None else DEFAULT_TIERS

    @classmethod
    def from_config(cls, vault_root: str | Path, config_path: str | Path) -> "AccessControl":
        with open(config_path, "r", encoding="utf-8") as f:
            return cls(vault_root, json.load(f))

    # ---- core checks ---------------------------------------------------

    def _tier_for(self, path: str | Path) -> dict | None:
        rel = self._relpath(path)
        for prefix, rules in self.tiers.items():
            norm = prefix.replace("\\", "/")
            if rel == norm or rel.startswith(norm + "/"):
                return rules
        return None

    def can(self, principal: Principal, action: str, path: str | Path) -> bool:
        """Return True if `principal` may perform `action` on `path`."""
        rules = self._tier_for(path)
        if rules is None:
            # outside the governed tree → deny by default for writes/approve,
            # allow reads (CognitiveOS prefers visibility)
            return action == "read"
        allowed: Iterable[str] = rules.get(action, [])
        if "*" in allowed:
            return True
        return bool(principal.roles.intersection(allowed))

    def require(self, principal: Principal, action: str, path: str | Path) -> None:
        if not self.can(principal, action, path):
            raise AccessDenied(
                f"{principal.name!r} ({sorted(principal.roles)}) cannot {action} {path}"
            )

    # ---- helpers -------------------------------------------------------

    def _relpath(self, path: str | Path) -> str:
        p = Path(path)
        try:
            rel = p.resolve().relative_to(self.vault_root)
        except ValueError:
            rel = p
        return str(rel).replace("\\", "/")
