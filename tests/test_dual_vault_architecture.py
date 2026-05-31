"""
Test Dual-Vault Architecture (DEV-20260530-150000-D5E6F7A8).

Verifies that all modules correctly use COS_VAULT_* paths for system-side vault
while keeping backend-side project files separate.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path - use the correct cognitive-os directory
SCRIPT_DIR = Path(__file__).resolve().parent.parent
COS_DIR = SCRIPT_DIR / "cognitive-os"
sys.path.insert(0, str(COS_DIR / "src"))


# ════════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_vault_dirs():
    """Create temporary directories for vault and backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        backend_dir = tmp_path / "backend"
        vault_dir = tmp_path / "vault"
        backend_dir.mkdir()
        vault_dir.mkdir()
        yield {"backend": backend_dir, "vault": vault_dir}


@pytest.fixture
def mock_cos_vault_paths(temp_vault_dirs):
    """Mock COS_VAULT_* path constants."""
    with patch("src.paths.COS_VAULT_ROOT", temp_vault_dirs["vault"]) as _:
        with patch("src.paths.COS_VAULT_PROPOSALS_DIR", temp_vault_dirs["vault"] / "proposals") as _:
            with patch("src.paths.COS_VAULT_HANDOFFS_DIR", temp_vault_dirs["vault"] / "handoffs") as _:
                with patch("src.paths.COS_VAULT_DECISIONS_DIR", temp_vault_dirs["vault"] / "decisions") as _:
                    with patch("src.paths.COS_VAULT_RELEASES_DIR", temp_vault_dirs["vault"] / "releases") as _:
                        with patch("src.paths.COS_VAULT_COUNCIL_OUTPUTS", temp_vault_dirs["vault"] / "council_outputs") as _:
                            with patch("src.paths.COS_VAULT_MEMORY_LOGS", temp_vault_dirs["vault"] / "memory_logs") as _:
                                yield


# ════════════════════════════════════════════════════════════════════
#  B1: Import COS_VAULT_* paths correctly
# ════════════════════════════════════════════════════════════════════


def test_paths_imports_cos_vault_paths():
    """B1: src.paths exports COS_VAULT_* path constants."""
    from src import paths
    
    # All COS vault paths should exist and be Path objects or strings
    required_paths = [
        "COS_VAULT_ROOT",
        "COS_VAULT_PROPOSALS_DIR",
        "COS_VAULT_HANDOFFS_DIR",
        "COS_VAULT_DECISIONS_DIR",
        "COS_VAULT_RELEASES_DIR",
        "COS_VAULT_COUNCIL_OUTPUTS",
        "COS_VAULT_MEMORY_LOGS",
    ]
    
    for attr in required_paths:
        assert hasattr(paths, attr), f"Missing {attr} in src.paths"
        path_val = getattr(paths, attr)
        # Should be Path-like or string
        assert path_val is not None, f"{attr} is None"


def test_proposal_writer_uses_cos_vault_paths():
    """B1: proposal_writer.py imports and uses COS_VAULT_* paths."""
    from src import proposal_writer
    
    # Check the class exists
    assert hasattr(proposal_writer, "ProposalWriter")
    
    # Verify the source contains the expected imports
    import inspect
    source = inspect.getsource(proposal_writer)
    
    # Should import from paths
    assert "COS_VAULT" in source, "proposal_writer should reference COS_VAULT paths"


def test_handoff_writer_uses_cos_vault_paths():
    """B1: handoff_writer.py imports and uses COS_VAULT_* paths."""
    from src import handoff_writer
    
    # Check the class exists
    assert hasattr(handoff_writer, "HandoffWriter")
    
    # Verify the source contains the expected imports
    import inspect
    source = inspect.getsource(handoff_writer)
    
    # Should import from paths
    assert "COS_VAULT" in source, "handoff_writer should reference COS_VAULT paths"


def test_obsidian_writer_uses_cos_vault_paths():
    """B1: obsidian_writer.py imports and uses COS_VAULT_* paths."""
    from src import obsidian_writer
    
    # Check the class exists
    assert hasattr(obsidian_writer, "ObsidianWriter")
    
    # Verify the source contains the expected imports
    import inspect
    source = inspect.getsource(obsidian_writer)
    
    # Should import from paths
    assert "COS_VAULT" in source, "obsidian_writer should reference COS_VAULT paths"


def test_output_router_uses_cos_vault_paths():
    """B1: output_router.py imports and uses COS_VAULT_* paths."""
    from src import output_router
    
    # Verify the source contains the expected imports
    import inspect
    source = inspect.getsource(output_router)
    
    # Should import from paths
    assert "COS_VAULT" in source, "output_router should reference COS_VAULT paths"


# ════════════════════════════════════════════════════════════════════
#  B2: No 'Grand Nexus' literal outside paths.py
# ════════════════════════════════════════════════════════════════════


def test_no_vault_literals_outside_paths():
    """B2: No 'Grand Nexus' literal appears outside src/paths.py."""
    from pathlib import Path as LibPath
    
    # Get the cognitive-os root directory
    script_dir = Path(__file__).resolve().parent.parent
    ROOT = script_dir / "cognitive-os"
    SRC_DIR = ROOT / "src"
    
    # Get all Python files in src/
    py_files = list(SRC_DIR.rglob("*.py"))
    
    # Exclude paths.py itself
    py_files = [f for f in py_files if f.name != "paths.py"]
    
    needle = "Grand Nexus"
    hits = []
    
    for f in py_files:
        try:
            content = f.read_text(encoding="utf-8")
            if needle in content:
                hits.append(str(f.relative_to(ROOT)))
        except (OSError, UnicodeDecodeError):
            continue
    
    assert not hits, f"'Grand Nexus' found outside paths.py: {', '.join(hits[:5])}"


# ════════════════════════════════════════════════════════════════════
#  B3: COS_VAULT_PATH environment variable
# ════════════════════════════════════════════════════════════════════


def test_cos_vault_path_set_in_startup_scripts():
    """B3: start_api scripts set COS_VAULT_PATH environment variable."""
    import re
    
    # Get the cognitive-os root directory
    # Test file is at tests/test_dual_vault_architecture.py, so parent gives us tests/
    script_dir = Path(__file__).resolve().parent  # cognitive-os/tests
    ROOT = script_dir.parent  # cognitive-os - go up one level from tests/
    
    # Check PowerShell script
    ps1_file = ROOT / "start_api.ps1"
    assert ps1_file.exists(), f"start_api.ps1 not found at {ps1_file}"
    ps1_content = ps1_file.read_text(encoding="utf-8")
    assert "$env:COS_VAULT_PATH" in ps1_content, "start_api.ps1 should set $env:COS_VAULT_PATH"
    
    # Check batch script
    bat_file = ROOT / "start_api.bat"
    assert bat_file.exists(), f"start_api.bat not found at {bat_file}"
    bat_content = bat_file.read_text(encoding="utf-8")
    assert "COS_VAULT_PATH=" in bat_content, "start_api.bat should set COS_VAULT_PATH="


# ════════════════════════════════════════════════════════════════════
#  B4-B5: HandoffWriter dual-vault write test
# ════════════════════════════════════════════════════════════════════


def test_handoff_writer_writes_to_both_vaults(mock_cos_vault_paths, temp_vault_dirs):
    """B4: HandoffWriter writes to both backend and COS vault handoffs."""
    from src.handoff_writer import HandoffWriter
    
    # Setup
    writer = HandoffWriter()
    
    test_proposal_id = "DEV-20260530-150000-TEST001"
    test_council_report = """# Summary

This is a summary of the proposal.

## Difficulties

No specific difficulties.

## Implementation Tasks

- [ ] Task 1: Implement feature A
- [ ] Task 2: Test feature A
"""
    
    # Generate beta handoff
    result = writer.generate_beta_handoff(
        proposal_id=test_proposal_id,
        council_report=test_council_report,
        proposals_dir=str(temp_vault_dirs["vault"] / "proposals"),
        vault_proposals_dir=str(temp_vault_dirs["vault"] / "proposals")
    )
    
    # Verify returned paths
    assert "source_path" in result, "Result should have source_path"
    assert "vault_path" in result, "Result should have vault_path"
    
    # Verify backend file was written
    source_file = Path(result["source_path"])
    assert source_file.exists(), f"Source handoff not written to {source_file}"
    
    # Verify vault file was written
    vault_file = Path(result["vault_path"])
    assert vault_file.exists(), f"Vault handoff not written to {vault_file}"
    
    # Verify content is the same (both should contain the proposal ID)
    source_content = source_file.read_text(encoding="utf-8")
    vault_content = vault_file.read_text(encoding="utf-8")
    
    assert test_proposal_id in source_content, "Source handoff should contain proposal ID"
    assert test_proposal_id in vault_content, "Vault handoff should contain proposal ID"


# ════════════════════════════════════════════════════════════════════
#  B6: ObsidianWriter routing test
# ════════════════════════════════════════════════════════════════════


def test_obsidian_writer_routes_by_council_type(temp_vault_dirs):
    """B6: ObsidianWriter routes to appropriate vault based on council_type."""
    user_vault_dir = temp_vault_dirs["vault"] / "user_council"
    system_vault_dir = temp_vault_dirs["vault"] / "system_council"
    
    # We need to patch the module AFTER it's imported, since obsidian_writer
    # imports from src.paths at import time (from src.paths import VAULT_COUNCIL_OUTPUTS)
    # So we need to patch the actual module-level attributes of obsidian_writer
    
    # First, ensure clean state by re-importing paths module
    if "src.paths" in sys.modules:
        del sys.modules["src.paths"]
    
    with patch("src.paths.VAULT_COUNCIL_OUTPUTS", user_vault_dir):
        with patch("src.paths.COS_VAULT_COUNCIL_OUTPUTS", system_vault_dir):
            # Re-import obsidian_writer module (not just ObsidianWriter class)
            if "src.obsidian_writer" in sys.modules:
                del sys.modules["src.obsidian_writer"]
            
            from src import obsidian_writer as obs_module
            ObsidianWriter = obs_module.ObsidianWriter
            
            # Now manually set the paths on the module before instantiating
            obs_module.VAULT_COUNCIL_OUTPUTS = str(user_vault_dir)
            obs_module.COS_VAULT_COUNCIL_OUTPUTS = str(system_vault_dir)
            
            # Create instances - they should now use our patched paths
            writer_user = ObsidianWriter(council_type="user_side")
            assert str(user_vault_dir) in str(writer_user.vault_path), \
                f"User-side council should route to {user_vault_dir}, got {writer_user.vault_path}"
            
            writer_system = ObsidianWriter(council_type="system_side")
            assert str(system_vault_dir) in str(writer_system.vault_path), \
                f"System-side council should route to {system_vault_dir}, got {writer_system.vault_path}"


def test_obsidian_writer_default_routes_to_system(temp_vault_dirs):
    """B6: ObsidianWriter defaults to system-side vault when no council_type specified."""
    from src.obsidian_writer import ObsidianWriter
    
    system_vault_dir = temp_vault_dirs["vault"] / "system_council"
    
    # Patch at import time
    with patch("src.obsidian_writer.COS_VAULT_COUNCIL_OUTPUTS", system_vault_dir):
        writer = ObsidianWriter()  # No council_type - defaults to system_side
        assert str(system_vault_dir) in str(writer.vault_path), \
            f"Default should route to system-side vault {system_vault_dir}, got {writer.vault_path}"