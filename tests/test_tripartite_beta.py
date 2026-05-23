"""
End-to-end tests for DEV-20260520-165800-7E5FA256 Beta deliverables.

Run with:  python -m pytest cognitive-os/tests/test_tripartite_beta.py -v
   or:     python cognitive-os/tests/test_tripartite_beta.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dev.beta import (  # noqa: E402
    METADATA_VERSION,
    AccessControl,
    BacklinkSentinel,
    IngestionEngine,
    MetadataIndex,
    dump_frontmatter,
    parse_markdown,
    sanitize_filename,
    validate_frontmatter,
)
from src.dev.beta.access_control import AccessDenied, Principal  # noqa: E402


def _valid_fm() -> dict:
    return {
        "council": "Boardroom",
        "type": "boardroom",
        "status": "draft",
        "date": "2026-05-20",
        "owner": "alice@cognitiveos",
        "tags": ["ai-ethics"],
        "metadata_version": METADATA_VERSION,
    }


class SchemaTests(unittest.TestCase):
    def test_valid_frontmatter_passes(self):
        ok, errs = validate_frontmatter(_valid_fm())
        self.assertTrue(ok, errs)

    def test_missing_metadata_version_fails(self):
        fm = _valid_fm()
        del fm["metadata_version"]
        ok, errs = validate_frontmatter(fm)
        self.assertFalse(ok)
        self.assertTrue(any("metadata_version" in e for e in errs))

    def test_wrong_version_rejected(self):
        fm = _valid_fm()
        fm["metadata_version"] = "0.9"
        ok, errs = validate_frontmatter(fm)
        self.assertFalse(ok)

    def test_enum_enforced(self):
        fm = _valid_fm()
        fm["council"] = "Pirates"
        ok, _ = validate_frontmatter(fm)
        self.assertFalse(ok)

    def test_roundtrip(self):
        fm = _valid_fm()
        rendered = dump_frontmatter(fm, "body text\n")
        parsed_fm, parsed_body = parse_markdown(rendered)
        self.assertEqual(parsed_fm["council"], "Boardroom")
        self.assertIn("body text", parsed_body)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        self.src = self.vault / "incoming"
        self.src.mkdir()
        self.engine = IngestionEngine(self.vault)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_source(self, name: str, body: str = "Hello") -> Path:
        f = self.src / name
        f.write_text(body, encoding="utf-8")
        return f

    def test_filename_is_deterministic(self):
        from datetime import datetime

        when = datetime(2026, 5, 20, 12, 0, 0)
        n1 = sanitize_filename(council="Boardroom", type_="request", slug_source="Hello World!", when=when)
        n2 = sanitize_filename(council="Boardroom", type_="request", slug_source="Hello  World!!", when=when)
        self.assertEqual(n1, n2)
        self.assertEqual(n1, "2026-05-20-boardroom-request-hello-world.md")

    def test_creates_and_is_idempotent(self):
        s = self._write_source("note.md", "Original body")
        r1 = self.engine.ingest_file(s, source_channel="telegram")
        self.assertEqual(r1.action, "created", r1.reason)
        r2 = self.engine.ingest_file(s, source_channel="telegram")
        self.assertEqual(r2.action, "skipped_idempotent", r2.reason)
        self.assertEqual(r1.target, r2.target)

    def test_collision_renames(self):
        s1 = self._write_source("note.md", "body one")
        r1 = self.engine.ingest_file(s1, source_channel="telegram", slug_hint="dupe")
        self.assertEqual(r1.action, "created")
        s2 = self._write_source("note2.md", "body two")
        r2 = self.engine.ingest_file(s2, source_channel="telegram", slug_hint="dupe")
        self.assertEqual(r2.action, "renamed_collision")
        self.assertNotEqual(r1.target, r2.target)

    def test_invalid_council_rejected(self):
        s = self._write_source("bad.md", "x")
        r = self.engine.ingest_file(s, source_channel="telegram", council="Pirates")
        self.assertEqual(r.action, "rejected")

    def test_frontmatter_is_normalised(self):
        s = self._write_source("note.md", "body")
        r = self.engine.ingest_file(s, source_channel="obsidian")
        text = r.target.read_text(encoding="utf-8")
        fm, _ = parse_markdown(text)
        self.assertEqual(fm["metadata_version"], METADATA_VERSION)
        self.assertEqual(fm["source_channel"], "obsidian")


class BacklinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _w(self, name: str, content: str) -> Path:
        p = self.vault / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_clean_vault_is_ok(self):
        self._w("Alpha.md", "see [[Beta]]\n")
        self._w("Beta.md", "ok")
        rep = BacklinkSentinel(self.vault).scan()
        self.assertTrue(rep.ok, rep.broken)

    def test_detects_broken_link(self):
        self._w("Alpha.md", "see [[Gamma]]\n")
        self._w("Beta.md", "ok")
        rep = BacklinkSentinel(self.vault).scan()
        self.assertFalse(rep.ok)
        self.assertEqual(rep.broken[0].target, "Gamma")

    def test_repair_unambiguous_rename(self):
        self._w("Alpha.md", "see [[Old Note]]\n")
        self._w("Old-Note.md", "renamed")  # fuzzy match
        rep = BacklinkSentinel(self.vault).scan(repair=True)
        self.assertEqual(len(rep.repaired), 1)
        updated = (self.vault / "Alpha.md").read_text(encoding="utf-8")
        self.assertIn("[[Old-Note]]", updated)


class AccessControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        for sub in (
            "Reports/Boardroom",
            "Reports/Technical",
            "Requests/Inbox",
            "Requests/Archive",
        ):
            (self.vault / sub).mkdir(parents=True)
        self.acl = AccessControl(self.vault)

    def tearDown(self):
        self.tmp.cleanup()

    def test_board_can_write_boardroom(self):
        alice = Principal("alice", frozenset({"board"}))
        self.assertTrue(self.acl.can(alice, "write", self.vault / "Reports/Boardroom/x.md"))

    def test_anon_cannot_write_boardroom(self):
        bob = Principal("bob", frozenset({"viewer"}))
        self.assertFalse(self.acl.can(bob, "write", self.vault / "Reports/Boardroom/x.md"))
        with self.assertRaises(AccessDenied):
            self.acl.require(bob, "write", self.vault / "Reports/Boardroom/x.md")

    def test_anyone_can_write_inbox(self):
        bob = Principal("bob", frozenset())
        self.assertTrue(self.acl.can(bob, "write", self.vault / "Requests/Inbox/x.md"))

    def test_archive_write_denied_even_to_board(self):
        alice = Principal("alice", frozenset({"board"}))
        self.assertFalse(self.acl.can(alice, "write", self.vault / "Requests/Archive/x.md"))

    def test_reads_always_open(self):
        bob = Principal("bob", frozenset())
        self.assertTrue(self.acl.can(bob, "read", self.vault / "Reports/Boardroom/x.md"))


class MetadataIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        self.db = self.vault / "_index.db"
        for i, status in enumerate(["draft", "approved", "approved"]):
            fm = {
                "council": "Boardroom",
                "type": "boardroom",
                "status": status,
                "date": f"2026-05-{20 + i:02d}",
                "owner": "alice",
                "tags": ["governance"] if status == "approved" else [],
                "metadata_version": METADATA_VERSION,
            }
            (self.vault / f"note-{i}.md").write_text(dump_frontmatter(fm, "body"), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_and_query(self):
        with MetadataIndex(self.db) as idx:
            stats = idx.index_vault(self.vault)
            self.assertEqual(stats.indexed, 3)
            approved = idx.query(status="approved")
            self.assertEqual(len(approved), 2)
            tagged = idx.query(tag="governance")
            self.assertEqual(len(tagged), 2)

    def test_reindex_is_skipped_when_unchanged(self):
        with MetadataIndex(self.db) as idx:
            idx.index_vault(self.vault)
            stats = idx.index_vault(self.vault)
            self.assertEqual(stats.indexed, 0)
            self.assertEqual(stats.skipped, 3)

    def test_deletion_is_pruned(self):
        with MetadataIndex(self.db) as idx:
            idx.index_vault(self.vault)
            os.remove(self.vault / "note-0.md")
            stats = idx.index_vault(self.vault)
            self.assertEqual(stats.removed, 1)
            self.assertEqual(idx.count(), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
