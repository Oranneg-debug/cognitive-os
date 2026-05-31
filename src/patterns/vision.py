"""Vision pattern: Vision-capable LLM for image-based tasks."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.patterns import PatternRequest


def execute(req: 'PatternRequest') -> str:
    """
    Execute a vision-capable pattern that processes both images and text.
    
    This pattern uses a vision-capable model to analyze images alongside
    text prompts. The image_base64 must be provided in the request.
    
    Args:
        req: PatternRequest with user_input and image_base64 required
        
    Returns:
        The LLM response as a string
        
    Raises:
        ValueError: If image_base64 is not provided in the request
    """
    from src.llm_client import llm
    from src.council_runner import get_role_config
    
    # Ensure image_base64 is provided for vision tasks
    if not req.image_base64:
        raise ValueError("Vision pattern requires image_base64 in PatternRequest")
    
    # Get the vision role config (vision-capable model)
    c = get_role_config("vision")
    
    # Generate response with image
    response = llm.generate_response(
        prompt=req.user_input,
        system_prompt=c.get("system_prompt"),
        model=c.get("model"),
        temperature=c.get("temperature", 0.7),
        top_p=c.get("top_p", 0.9),
        top_k=c.get("top_k", 40),
        repeat_penalty=c.get("repeat_penalty", 1.1),
        min_p=c.get("min_p", 0.0),
        max_tokens=c.get("max_tokens", 2048),
        context_window=c.get("context_window", 8192),
        gpu_layers=c.get("gpu_layers", -1),
        image_base64=req.image_base64,  # Image is passed here
        flash_attention=c.get("flash_attention"),
        cache_type_k=c.get("k_cache_quant"),
        cache_type_v=c.get("v_cache_quant"),
        gpu_offload_ratio=c.get("gpu_offload_ratio"),
        reasoning_enabled=c.get("reasoning_enabled"),
        batch_size=c.get("batch_size"),
    )
    
    return response