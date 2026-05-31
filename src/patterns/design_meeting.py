"""Design Meeting pattern: Design-focused orchestration."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.patterns import PatternRequest

from src.council_runner import run_council


# Role sequence for design meetings (Draft → Expand → Refine → Synthesize with design focus)
ROLES = [
    "design_junior",
    "creative_expansionist",
    "design_critic",
]

SYNTHESIS_ROLE = "design_senior"


def execute(req: 'PatternRequest') -> str:
    """
    Execute a design meeting pattern with sequential deliberation.
    
    This pattern follows a Draft → Expand → Refine → Synthesize pipeline
    specifically for creative design tasks:
    1. Junior Designer creates initial design concepts
    2. Creative Expansionist expands on the design with creative elements
    3. Design Critic identifies design issues and suggests improvements
    4. Senior Designer synthesizes all input into a final design solution
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The synthesized design report as a string
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
    
    # Run the council with design meeting configuration
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
        inject_system_context=False,  # Design meetings are for art/tattoo, not codebase knowledge
    )
    
    return report