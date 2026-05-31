"""Sequential Boardroom pattern: Independent opinions + memory file."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.patterns import PatternRequest

from src.council_runner import run_council


# Role sequence for sequential boardroom (independent opinions with memory)
# Per proposal ARCH-20260526-093000-7C4E2B91: 5 board members + chairman
ROLES = [
    "board_strategist",
    "board_specialist",
    "board_critic",
    "board_creative",
    "board_logical",
]

SYNTHESIS_ROLE = "board_chairman"


def execute(req: 'PatternRequest') -> str:
    """
    Execute a sequential boardroom pattern with independent opinions.
    
    This pattern follows the Sequential Boardroom specification:
    1. Each board member delivers an independent opinion without seeing others'
    2. Opinions are stored in memory files for later reference
    3. Brand Guard audits each opinion for coherence and strategy alignment
    4. Chairman synthesizes all independent opinions into a unified strategy
    
    Args:
        req: PatternRequest with user_input and optional parameters
        
    Returns:
        The synthesized boardroom report as a string
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
    
    # Run the council with sequential boardroom configuration
    report = run_council(
        task_id=task_id,
        user_input=req.user_input,
        role_sequence=ROLES,
        synthesis_role=SYNTHESIS_ROLE,
        compass_weight=req.compass_weight if req.compass_weight else "DEFAULT",
        image_base64=req.image_base64,
        progress_callback=req.progress_callback,
        output_router=req.output_router,
        memory=memory,
    )
    
    return report