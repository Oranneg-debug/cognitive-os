---
name: create_proposal
description: "Use this SOP when creating a new development proposal for the Cognitive OS Kanban board."
---

# Create Proposal SOP

**Purpose:** This SOP ensures that whenever an AI agent creates a new architectural, developmental, or system proposal, it uses the correct application routing rather than raw file-system writes. Raw file-system writes bypass the Kanban SQLite database, rendering the proposal invisible on the dashboard.

## Strict Rule
**NEVER use `create_file` or `insert_edit_into_file` to write a proposal directly to `dev/proposals/` or the Obsidian vault.**

## The Correct Procedure
To create a proposal, you MUST use the `run_in_terminal` tool to execute a Python script that calls `DevRouteManager.create_proposal()`. This guarantees the proposal is written to disk *and* inserted into the SQLite database.

### Command Template
Run the following python snippet via `run_in_terminal` in the `cognitive-os` directory:

```python
cd path/to/cognitive-os; python -c "
from src.dev_route import DevRouteManager

mgr = DevRouteManager()
res = mgr.proposal_writer.create_proposal(
    user_input='YOUR FULL PROPOSAL CONTENT OR DESCRIPTION HERE',
    origin='System Analyst' # or whatever agent you are
)
print('Proposal created:', res['proposal_id'])
"
```

### Important Notes on the Python Snippet:
1. `user_input` should contain the actual content you want evaluated.
2. `DevRouteManager` handles generating the correct ID, loading the template, writing the file, syncing to the vault, AND inserting it into the `kanban_store.db`.
3. If you need a specific prefix (e.g., `ARCH` or `NLST`), the `user_input` must start with a YAML frontmatter block that specifies the prefix, or you must rely on the router's automatic classification. (For explicit control, it is safer to ensure the YAML `type` or `prefix` hint is in the content).

By following this SOP, you guarantee the proposal immediately appears in the "Backlog" column on the dashboard without manual intervention.