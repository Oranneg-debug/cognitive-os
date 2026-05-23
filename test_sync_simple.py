#!/usr/bin/env python
"""Simple sync test"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.proposal_sync import ProposalSyncManager

# Initialize and sync
psm = ProposalSyncManager()

print("Performing sync...")
result = psm.sync_backend_to_vault()

# Convert to dict using to_dict() method
if hasattr(result, 'to_dict'):
    result_dict = result.to_dict()
else:
    result_dict = result.__dict__ if hasattr(result, '__dict__') else result

print(f"Success: {result_dict.get('success', False)}")
print(f"Synced: {result_dict.get('files_synced', 0)} proposals")
print(f"Skipped: {result_dict.get('files_skipped', 0)}")
print(f"Conflicted: {result_dict.get('files_conflicted', 0)}")
print(f"Errors: {result_dict.get('errors', [])}")

# Check status after sync
status = psm.check_sync_status()
if hasattr(status, 'to_dict'):
    status_dict = status.to_dict()
else:
    status_dict = status.__dict__ if hasattr(status, '__dict__') else status

print(f"\nStatus after sync:")
print(f"  Health: {status_dict.get('health', 'unknown')}")
print(f"  Backend count: {status_dict.get('backend_count', 0)}")
print(f"  Vault count: {status_dict.get('vault_count', 0)}")
print(f"  Missing in vault: {len(status_dict.get('missing_in_vault', []))}")
print(f"  Conflicts: {len(status_dict.get('conflicts', []))}")