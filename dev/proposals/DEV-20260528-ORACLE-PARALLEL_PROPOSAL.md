# DEV Proposal: Parallel LLM-Council for Oracle Execution

## Status: Backlog
**Date**: 2026-05-28
**Initiator**: Council Expert

## Context
Currently, the **Oracle Council** (`execute_oracle_council` in `src/orchestrator.py`) leverages the sequential `_execute_orchestrated_meeting` flow (Agent A -> Agent B -> Agent C). To adhere to the Karpathy [LLM-Council](https://github.com/karpathy/llm-council) standard for truth-seeking, we need to transition this to a **parallel/independent execution model**. 

In this pattern, three independent agents evaluate the user's prompt blindly, and a final Judge synthesizes the independent answers to form the truth.

> **Note**: I have already updated `docs/MODEL_ORCHESTRATION.md` and `docs/SYSTEM_ARCHITECTURE.md` to reflect this new parallel architecture.

## Proposed Changes

### 1. Update Configuration (`dev/master_config.md`)
Add the following roles to the `roles:` block in `master_config.md`:
*   `oracle_member_1` (e.g., `qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max`)
*   `oracle_member_2` (e.g., `deepseek-r1-distill-qwen-32b-uncensored`)
*   `oracle_member_3` (e.g., `gemma-4-31b-it`)
*   `oracle_judge` (e.g., `hermes-4-70b`)

*Ensure each member prompt requests independent analysis and confidence scores in JSON, and the judge prompt requests synthesis.*

### 2. Implement Parallel Generation (`src/orchestrator.py` or new `src/patterns/oracle_council.py`)
Replace the current `execute_oracle_council` method logic:
1.  **Do not use** `_execute_orchestrated_meeting`.
2.  Use `asyncio.gather()` or a `ThreadPoolExecutor` to prompt `oracle_member_1`, `oracle_member_2`, and `oracle_member_3` in parallel using `llm.generate_response()` against the user's original query.
3.  Gather the JSON outputs from all three members.
4.  Construct a new context prompt containing all three independent responses.
5.  Invoke the `oracle_judge` to evaluate the answers and return the final synthesis.
6.  Save the final judgment to `council_memory/`.

## Success Criteria
*   The Oracle Council executes three LLM requests in parallel rather than sequentially.
*   The final response is synthesized by the Judge.
*   The system passes `alpha_polish_check.py` gates.
*   The updated `master_config.md` successfully loads the new roles without errors.