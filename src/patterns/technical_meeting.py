"""Technical Meeting pattern: Draft → Expand → Refine → Synthesize pipeline."""
from src.patterns import PatternRequest
from src.council_runner import run_council


# Role sequence for technical meetings (Draft → Expand → Refine → Synthesize)
ROLES = [
    "drafting_architect",
    "creative_expansionist",
    "technical_critic",
]

SYNTHESIS_ROLE = "chief_technical_officer"


def execute(req: PatternRequest) -> str:
    """
    Execute a technical meeting pattern with sequential deliberation.
    
    This pattern follows a Draft → Expand → Refine → Synthesize pipeline:
    1. Drafting Architect creates initial technical blueprint
    2. Creative Expansionist expands on the draft with innovative solutions
    3. Technical Critic identifies problems and suggests improvements
    4. Chief Technical Officer synthesizes all input into a final solution
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The synthesized technical report as a string
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
    
    # Run the council with technical meeting configuration
    report = run_council(
        task_id=task_id,
        user_input=req.user_input,
        role_sequence=ROLES,
        synthesis_role=SYNTHESIS_ROLE,
        compass_weight=req.compass_weight,
        image_base64=req.image_base64,
        progress_callback=req.progress_callback,
        output_router=req.output_router,
        memory=memory,
    )
    
    return report