"""Final Audit pattern module for Finalized phase quality gate.

This pattern implements the Finalized transition gate with:
- final_scribe: Generates comprehensive release notes
- dev_final_audit: Outputs binary verdict (APPROVED/REJECTED)
"""
from src.patterns import PatternRequest
from src.council_runner import run_council


# Role sequence for Final Audit (Scribe → Final Auditor)
FINAL_AUDIT_ROLES = [
    "final_scribe",
]

SYNTHESIS_ROLE = "dev_final_audit"


def execute(req: PatternRequest) -> str:
    """
    Execute the Final Audit pattern for Finalized phase quality gate.
    
    This pattern validates documentation and code state before moving to
    the Finalized column. The scribe generates release notes, then the
    final auditor produces a binary APPROVED/REJECTED verdict.
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The synthesized final audit report with verdict as a string
    """
    from src.council_runner import get_role_config
    from src.memory_file_system import MemoryFileManager
    from src.output_router import OutputRouter
    
    # Generate task ID for this council session
    import hashlib
    import datetime
    input_hash = hashlib.md5(req.user_input.encode()).hexdigest()[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"task_{timestamp}_{input_hash}"
    
    # Run the final audit council
    report = run_council(
        task_id=task_id,
        user_input=req.user_input,
        role_sequence=FINAL_AUDIT_ROLES,
        synthesis_role=SYNTHESIS_ROLE,
        compass_weight=req.compass_weight,
        image_base64=req.image_base64,
        progress_callback=req.progress_callback,
        output_router=req.output_router,
        memory=MemoryFileManager(),
    )
    
    return report