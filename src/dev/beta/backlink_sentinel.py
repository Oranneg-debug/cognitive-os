"""
Backlink Integrity Sentinel.

Scans the vault for Obsidian-style [[wikilinks]] and reports drift:
- broken targets (file renamed/moved/deleted)
- aliased links still pointing at the old name
- repairable drift (an unambiguous rename can be inferred)

The sentinel never edits files unless `repair=True` is passed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# matches [[Target]], [[Target|Alias]], [[folder/Target#heading|Alias]]
_LINK_RE = re.compile(r"\[\[([^\[\]\n|#]+)(?:#[^\[\]\n|]*)?(?:\|([^\[\]\n]*))?\]\]")


@dataclass
class BrokenLink:
    file: Path
    line: int
    target: str
    alias: str | None = None
    suggested_fix: str | None = None


@dataclass
class SentinelReport:
    scanned: int = 0
    links_total: int = 0
    broken: list[BrokenLink] = field(default_factory=list)
    repaired: list[BrokenLink] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.broken


class BacklinkSentinel:
    def __init__(self, vault_root: str | Path):
        self.vault_root = Path(vault_root)

    # ---- index --------------------------------------------------------

    def _markdown_files(self) -> list[Path]:
        return [p for p in self.vault_root.rglob("*.md") if p.is_file()]

    def _build_index(self, files: Iterable[Path]) -> dict[str, list[Path]]:
        """Map basename (no extension, lower) → list of matching paths."""
        idx: dict[str, list[Path]] = {}
        for p in files:
            idx.setdefault(p.stem.lower(), []).append(p)
        return idx

    # ---- scan ---------------------------------------------------------

    def scan(self, *, repair: bool = False) -> SentinelReport:
        report = SentinelReport()
        files = self._markdown_files()
        index = self._build_index(files)

        for md in files:
            report.scanned += 1
            try:
                content = md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            changed = False
            new_lines: list[str] = []
            for lineno, line in enumerate(content.splitlines(keepends=True), start=1):
                line_out = line
                for m in _LINK_RE.finditer(line):
                    report.links_total += 1
                    target = m.group(1).strip()
                    alias = (m.group(2) or "").strip() or None
                    if self._exists(target, index):
                        continue
                    suggestion = self._suggest(target, index)
                    broken = BrokenLink(md, lineno, target, alias, suggestion)
                    if repair and suggestion:
                        # rewrite [[old]] → [[new]] (preserve alias)
                        replacement = (
                            f"[[{suggestion}|{alias}]]" if alias else f"[[{suggestion}]]"
                        )
                        line_out = line_out.replace(m.group(0), replacement)
                        changed = True
                        report.repaired.append(broken)
                    else:
                        report.broken.append(broken)
                new_lines.append(line_out)

            if changed:
                md.write_text("".join(new_lines), encoding="utf-8")

        return report

    # ---- helpers ------------------------------------------------------

    @staticmethod
    def _exists(target: str, index: dict[str, list[Path]]) -> bool:
        return target.lower() in index or "/" in target  # path-based: trust user

    @staticmethod
    def _suggest(target: str, index: dict[str, list[Path]]) -> str | None:
        """Suggest a unique replacement when basename matching is unambiguous."""
        t = target.lower()
        # exact match on stem (case-insensitive)
        if t in index and len(index[t]) == 1:
            return index[t][0].stem
        # fuzzy: identical after stripping non-alnum
        norm = re.sub(r"[^a-z0-9]+", "", t)
        candidates = [
            paths[0].stem
            for stem, paths in index.items()
            if len(paths) == 1 and re.sub(r"[^a-z0-9]+", "", stem) == norm
        ]
        return candidates[0] if len(candidates) == 1 else None
