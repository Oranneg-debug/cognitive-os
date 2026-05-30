"""Alpha Council pattern module for Alpha Polish phase validation.

This pattern implements the Alpha transition gate with specialized roles:
- alpha_ux_specialist: UI/UX friction, accessibility, visual feedback
- alpha_perf_specialist: Algorithmic bottlenecks, latency, memory leaks
- alpha_critic: Edge cases, race conditions, security vulnerabilities
- dev_alpha_polish: Synthesis role that produces the final JSON blueprint
"""
from src.patterns import PatternRequest
from src.council_runner import run_council


# Role sequence for Alpha Council (UX → Perf → Critic → Synthesis)
ALPHA_ROLES = [
    "alpha_ux_specialist",
    "alpha_perf_specialist",
    "alpha_critic",
]

SYNTHESIS_ROLE = "dev_alpha_polish"


def execute(req: PatternRequest) -> str:
    """
    Execute the Alpha Council pattern for Alpha Polish phase validation.
    
    This pattern validates UI/UX, performance, and security before moving to
    the Alpha Polish column. Each role focuses on its specialty, then the
    synthesis role produces a definitive JSON blueprint.
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The synthesized alpha council report as a string
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
    
    # Run the alpha council with specialized roles
    report = run_council(
        task_id=task_id,
        user_input=req.user_input,
        role_sequence=ALPHA_ROLES,
        synthesis_role=SYNTHESIS_ROLE,
        compass_weight=req.compass_weight,
        image_base64=req.image_base64,
        progress_callback=req.progress_callback,
        output_router=req.output_router,
        memory=MemoryFileManager(),
    )
    
    return report