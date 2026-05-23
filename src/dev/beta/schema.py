"""
YAML schema v1.0 for CognitiveOS council reports.

Mandates `metadata_version: "1.0"` (Boardroom veto).
Provides a stdlib-only JSON Schema validator (no external deps required;
falls back to `jsonschema` if installed for richer errors).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

import yaml


METADATA_VERSION = "1.0"

COUNCILS = ("Boardroom", "Technical", "Creative", "Dev", "Strategic", "Logical")
TYPES = (
    "boardroom",
    "technical",
    "creative",
    "strategic",
    "dev_proposal",
    "request",
    "report",
)
STATUSES = ("draft", "proposed", "review", "approved", "rejected", "archived")


FRONTMATTER_SCHEMA: dict = {
    "type": "object",
    "required": ["council", "type", "status", "date", "owner", "metadata_version"],
    "properties": {
        "council": {"type": "string", "enum": list(COUNCILS)},
        "type": {"type": "string", "enum": list(TYPES)},
        "status": {"type": "string", "enum": list(STATUSES)},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "owner": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "metadata_version": {"type": "string", "const": METADATA_VERSION},
    },
    "additionalProperties": True,
}


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_markdown(content: str) -> tuple[dict, str]:
    """Split a markdown document into (frontmatter_dict, body_str).

    If no frontmatter block is found, returns ({}, content).
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    raw_fm, body = match.group(1), match.group(2)
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        return {}, content
    # normalise date objects → ISO string
    if isinstance(fm.get("date"), (date, datetime)):
        fm["date"] = fm["date"].strftime("%Y-%m-%d")
    return fm, body


def dump_frontmatter(fm: dict, body: str = "") -> str:
    """Render a (frontmatter, body) pair back into a markdown string."""
    yaml_str = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_str}\n---\n{body}" if body else f"---\n{yaml_str}\n---\n"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _stdlib_validate(fm: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    required: Iterable[str] = schema.get("required", [])
    for key in required:
        if key not in fm:
            errors.append(f"missing required field: '{key}'")
    props: dict = schema.get("properties", {})
    for key, value in fm.items():
        if key not in props:
            continue
        rule = props[key]
        if "const" in rule and value != rule["const"]:
            errors.append(f"'{key}' must equal {rule['const']!r}, got {value!r}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"'{key}' must be one of {rule['enum']}, got {value!r}")
        if rule.get("type") == "string":
            if not isinstance(value, str):
                errors.append(f"'{key}' must be a string, got {type(value).__name__}")
                continue
            if rule.get("minLength") and len(value) < rule["minLength"]:
                errors.append(f"'{key}' is shorter than minLength {rule['minLength']}")
            pattern = rule.get("pattern")
            if pattern and not re.match(pattern, value):
                errors.append(f"'{key}' does not match pattern {pattern!r}")
        if rule.get("type") == "array":
            if not isinstance(value, list):
                errors.append(f"'{key}' must be an array")
    return errors


def validate_frontmatter(fm: dict, schema: dict | None = None) -> tuple[bool, list[str]]:
    """Validate frontmatter against the schema.

    Returns (ok, errors). Uses `jsonschema` if importable, otherwise a small
    stdlib subset that covers the documented fields.
    """
    schema = schema or FRONTMATTER_SCHEMA
    try:  # pragma: no cover — depends on env
        import jsonschema  # type: ignore

        validator = jsonschema.Draft7Validator(schema)
        errs = [e.message for e in validator.iter_errors(fm)]
        return (len(errs) == 0), errs
    except ImportError:
        errs = _stdlib_validate(fm, schema)
        return (len(errs) == 0), errs
