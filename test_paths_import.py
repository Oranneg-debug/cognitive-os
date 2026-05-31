#!/usr/bin/env python
"""Test script to verify paths module imports correctly."""
import sys
sys.path.insert(0, '.')

try:
    from src.paths import (
        COS_VAULT_ROOT,
        _ensure_cos_vault_structure,
        cross_vault_link,
    )
    print(f'COS_VAULT_ROOT: {COS_VAULT_ROOT}')
    
    # Test directory structure creation
    _ensure_cos_vault_structure()
    print('Directory structure created successfully')
    
    # Test cross-vault link generation
    link = cross_vault_link("Grand Nexus", "notes/test.md")
    print(f'Cross-vault link: {link}')
    
    print('\nAll paths tests passed!')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)