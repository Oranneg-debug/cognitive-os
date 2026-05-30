from dataclasses import dataclass
from typing import Optional, Callable


@dataclass(frozen=True)
class PatternRequest:
    """
    Request object passed to all pattern executors.
    
    Args:
        user_input: The original task request from the user
        image_base64: Optional base64-encoded image for vision tasks
        compass_weight: Weight of the Sovereign Compass (DEFAULT, MINIMUM, MAXIMUM, IGNORE)
        source_file_path: Optional path to source file for dev lifecycle patterns
        progress_callback: Optional callback for progress updates
        output_router: Optional OutputRouter instance for routing synthesis
        system_context: Optional system context (codebase knowledge) for enriched prompts
    """
    user_input: str
    image_base64: Optional[str] = None
    compass_weight: Optional[str] = None
    source_file_path: Optional[str] = None
    progress_callback: Optional[Callable] = None
    output_router: Optional['OutputRouter'] = None
    system_context: Optional[str] = None


# PATTERN_REGISTRY maps pattern names to their executor functions.
# Each executor accepts a PatternRequest and returns the synthesized report as a string.
from src.patterns.simple import execute as simple_execute
from src.patterns.standard import execute as standard_execute
from src.patterns.vision import execute as vision_execute
from src.patterns.technical_meeting import execute as technical_meeting_execute
from src.patterns.design_meeting import execute as design_meeting_execute
from src.patterns.sequential_boardroom import execute as sequential_boardroom_execute
from src.patterns.oracle_council import execute as oracle_council_execute
from src.patterns.nft_creation import execute as nft_creation_execute
from src.patterns.development_lifecycle import execute as development_lifecycle_execute
from src.patterns.alpha_council import execute as alpha_council_execute
from src.patterns.final_audit import execute as final_audit_execute

PATTERN_REGISTRY: dict[str, Callable[[PatternRequest], str]] = {
    "SIMPLE": simple_execute,
    "STANDARD": standard_execute,
    "VISION": vision_execute,
    "TECHNICAL_MEETING": technical_meeting_execute,
    "DESIGN_MEETING": design_meeting_execute,
    "SEQUENTIAL_BOARDROOM": sequential_boardroom_execute,
    "ORACLE_COUNCIL": oracle_council_execute,
    "NFT_CREATION": nft_creation_execute,
    "DEVELOPMENT_LIFECYCLE": development_lifecycle_execute,
    "ALPHA_COUNCIL": alpha_council_execute,
    "FINAL_AUDIT": final_audit_execute,
}
