"""
Schema Validation & Legacy Migration for Governance Foundation

This module provides YAML frontmatter validation and legacy proposal migration.

VETO COMPLIANCE:
- V5: No I/O in workflow_models.py (we're the validator, not the model)
- B6: Uses ruamel.yaml to preserve comments + key ordering during migration
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import glob
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
except ImportError as e:
    raise ImportError(
        "ruamel.yaml is required for schema validation. "
        "Install with: pip install ruamel.yaml"
    ) from e

from src.workflow_models import (
    ValidatedProposal,
    Severity,
    WorkflowPhase,
    SchemaValidationError,
)


# Configuration
SCHEMA_VALIDATION_MODE = os.environ.get("SCHEMA_VALIDATION_MODE", "warn").lower()
assert SCHEMA_VALIDATION_MODE in ("warn", "reject"), (
    f"SCHEMA_VALIDATION_MODE must be 'warn' or 'reject', got '{SCHEMA_VALIDATION_MODE}'"
)


def validate_proposal_yaml(yaml_text: str) -> ValidatedProposal:
    """
    Parse YAML frontmatter and validate against schema.
    
    Args:
        yaml_text: Raw markdown text with YAML frontmatter
        
    Returns:
        ValidatedProposal if validation passes
        
    Raises:
        SchemaValidationError: If validation fails
    """
    try:
        # Split frontmatter from body
        frontmatter, body = _split_frontmatter(yaml_text)
        
        # Parse YAML
        yaml = YAML(typ="safe")
        data = yaml.load(frontmatter)
        
        if data is None:
            data = {}
            
        # Validate required fields
        _validate_required_fields(data)
        
        # Convert to ValidatedProposal
        proposal = _build_validated_proposal(data, body)
        
        return proposal
        
    except Exception as e:
        if isinstance(e, SchemaValidationError):
            raise
        raise SchemaValidationError(
            field="yaml_parse",
            value=str(e)[:100],
            reason=f"Failed to parse YAML: {e}"
        ) from e


def _split_frontmatter(text: str) -> Tuple[str, str]:
    """Split markdown into frontmatter and body."""
    lines = text.split("\n")
    
    if not lines or lines[0].strip() != "---":
        raise SchemaValidationError(
            field="format",
            value="missing",
            reason="YAML frontmatter must start with '---'"
        )
    
    # Find closing ---
    end_idx = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break
    
    if end_idx == -1:
        raise SchemaValidationError(
            field="format",
            value="missing",
            reason="YAML frontmatter must end with '---'"
        )
    
    frontmatter = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])
    
    return frontmatter, body


def _validate_required_fields(data: dict) -> None:
    """Validate that all required fields are present and valid."""
    required_fields = ["severity", "origin", "workflow_version", "phase", "status"]
    
    for field in required_fields:
        if field not in data:
            raise SchemaValidationError(
                field=field,
                value="missing",
                reason=f"Required field '{field}' is missing"
            )
    
    # Validate severity enum
    severity_val = data.get("severity")
    if not isinstance(severity_val, str):
        raise SchemaValidationError(
            field="severity",
            value=str(type(severity_val)),
            reason="Must be a string"
        )
    
    valid_severities = [s.value for s in Severity]
    if severity_val.lower() not in valid_severities:
        raise SchemaValidationError(
            field="severity",
            value=severity_val,
            reason=f"Must be one of: {', '.join(valid_severities)}"
        )
    
    # Validate phase enum
    phase_val = data.get("phase")
    if not isinstance(phase_val, str):
        raise SchemaValidationError(
            field="phase",
            value=str(type(phase_val)),
            reason="Must be a string"
        )
    
    valid_phases = [p.value for p in WorkflowPhase]
    if phase_val.lower() not in valid_phases:
        raise SchemaValidationError(
            field="phase",
            value=phase_val,
            reason=f"Must be one of: {', '.join(valid_phases)}"
        )


def _build_validated_proposal(data: dict, body: str) -> ValidatedProposal:
    """Build a ValidatedProposal from parsed data."""
    severity = Severity(str(data.get("severity", "unknown")).lower())
    phase = WorkflowPhase(str(data.get("phase", "backlog")).lower())
    
    # Ensure workflow_version is string (YAML may parse "1.0" as float)
    workflow_version = str(data.get("workflow_version", "1.0"))
    
    return ValidatedProposal(
        proposal_id=str(data.get("proposal_id", "UNKNOWN")),
        severity=severity,
        origin=str(data.get("origin", "unknown")),
        workflow_version=workflow_version,
        phase=phase,
        status=str(data.get("status", "draft")),
        body=body.strip(),
        created_at=datetime.now() if data.get("created_at") else None,
        updated_at=datetime.now() if data.get("updated_at") else None
    )


def migrate_legacy(path: str) -> bool:
    """
    Inject defaults into legacy proposals without altering body content.
    
    Idempotent: running twice produces zero diff.
    
    Args:
        path: Path to the proposal markdown file
        
    Returns:
        True if migration was applied, False if already up-to-date
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        
        # Split frontmatter from body
        frontmatter_text, body = _split_frontmatter(text)
        
        # Parse with ruamel.yaml to preserve formatting
        yaml = YAML()
        yaml.preserve_quotes = True
        data = yaml.load(frontmatter_text)
        
        if data is None:
            data = CommentedMap()
        
        # Track changes
        changed = False
        
        # Inject defaults only if missing (idempotent)
        if "severity" not in data or not isinstance(data.get("severity"), str):
            data["severity"] = "unknown"
            changed = True
            
        if "workflow_version" not in data or not isinstance(data.get("workflow_version"), str):
            data["workflow_version"] = "1.0"
            changed = True
            
        if "origin" not in data or not isinstance(data.get("origin"), str):
            data["origin"] = "legacy"
            changed = True
        
        # Write back only if changes were made
        if changed:
            # Reconstruct frontmatter via StringIO (ruamel needs a stream
            # with write(), not a list).
            from io import StringIO
            yaml_buf = StringIO()
            yaml.dump(data, yaml_buf)
            yaml_text = yaml_buf.getvalue().rstrip("\n")
            new_text = f"---\n{yaml_text}\n---\n{body}"

            # Atomic write with fsync
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path, path)
            # fsync the directory on POSIX; Windows doesn't support dir fsync.
            if os.name != "nt":
                dir_fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)

        return changed
        
    except Exception as e:
        raise SchemaValidationError(
            field="migration",
            value=path,
            reason=f"Failed to migrate legacy proposal: {e}"
        ) from e


def run_migration(proposals_dir: Optional[Path] = None) -> dict:
    """
    Scan all proposals for missing fields and migrate them.

    Idempotent: running twice produces zero diff on second run.

    Args:
        proposals_dir: Optional directory to scan. Defaults to
            ``dev/proposals`` (production). Pass a different path in tests.

    Returns:
        Migration report with counts
    """
    from src.paths import PROPOSALS_DIR
    proposals_dir = Path(proposals_dir) if proposals_dir else PROPOSALS_DIR

    if not proposals_dir.exists():
        return {
            "total": 0,
            "migrated": 0,
            "errors": [],
            "already_up_to_date": 0
        }

    md_files = glob.glob(str(proposals_dir / "*.md"))
    
    migrated = 0
    errors = []
    already_up_to_date = 0
    
    for filepath in md_files:
        try:
            if migrate_legacy(filepath):
                migrated += 1
            else:
                already_up_to_date += 1
        except SchemaValidationError as e:
            errors.append({
                "file": filepath,
                "error": str(e)
            })
    
    return {
        "total": len(md_files),
        "migrated": migrated,
        "errors": errors,
        "already_up_to_date": already_up_to_date
    }


def compute_file_hash(path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_schema_mode() -> None:
    """
    Check if schema validation should proceed based on mode.
    
    Raises:
        SchemaValidationError: If mode is 'reject' and validation fails
    """
    if SCHEMA_VALIDATION_MODE == "reject":
        raise RuntimeError(
            f"Schema validation is in REJECT mode ({SCHEMA_VALIDATION_MODE}). "
            "Set SCHEMA_VALIDATION_MODE=warn to allow warnings."
        )