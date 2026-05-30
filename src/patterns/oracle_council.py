"""Oracle Council pattern: Strategic oversight with MAXIMUM compass."""
from src.patterns import PatternRequest
from src.council_runner import run_council


# Role sequence for oracle council (strategic oversight)
ROLES = [
    "oracle_sage",
    "strategic_analyst",
    "visionary_seer",
]

SYNTHESIS_ROLE = "board_chairman"


def execute(req: PatternRequest) -> str:
    """
    Execute an Oracle Council pattern with MAXIMUM compass weight.
    
    This pattern is for high-stakes strategic decisions requiring maximum
    adherence to the Sovereign Compass:
    1. Oracle Sage provides divine insight
    2. Strategic Analyst interprets strategy alignment
    3. Visionary Seer forecasts long-term implications
    4. Chairman synthesizes with MAXIMUM compass weight (full strategic compliance)
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The synthesized oracle council report as a string
    """
    from src.council_runner import get_role_config
    from src.memory_file_system import MemoryFileManager
    from src.output_router import OutputRouter
    
    # Oracle Council requires MAXIMUM compass weight per proposal spec
    compass_weight = "MAXIMUM"
    
    # Get task ID (generate one if not provided in req)
    memory = MemoryFileManager()
    
    # Extract task ID from user_input hash for continuity
    import hashlib
    import datetime
    input_hash = hashlib.md5(req.user_input.encode()).hexdigest()[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"task_{timestamp}_{input_hash}"
    
    # Run the council with oracle council configuration (MAXIMUM compass)
    report = run_council(
        task_id=task_id,
        user_input=req.user_input,
        role_sequence=ROLES,
        synthesis_role=SYNTHESIS_ROLE,
        compass_weight=compass_weight,
        image_base64=req.image_base64,
        progress_callback=req.progress_callback,
        output_router=req.output_router,
        memory=memory,
    )
    
    return report