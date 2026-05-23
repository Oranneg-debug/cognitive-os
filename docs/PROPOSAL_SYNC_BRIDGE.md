# 🔄 Proposal Sync Bridge

**Status**: ✅ Implemented (v1.0.0)  
**Last Updated**: May 21, 2026  
**Module**: `src.proposal_sync`

---

## Overview

The **Proposal Sync Bridge** ensures that development proposals remain in sync between the backend (`cognitive-os/dev/proposals/`) and the Obsidian vault mirror (`1. P - Seedlings/dev/proposals/`).

### Why This Matters

Previously, proposals created via `/dev` or `#dev` were saved to both locations, but over time:
- Files could become out of sync
- Missing files in vault weren't detected
- Conflicts between backend and vault weren't identified
- No health monitoring for the sync process

The Proposal Sync Bridge fixes this gap with automated health checks and one-way synchronization.

---

## Features

### 1. One-Way Sync (Backend → Vault)
- Backend is the source of truth
- Vault is the mirror (for Obsidian integration)
- Preserves file metadata (timestamps, etc.)

### 2. Health Monitoring
Three-level status system:
- 🟢 **Green**: All proposals in sync
- 🟡 **Yellow**: Some proposals missing in vault
- 🔴 **Red**: Conflicts detected or other issues

### 3. Conflict Detection
Identifies files that exist in both locations but have different content using SHA256 hashing.

### 4. Content-Addressable Hashing
- Uses SHA256 for reliable change detection
- Detects even minor content modifications
- Efficient comparison without full file reads

### 5. Sync History
- Tracks all sync operations
- Stores last 100 sync records
- Includes duration, file counts, and errors

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ProposalSyncManager                      │
├─────────────────────────────────────────────────────────────┤
│  • check_sync_status()  → SyncStatus                        │
│  • sync_backend_to_vault() → SyncResult                     │
│  • detect_conflicts()   → List[Dict]                        │
│  • get_missing_files()  → List[str]                         │
│  • force_sync()         → SyncResult                        │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
       ┌──────────┐    ┌──────────┐    ┌──────────┐
       │ Backend  │    │  Hash    │    │  Vault   │
       │ Proposals│    │  Engine  │    │ Proposals│
       │  (src)   │    │ SHA256   │    │  (mirror)│
       └──────────┘    └──────────┘    └──────────┘
```

---

## API Reference

### `ProposalSyncManager` Class

```python
from src.proposal_sync import ProposalSyncManager

sync_manager = ProposalSyncManager()
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| proposals_dir | Path | `dev/proposals/` | Backend proposals directory |
| vault_dir | Path | `vault/dev/proposals/` | Vault proposals directory |
| history_file | Path | `.sync_history.json` | Sync operation history file |

#### Methods

##### `check_sync_status() → SyncStatus`

Check current sync status and determine health.

**Returns:**
```python
SyncStatus(
    health="green",           # "green", "yellow", or "red"
    backend_count=5,          # Number of files in backend
    vault_count=5,            # Number of files in vault
    missing_in_vault=[],      # List of filenames missing in vault
    conflicts=[],             # List of conflict dictionaries
    last_sync="2026-05-21T...",  # ISO timestamp of last sync
    last_sync_duration_ms=123  # Duration in milliseconds
)
```

##### `sync_backend_to_vault() → SyncResult`

Perform one-way sync from backend to vault.

**Returns:**
```python
SyncResult(
    success=True,             # Whether sync completed without errors
    files_synced=5,           # Number of files copied
    files_skipped=0,          # Number of files skipped
    files_conflicted=0,       # Number of conflicts detected
    errors=[]                 # List of error messages
)
```

##### `detect_conflicts() → List[Dict]`

Detect files with conflicts between backend and vault.

**Returns:**
```python
[
    {
        "filename": "DEV-20260520-194846-8CC9917F_PROPOSAL.md",
        "backend_hash": "a1b2c3...",
        "vault_hash": "d4e5f6...",
        "backend_modified": "2026-05-20T19:48:46.000000",
        "vault_modified": "2026-05-20T20:03:13.000000"
    }
]
```

##### `get_missing_files() → List[str]`

Get list of files missing in vault (exist in backend only).

**Returns:**
```python
["DEV-20260521-163101-DDC79BB3_PROPOSAL.md"]
```

##### `force_sync() → SyncResult`

Alias for `sync_backend_to_vault()`.

##### `get_file_content(filename: str, location: str = "backend") → Optional[str]`

Get content of a file from specified location.

**Parameters:**
- `filename`: Name of the file
- `location`: "backend" or "vault"

**Returns:**
File content as string, or None if not found

##### `get_sync_history(limit: int = 10) → List[Dict]`

Get sync operation history.

**Parameters:**
- `limit`: Maximum number of records to return

**Returns:**
```python
[
    {
        "timestamp": "2026-05-21T17:00:00.000000",
        "duration_ms": 123,
        "files_synced": 5,
        "files_skipped": 0,
        "errors": []
    }
]
```

---

## API Endpoints

### GET `/api/sync/status`

Get current sync status with health indicator.

**Response:**
```json
{
  "health": "green",
  "backend_count": 5,
  "vault_count": 5,
  "missing_in_vault": [],
  "conflicts": [],
  "last_sync": "2026-05-21T17:00:00.000000",
  "last_sync_duration_ms": 123
}
```

### GET `/api/sync/proposals`

List all proposals with their sync status.

**Response:**
```json
{
  "proposals": [
    {
      "filename": "DEV-20260520-194846-8CC9917F_PROPOSAL.md",
      "proposal_id": "DEV-20260520-194846-8CC9917F",
      "in_backend": true,
      "in_vault": true,
      "backend_hash": "a1b2c3...",
      "vault_hash": "a1b2c3...",
      "size": 3749,
      "modified_at": "2026-05-20T19:48:46.000000"
    }
  ],
  "count": 1
}
```

### GET `/api/sync/missing`

Get list of proposals missing in vault.

**Response:**
```json
{
  "missing": ["DEV-20260521-163101-DDC79BB3_PROPOSAL.md"],
  "count": 1
}
```

### GET `/api/sync/conflicts`

Get list of files with conflicts.

**Response:**
```json
{
  "conflicts": [],
  "count": 0
}
```

### POST `/api/sync/force-sync`

Force a sync from backend to vault.

**Response (Success):**
```json
{
  "status": "success",
  "message": "Synced 5 files",
  "result": {
    "success": true,
    "files_synced": 5,
    "files_skipped": 0,
    "files_conflicted": 0,
    "errors": []
  }
}
```

### GET `/api/sync/history`

Get sync operation history.

**Query Parameters:**
- `limit`: Maximum number of records (default: 10)

**Response:**
```json
{
  "history": [
    {
      "timestamp": "2026-05-21T17:00:00.000000",
      "duration_ms": 123,
      "files_synced": 5,
      "files_skipped": 0,
      "errors": []
    }
  ],
  "count": 1
}
```

---

## Integration Examples

### 1. DevRouteManager Integration

The `DevRouteManager` automatically triggers a sync check after creating a proposal:

```python
from src.dev_route import DevRouteManager

dev_manager = DevRouteManager()

# Create proposal → auto-triggers sync check
proposal_data = dev_manager.create_proposal(
    user_input="Add new feature X",
    origin="telegram"
)

# Check sync status manually
sync_status = dev_manager._trigger_sync_check()
```

### 2. KanbanProcessor Integration

The `KanbanProcessor` includes sync checks and manual sync capability:

```python
from src.kanban_processor import KanbanProcessor

kanban = KanbanProcessor()

# Trigger sync check (called automatically on card updates)
sync_status = kanban._trigger_sync_check()

# Manual sync
result = kanban.sync_proposals()
```

### 3. Orchestrator Startup Check

The `Orchestrator` performs a startup health check:

```python
from src.orchestrator import Orchestrator

orchestrator = Orchestrator()
# Startup message includes sync status:
# 🔍 Performing startup proposal sync health check...
#    Sync Status: 🟢 GREEN
#    Backend Proposals: 5
#    Vault Proposals: 5
```

### 4. Direct API Usage

```python
from src.proposal_sync import ProposalSyncManager

# Initialize
sync_manager = ProposalSyncManager()

# Check status
status = sync_manager.check_sync_status()
print(f"Health: {status.health}")

# Sync if needed
if status.health in ["yellow", "red"]:
    result = sync_manager.sync_backend_to_vault()
    print(f"Synced {result.files_synced} files")
```

---

## Health Status Logic

```python
def determine_health(missing_count, conflict_count):
    if missing_count == 0 and conflict_count == 0:
        return "green"  # All in sync
    elif missing_count > 0 and conflict_count == 0:
        return "yellow"  # Missing files but no conflicts
    else:
        return "red"  # Has conflicts or other issues
```

### Status Meanings

| Status | Meaning | Action Required |
|---|---|---|
| 🟢 Green | All proposals in sync | None |
| 🟡 Yellow | Some proposals missing in vault | Run `force-sync` |
| 🔴 Red | Conflicts detected | Investigate and resolve |

---

## Troubleshooting

### Issue: "Sync manager not available"

**Cause:** The `proposal_sync.py` module is missing or not importable.

**Solution:**
```bash
# Verify the file exists
ls src/proposal_sync.py

# Check Python path
python -c "import sys; print(sys.path)"
```

### Issue: "Vault proposals directory does NOT exist"

**Cause:** The vault path is incorrect or the directory hasn't been created.

**Solution:**
```python
from src.proposal_sync import ProposalSyncManager, VAULT_PROPOSALS_DIR

print(f"Expected vault path: {VAULT_PROPOSALS_DIR}")

# Create the directory if it doesn't exist
import os
os.makedirs(VAULT_PROPOSALS_DIR, exist_ok=True)
```

### Issue: "Permission denied" during sync

**Cause:** Insufficient permissions to write to vault directory.

**Solution:**
```bash
# Check permissions (Windows)
icacls "E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus\1. P - Seedlings\dev\proposals"

# Ensure your user has write permissions
```

### Issue: High sync duration (>500ms)

**Cause:** Large number of proposal files or slow disk I/O.

**Solution:**
```python
# Check number of files
import os
backend_count = len(os.listdir("dev/proposals"))
vault_count = len(os.listdir(vault_proposals_dir))
print(f"Backend: {backend_count}, Vault: {vault_count}")

# Consider archiving old proposals
```

---

## Performance Considerations

### File Count vs Performance

| Files | Expected Sync Time | Recommendation |
|---|---|---|
| < 10 | < 100ms | No optimization needed |
| 10-50 | 100-300ms | Monitor performance |
| 50-100 | 300-500ms | Consider archiving old proposals |
| > 100 | > 500ms | Implement archival strategy |

### Optimization Tips

1. **Archive Old Proposals**: Move completed proposals to `dev/releases/`
2. **Use Content Hashing**: Only read file headers for proposal ID extraction
3. **Batch Operations**: Sync multiple files in a single operation
4. **Monitor History**: Check sync duration over time with `get_sync_history()`

---

## Testing

### Unit Tests

```python
import unittest
from src.proposal_sync import ProposalSyncManager, ProposalFile, SyncStatus

class TestProposalSyncManager(unittest.TestCase):
    def setUp(self):
        self.sync_manager = ProposalSyncManager()
    
    def test_check_sync_status_returns_valid_status(self):
        status = self.sync_manager.check_sync_status()
        self.assertIn(status.health, ["green", "yellow", "red"])
        self.assertIsInstance(status.backend_count, int)
        self.assertIsInstance(status.vault_count, int)
    
    def test_sync_backend_to_vault(self):
        result = self.sync_manager.sync_backend_to_vault()
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.files_synced, 0)

if __name__ == '__main__':
    unittest.main()
```

### Manual Testing

```bash
# Check sync status
curl http://localhost:5000/api/sync/status | jq .

# Force sync
curl -X POST http://localhost:5000/api/sync/force-sync | jq .

# Check history
curl "http://localhost:5000/api/sync/history?limit=5" | jq .
```

---

## Future Enhancements

### Phase 2 Features

- [ ] Two-way sync with conflict resolution
- [ ] Incremental sync (only changed files)
- [ ] Sync scheduling (cron-based)
- [ ] Webhook notifications on sync events
- [ ] Dashboard widget for real-time sync status
- [ ] Automatic archival of completed proposals

### Phase 3 Features

- [ ] Git-based versioning for proposals
- [ ] Diff view for conflicts
- [ ] Manual conflict resolution UI
- [ ] Sync analytics and insights
- [ ] Multi-vault support

---

## Changelog

### v1.0.0 (May 21, 2026)

- ✅ Initial implementation
- ✅ One-way sync (backend → vault)
- ✅ Health monitoring (green/yellow/red)
- ✅ Conflict detection with SHA256 hashing
- ✅ API endpoints for sync operations
- ✅ DevRouteManager integration
- ✅ KanbanProcessor integration
- ✅ Orchestrator startup health check
- ✅ Sync history tracking

---

## See Also

- [README.md](../README.md) - Main documentation
- [src/dev_route.py](../src/dev_route.py) - Development lifecycle management
- [src/kanban_processor.py](../src/kanban_processor.py) - Kanban automation
- [src/orchestrator.py](../src/orchestrator.py) - Core orchestration logic

---

**Last Updated**: May 21, 2026  
**Maintainer**: Antigravity Development Team
