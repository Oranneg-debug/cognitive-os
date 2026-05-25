"""D8: Malformed routing-rules YAML refuses startup.

E3 contract: Pydantic schema validation at FastAPI startup so malformed rules
fail fast — we do NOT wait until the first synthesis arrives to discover a typo.

This test covers both YAML syntax errors and schema validation errors.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAMLError

from src.routing_rules_schema import load_routing_rules


@pytest.mark.parametrize(
    ("description", "yaml_content", "expected_exc"),
    [
        (
            "schema-invalid: missing colon after pattern field",
            """version: "1.0"
rules:
  - name: boardroom_proposal
    destination: proposals
    markers:
      - pattern #boardroom
""",
            ValidationError,
        ),
        (
            "syntax-broken: unclosed bracket",
            """version: "1.0"
rules: [
""",
            YAMLError,
        ),
    ],
)
def test_malformed_routing_rules_refuses_startup(
    tmp_path: Path, description: str, yaml_content: str, expected_exc: type[Exception]
) -> None:
    """Malformed routing-rules YAML raises at load time (E3 fail-fast)."""
    yaml_path = tmp_path / "routing_rules.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(expected_exc):
        load_routing_rules(yaml_path)