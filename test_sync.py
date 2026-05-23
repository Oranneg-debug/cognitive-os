#!/usr/bin/env python
"""Test script for Proposal Sync Bridge"""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.proposal_sync import ProposalSyncManager

def test_sync_manager():
    """Test the ProposalSyncManager functionality"""
    
    print("=" * 60)
    print("TESTING PROPOSAL SYNC BRIDGE")
    print("=" * 60)
    
    # Initialize sync manager
    print("\n1. Initializing ProposalSyncManager...")
    try:
        psm = ProposalSyncManager()
        print("   ✓ ProposalSyncManager initialized successfully")
    except Exception as e:
        print(f"   ✗ Failed to initialize: {e}")
        return
    
    # Check sync status
    print("\n2. Checking sync status...")
    try:
        status = psm.check_sync_status()
        print(f"   ✓ Status retrieved")
        
        # Convert to dict if it's a custom object
        if hasattr(status, '__dict__'):
            status_dict = status.__dict__
        else:
            status_dict = status
            
        print(f"   - Synchronized: {status_dict.get('synchronized', 'Unknown')}")
        print(f"   - Backend proposals: {status_dict.get('backend_proposals', 0)}")
        print(f"   - Vault proposals: {status_dict.get('vault_proposals', 0)}")
        print(f"   - Conflicts: {len(status_dict.get('conflicts', []))}")
        
        if status_dict.get('conflicts'):
            print("\n   Conflicts detected:")
            for conflict in status_dict['conflicts'][:3]:  # Show first 3
                print(f"     - {conflict}")
                
    except Exception as e:
        print(f"   ✗ Failed to check status: {e}")
    
    # Test sync operation
    print("\n3. Testing sync operation...")
    try:
        result = psm.sync_backend_to_vault()
        print(f"   ✓ Sync completed")
        
        # Convert result to dict if needed
        if hasattr(result, '__dict__'):
            result_dict = result.__dict__
        else:
            result_dict = result
            
        print(f"   - Synced: {result_dict.get('synced', 0)} proposals")
        print(f"   - Errors: {result_dict.get('errors', 0)}")
        
        if result_dict.get('details'):
            print("\n   Sync details:")
            for detail in result_dict['details'][:3]:  # Show first 3
                print(f"     - {detail}")
                
    except Exception as e:
        print(f"   ✗ Failed to sync: {e}")
    
    # Check directories
    print("\n4. Checking directory structure...")
    backend_dir = Path("E:/Antigravity/cognitive-os/dev/proposals")
    vault_dir = Path("E:/Oranneg/CloudStation/Documents/Obsidian/Grand Nexus/dev/proposals")
    
    print(f"   Backend dir exists: {backend_dir.exists()}")
    print(f"   Vault dir exists: {vault_dir.exists()}")
    
    if backend_dir.exists():
        backend_files = list(backend_dir.glob("*.md"))
        print(f"   Backend proposals: {len(backend_files)}")
        if backend_files:
            print("   Sample backend files:")
            for f in backend_files[:3]:
                print(f"     - {f.name}")
    
    if vault_dir.exists():
        vault_files = list(vault_dir.glob("*.md"))
        print(f"   Vault proposals: {len(vault_files)}")
        if vault_files:
            print("   Sample vault files:")
            for f in vault_files[:3]:
                print(f"     - {f.name}")
    
    # Test hash generation
    print("\n5. Testing hash generation...")
    test_file = "E:/Antigravity/cognitive-os/src/proposal_sync.py"
    if Path(test_file).exists():
        try:
            file_hash = psm._get_file_hash(test_file)
            print(f"   ✓ Hash generated: {file_hash[:16]}...")
        except Exception as e:
            print(f"   ✗ Failed to generate hash: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_sync_manager()