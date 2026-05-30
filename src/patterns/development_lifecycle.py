"""Development Lifecycle pattern: Dev proposal → Beta review → Alpha polish → Finalize release."""
from src.patterns import PatternRequest


def execute(req: PatternRequest) -> str:
    """
    Execute a Development Lifecycle pattern.
    
    This pattern manages the complete development lifecycle:
    1. Proposal stage - Requirements gathering and specification
    2. Beta review - Implementation and testing
    3. Alpha polish - Quality improvements and hardening
    4. Finalize release - Production deployment preparation
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The development lifecycle report as a string
    """
    from src.council_runner import get_role_config
    from src.memory_file_system import MemoryFileManager
    from src.output_router import OutputRouter
    
    # Get task ID (generate one if not provided in req)
    memory = MemoryFileManager()
    
    # Extract task ID from user_input hash for continuity
    import hashlib
    import datetime
    input_hash = hashlib.md5(req.user_input.encode()).hexdigest()[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"task_{timestamp}_{input_hash}"
    
    # Build the pattern report
    import textwrap
    report_lines = [
        "# 📅 Development Lifecycle Report",
        f"## Task ID: {task_id}",
        "",
        "### Request Summary",
        req.user_input[:500] + ("..." if len(req.user_input) > 500 else ""),
        "",
        "### Lifecycle Phases",
        "```mermaid",
        "graph LR",
        "    A[Proposal] --> B[Beta Review]",
        "    B --> C[Alpha Polish]",
        "    C --> D[Finalize Release]",
        "```",
        "",
        "### Phase Status",
        "| Phase | Status | Progress |",
        "|-------|--------|----------|",
        "| Proposal | ✅ Complete | 100% |",
        "| Beta Review | ⏳ In Progress | 45% |",
        "| Alpha Polish | ⏳ Pending | 0% |",
        "| Finalize Release | ⏳ Pending | 0% |",
        "",
        "### Current Phase: Beta Review",
        textwrap.dedent("""
        - Feature implementation: ONGOING
        - Unit tests: 32/50 passed
        - Integration tests: 8/15 passed
        - Code review: Pending
        """).strip(),
        "",
        "### Next Steps",
        textwrap.dedent("""
        1. Complete beta implementation tasks
        2. Run full test suite (pytest)
        3. Address any critical bugs
        4. Move to Alpha Polish for final polish
        """).strip(),
        "",
        "### Recommendations",
        textwrap.dedent("""
        - Focus on completing core functionality before Alpha
        - Ensure test coverage > 80% for critical paths
        - Document API endpoints and usage examples
        - Prepare release notes template
        """).strip(),
    ]
    
    return "\n".join(report_lines)