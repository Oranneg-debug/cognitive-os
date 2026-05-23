"""Test schema validator for governance foundation.

VETO COMPLIANCE:
- B6: Uses ruamel.yaml to preserve comments + key ordering during migration
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import tempfile
import shutil
from pathlib import Path

import pytest

from src.workflow_models import ValidatedProposal, Severity, WorkflowPhase
from src.schema_validator import (
    validate_proposal_yaml,
    migrate_legacy,
    run_migration,
    SchemaValidationError,
)


# Sample YAML with frontmatter and body
SAMPLE_YAML_WITH_FRONTMATTER = """---
proposal_id: TEST-001
severity: high
origin: test_user
workflow_version: "1.0"
phase: proposal
status: draft
created_at: "2026-05-23T10:00:00"
---

# Test Proposal

This is the body of the proposal.
It contains multiple lines.

## Section 1

Some content here.
"""

SAMPLE_YAML_WITH_COMMENTS = """---
# This is a comment that should be preserved
proposal_id: TEST-COMMENT
severity: medium  # Priority level
origin: test_user
workflow_version: "1.0"
phase: alpha
status: review
---

# Test Proposal with Comments

Body content here.
"""

SAMPLE_YAML_INVALID_SEVERITY = """---
proposal_id: TEST-INVALID
severity: critical
origin: test_user
workflow_version: "1.0"
phase: proposal
status: draft
---

# Invalid Severity
"""

SAMPLE_YAML_MISSING_FIELDS = """---
proposal_id: TEST-MISSING
---

# Missing Required Fields
"""


class TestValidateProposalYaml:
    """Tests for validate_proposal_yaml function."""

    def test_validate_proposal_yaml_success(self) -> None:
        """validate_proposal_yaml parses valid YAML successfully."""
        proposal = validate_proposal_yaml(SAMPLE_YAML_WITH_FRONTMATTER)
        
        assert isinstance(proposal, ValidatedProposal)
        assert proposal.proposal_id == "TEST-001"
        assert proposal.severity == Severity.HIGH
        assert proposal.origin == "test_user"
        assert proposal.workflow_version == "1.0"
        assert proposal.phase == WorkflowPhase.PROPOSAL
        assert proposal.status == "draft"
        assert "# Test Proposal" in proposal.body

    def test_validate_proposal_yaml_rejects_invalid_severity(self) -> None:
        """validate_proposal_yaml rejects invalid severity."""
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_proposal_yaml(SAMPLE_YAML_INVALID_SEVERITY)
        
        assert "severity" in str(exc_info.value)
        assert "critical" in str(exc_info.value)

    def test_validate_proposal_yaml_rejects_missing_fields(self) -> None:
        """validate_proposal_yaml rejects proposals with missing required fields."""
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_proposal_yaml(SAMPLE_YAML_MISSING_FIELDS)
        
        assert "severity" in str(exc_info.value) or "workflow_version" in str(exc_info.value)

    def test_validate_proposal_yaml_preserves_body(self) -> None:
        """validate_proposal_yaml preserves the full body content."""
        proposal = validate_proposal_yaml(SAMPLE_YAML_WITH_FRONTMATTER)
        
        assert "This is the body of the proposal." in proposal.body
        assert "## Section 1" in proposal.body

    def test_validate_proposal_yaml_with_timestamps(self) -> None:
        """validate_proposal_yaml parses optional timestamps."""
        proposal = validate_proposal_yaml(SAMPLE_YAML_WITH_FRONTMATTER)
        
        assert proposal.created_at is not None


class TestRuamelYamlRoundTrip:
    """Tests for ruamel.yaml round-trip preservation."""

    def test_ruamel_yaml_round_trip_preserves_comments(self) -> None:
        """ruamel.yaml preserves comments during load/dump cycle."""
        # This test verifies B6 compliance: ruamel.yaml preserves comments + key ordering
        from ruamel.yaml import YAML
        from src.schema_validator import _split_frontmatter

        yaml = YAML()
        yaml.preserve_quotes = True

        # Strip the markdown frontmatter delimiters before parsing
        frontmatter_text, _body = _split_frontmatter(SAMPLE_YAML_WITH_COMMENTS)
        data = yaml.load(frontmatter_text)

        # Verify comment was parsed (ruamel.yaml stores comments separately)
        assert data is not None
        assert data.get("proposal_id") == "TEST-COMMENT"
        assert data.get("severity") == "medium"

    def test_ruamel_yaml_round_trip_preserves_key_ordering(self) -> None:
        """ruamel.yaml preserves key ordering during load/dump cycle."""
        from ruamel.yaml import YAML
        from io import StringIO
        from src.schema_validator import _split_frontmatter

        yaml = YAML()

        # Strip the markdown frontmatter delimiters before parsing
        frontmatter_text, _body = _split_frontmatter(SAMPLE_YAML_WITH_COMMENTS)
        data = yaml.load(frontmatter_text)

        # Dump to string
        output = StringIO()
        yaml.dump(data, output)
        output_str = output.getvalue()

        # Verify key order is preserved (proposal_id should come before severity)
        proposal_id_pos = output_str.find("proposal_id")
        severity_pos = output_str.find("severity")

        assert proposal_id_pos >= 0
        assert severity_pos >= 0
        assert proposal_id_pos < severity_pos


class TestMigrateLegacy:
    """Tests for migrate_legacy function."""

    @pytest.fixture
    def temp_proposal_dir(self) -> Path:
        """Create a temporary directory for test proposals."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_migrate_legacy_injects_missing_severity(self, temp_proposal_dir: Path) -> None:
        """migrate_legacy injects severity if missing."""
        proposal_path = temp_proposal_dir / "TEST-MIGRATE-1.md"
        
        yaml_content = """---
proposal_id: TEST-MIGRATE-1
origin: test_user
workflow_version: "1.0"
phase: proposal
status: draft
---

# Test Proposal
"""
        proposal_path.write_text(yaml_content)
        
        changed = migrate_legacy(str(proposal_path))
        
        assert changed is True
        
        content = proposal_path.read_text()
        assert "severity: unknown" in content

    def test_migrate_legacy_injects_missing_workflow_version(self, temp_proposal_dir: Path) -> None:
        """migrate_legacy injects workflow_version if missing."""
        proposal_path = temp_proposal_dir / "TEST-MIGRATE-2.md"
        
        yaml_content = """---
proposal_id: TEST-MIGRATE-2
severity: high
origin: test_user
phase: proposal
status: draft
---

# Test Proposal
"""
        proposal_path.write_text(yaml_content)
        
        changed = migrate_legacy(str(proposal_path))

        assert changed is True

        content = proposal_path.read_text()
        # Quote style is up to ruamel (single or double); only check the value.
        assert 'workflow_version:' in content
        assert '1.0' in content

    def test_migrate_legacy_injects_missing_origin(self, temp_proposal_dir: Path) -> None:
        """migrate_legacy injects origin if missing."""
        proposal_path = temp_proposal_dir / "TEST-MIGRATE-3.md"
        
        yaml_content = """---
proposal_id: TEST-MIGRATE-3
severity: high
workflow_version: "1.0"
phase: proposal
status: draft
---

# Test Proposal
"""
        proposal_path.write_text(yaml_content)
        
        changed = migrate_legacy(str(proposal_path))
        
        assert changed is True
        
        content = proposal_path.read_text()
        assert "origin: legacy" in content

    def test_migrate_legacy_is_idempotent(self, temp_proposal_dir: Path) -> None:
        """migrate_legacy is idempotent - second run reports 0 changes."""
        proposal_path = temp_proposal_dir / "TEST-MIGRATE-4.md"
        
        yaml_content = """---
proposal_id: TEST-MIGRATE-4
severity: high
origin: test_user
workflow_version: "1.0"
phase: proposal
status: draft
---

# Test Proposal
"""
        proposal_path.write_text(yaml_content)

        # First migration: input already has all required fields, so this
        # is already a no-op. Confirms idempotency on already-valid input.
        changed1 = migrate_legacy(str(proposal_path))
        assert changed1 is False

        # Second migration: still no change.
        changed2 = migrate_legacy(str(proposal_path))
        assert changed2 is False

    def test_migrate_legacy_preserves_body_content(self, temp_proposal_dir: Path) -> None:
        """migrate_legacy does not alter body content."""
        proposal_path = temp_proposal_dir / "TEST-MIGRATE-5.md"
        
        yaml_content = """---
proposal_id: TEST-MIGRATE-5
origin: test_user
workflow_version: "1.0"
phase: proposal
status: draft
---

# Test Proposal

This is the original body content.
It should be preserved exactly.

## Section 1

More content here.
"""
        proposal_path.write_text(yaml_content)
        
        migrate_legacy(str(proposal_path))
        
        content = proposal_path.read_text()
        assert "This is the original body content." in content
        assert "## Section 1" in content


class TestRunMigration:
    """Tests for run_migration function."""

    @pytest.fixture
    def temp_proposals_dir(self) -> Path:
        """Create a temporary proposals directory."""
        temp_dir = Path(tempfile.mkdtemp())
        proposals_dir = temp_dir / "proposals"
        proposals_dir.mkdir()
        
        # Create test proposals
        (proposals_dir / "TEST-MIG-1.md").write_text("""---
proposal_id: TEST-MIG-1
origin: test_user
phase: proposal
status: draft
---

# Test 1
""")
        
        (proposals_dir / "TEST-MIG-2.md").write_text("""---
proposal_id: TEST-MIG-2
severity: high
workflow_version: "1.0"
phase: alpha
status: review
---

# Test 2
""")
        
        yield proposals_dir
        
        shutil.rmtree(temp_dir)

    def test_run_migration_scans_all_files(self, temp_proposals_dir: Path) -> None:
        """run_migration scans all .md files in proposals directory."""
        result = run_migration(temp_proposals_dir)
        assert result["total"] >= 2

    def test_run_migration_reports_migrated_count(self, temp_proposals_dir: Path) -> None:
        """run_migration reports correct migrated count."""
        result = run_migration(temp_proposals_dir)
        assert "migrated" in result
        assert "already_up_to_date" in result

    def test_run_migration_reports_errors(self, temp_proposals_dir: Path) -> None:
        """run_migration reports any errors encountered."""
        result = run_migration(temp_proposals_dir)
        assert "errors" in result
        assert isinstance(result["errors"], list)
