# Contributing to Cognitive OS

Welcome! This guide explains how to contribute to the Cognitive OS codebase, with a focus on adding new orchestration patterns.

---

## 🏗️ Architecture Overview

Cognitive OS implements a **modular council dispatch system** for orchestrating AI agent deliberations. The architecture is designed around these core principles:

### Module Structure

```
src/
├── orchestrator.py          # Lightweight dispatcher (<250 LoC)
├── council_runner.py        # Reusable moderator/agent/synthesis loop
├── llm_client.py           # LLM inference + VRAM lifecycle
├── sentry_router.py        # Pattern classification
└── patterns/               # Per-pattern strategy modules
    ├── __init__.py         # PATTERN_REGISTRY
    ├── simple.py
    ├── standard.py
    ├── vision.py
    ├── technical_meeting.py
    ├── design_meeting.py
    ├── sequential_boardroom.py
    ├── oracle_council.py
    ├── nft_creation.py
    ├── development_lifecycle.py
    └── ...
```

### Core Components

| Component | Responsibility |
|-----------|----------------|
| `orchestrator.py` | Maps patterns to executors via `PATTERN_REGISTRY` |
| `council_runner.py` | Centralized moderator → agent loop → synthesis pipeline |
| `llm_client.py` | LLM inference + VRAM management (`flush_vram`, `restore_default`) |
| `sentry_router.py` | Classifies input → pattern name |
| `patterns/*.py` | Pattern-specific strategy modules |

---

## 🧩 Adding a New Pattern

To add a new orchestration pattern:

### 1. Create the Pattern Module

Create a new file in `src/patterns/` (e.g., `my_pattern.py`):

```python
from dataclasses import dataclass
from typing import Optional, Callable
from src.council_runner import run_council
from src.output_router import OutputRouter


def execute(req) -> str:
    """
    Execute the pattern.
    
    Args:
        req: PatternRequest dataclass with user_input, image_base64, etc.
        
    Returns:
        The synthesized report as a markdown string
    """
    # Define roles and synthesis role for this pattern
    role_sequence = ["role1", "role2", "role3"]
    synthesis_role = "synthesis_role"
    
    # Generate unique task ID (use proposal ID or timestamp)
    import time
    task_id = f"PATTERN_{int(time.time() * 1000)}"
    
    # Call the shared council runner
    report = run_council(
        task_id=task_id,
        user_input=req.user_input,
        role_sequence=role_sequence,
        synthesis_role=synthesis_role,
        compass_weight=req.compass_weight,
        image_base64=req.image_base64,
        progress_callback=req.progress_callback,
        output_router=req.output_router,
    )
    
    return report
```

### 2. Register the Pattern

Add the import and registration to `src/patterns/__init__.py`:

```python
# Add import (keep alphabetically sorted)
from src.patterns.my_pattern import execute as my_pattern_execute

# Add to PATTERN_REGISTRY (keep alphabetically sorted)
PATTERN_REGISTRY: dict[str, Callable[[PatternRequest], str]] = {
    # ... existing patterns ...
    "MY_PATTERN": my_pattern_execute,
}
```

### 3. Register the Pattern in SentryRouter

Add the pattern classification to `src/sentry_router.py`:

```python
# In the patterns dict:
patterns: ClassVar[dict[str, PatternInfo]] = {
    # ... existing patterns ...
    "MY_PATTERN": PatternInfo(
        prefix="/my_pattern",
        complexity="medium",  # or "simple", "complex"
        description="Short description of what this pattern does"
    ),
}
```

---

## 🧪 Testing Guidelines

### Unit Tests

Add tests in `tests/` following the existing structure:

```python
# tests/test_my_pattern.py
import pytest
from src.patterns.my_pattern import execute
from src.patterns import PatternRequest


def test_my_pattern_executes():
    """Test that my_pattern executes without errors."""
    req = PatternRequest(user_input="Test input")
    result = execute(req)
    
    assert isinstance(result, str)
    assert len(result) > 0
```

### Registry Completeness

The `tests/test_pattern_registry.py` test verifies that every pattern in `SentryRouter` has a registered executor. When adding a new pattern:

1. Ensure it's in `PATTERN_REGISTRY`
2. Ensure it's in `SentryRouter.patterns`
3. Run: `pytest tests/test_pattern_registry.py`

### Running All Tests

```bash
cd cognitive-os
python -m pytest
```

---

## 🔧 Code Organization Rules

### Pattern Module Requirements

- Each pattern file must export a single `execute(req: PatternRequest) -> str` function
- Use `run_council()` for multi-agent councils (preserves error handling)
- Keep role sequences and synthesis roles in the pattern module, not in `orchestrator.py`

### Orchestrator Constraints

The `orchestrator.py` must:
- Stay under 250 lines of code
- Only contain dispatch logic via `PATTERN_REGISTRY`
- Not define any pattern-specific strategies

### VRAM Management

- Use `llm.flush_vram()` and `llm.restore_default()` from `llm_client`
- Never shell to `lms` CLI from orchestrator or patterns
- Call `eject_all_models()` between sequential councils

---

## 📝 Pull Request Checklist

Before submitting a PR:

- [ ] New pattern module created in `src/patterns/`
- [ ] Pattern registered in `PATTERN_REGISTRY`
- [ ] Pattern classified in `SentryRouter.patterns`
- [ ] Unit test added for the new pattern
- [ ] `pytest` passes (no regressions)
- [ ] Orchestrator remains < 250 lines (if modified)

---

## 🚨 Breaking Changes

If your change affects the public API:

1. Update this guide
2. Document migration steps in the PR description
3. Update the version number per SemVer

---

*Last updated: 2026-05-29*