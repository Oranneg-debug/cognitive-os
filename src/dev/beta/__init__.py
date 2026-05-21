"""
Tripartite File System Architecture — Beta Implementation
DEV-20260520-165800-7E5FA256

Modules:
    schema             — YAML v1.0 schema + JSON Schema validator
    routing            — Event-driven ingestion engine (idempotent)
    backlink_sentinel  — Drift detection for [[wikilinks]]
    access_control     — Tier-based read/write/approve enforcement
    metadata_index     — SQLite indexing of YAML frontmatter
"""

from .schema import (
    METADATA_VERSION,
    FRONTMATTER_SCHEMA,
    parse_markdown,
    validate_frontmatter,
    dump_frontmatter,
)
from .routing import IngestionEngine, sanitize_filename
from .backlink_sentinel import BacklinkSentinel
from .access_control import AccessControl
from .metadata_index import MetadataIndex

__all__ = [
    "METADATA_VERSION",
    "FRONTMATTER_SCHEMA",
    "parse_markdown",
    "validate_frontmatter",
    "dump_frontmatter",
    "IngestionEngine",
    "sanitize_filename",
    "BacklinkSentinel",
    "AccessControl",
    "MetadataIndex",
]
