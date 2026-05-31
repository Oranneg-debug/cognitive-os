import json
import logging
import sys
from typing import Optional, Callable

from src.llm_client import llm
from src.memory_file_system import MemoryFileManager
from src.output_router import OutputRouter

from src.system_context_builder import build_universal_context


def get_role_config(role_key: str) -> dict:
    """Get the full configuration for a specific role from the master config."""
    from dotenv import load_dotenv
    load_dotenv()
    
    import os
    import re
    import yaml
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'dev', 'master_config.md')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract the YAML block
    yaml_match = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
    if not yaml_match:
        raise ValueError(f"Could not find a YAML code block in master_config.md")
    
    yaml_content = yaml_match.group(1)
    config = yaml.safe_load(yaml_content)
    
    roles = config.get("roles", {})
    if role_key in roles:
        # Inherit base model parameters
        role_info = roles[role_key]
        model_name = role_info.get("model")
        if model_name:
            models = config.get("models", {})
            base_model_config = models.get(model_name, {})
            # Role-specific params override model defaults
            return {**base_model_config, **role_info}
    raise ValueError(f"Role '{role_key}' not found in master_config.md")


def _load_sovereign_compass() -> str:
    """Load the Sovereign Compass from environment path."""
    import os
    
    compass_path = os.getenv("SOVEREIGN_COMPASS_PATH")
    if compass_path and os.path.exists(compass_path):
        try:
            with open(compass_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"⚠️ Failed to read Sovereign Compass at {compass_path}: {e}")
    return ""


def _inject_compass(system_prompt: str, weight_override: str = None, role_config: dict = None) -> str:
    """Inject the Sovereign Compass into a system prompt."""
    compass = _load_sovereign_compass()
    
    if not compass:
        return system_prompt
    
    weight = weight_override
    if role_config and (not weight or weight == "DEFAULT"):
        weight = role_config.get("compass_weight", "IGNORE")
    
    if weight in ["IGNORE", "NONE", None]:
        return system_prompt
        
    return f"{system_prompt}\n\n### THE DARK MAESTRO SOVEREIGN COMPASS:\n{compass}\n\n### YOUR ADHERENCE DIRECTIVE:\n{weight}"


def _inject_system_context(system_prompt: str) -> str:
    """Inject system context (codebase knowledge) into a system prompt."""
    try:
        system_context = build_universal_context()
        if system_context:
            return f"{system_prompt}\n\n{system_context}"
    except Exception as e:
        logging.warning(f"Context injection failed: {e}")
    
    return system_prompt


def _extract_json(text: str) -> dict:
    """Extract JSON from text response."""
    try:
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"error": "No JSON found", "raw": text}
    except Exception as e:
        return {"error": str(e), "raw": text}


def _format_meeting_history(task_id: str, memory: MemoryFileManager) -> str:
    """
    Retrieves all opinions from memory and formats them as readable text history.
    Includes Brand Guard approval status for each agent output.
    """
    opinions = memory.get_all_opinions(task_id)
    
    history_lines = []
    history_lines.append("=" * 80)
    history_lines.append("MEETING HISTORY SO FAR - Sequential Deliberation Context")
    history_lines.append("=" * 80)
    history_lines.append("")
    
    for opinion in opinions:
        role = opinion.get("role", "unknown")
        model = opinion.get("model_name", "unknown_model")
        timestamp = opinion.get("timestamp_completed", "")
        
        # Skip moderator framing for the main discussion history
        if role == "moderator":
            mod_data = _extract_json(opinion.get("opinion", "{}"))
            history_lines.append(f"[MODERATOR FRAMING - {timestamp}]")
            history_lines.append(f"Next Role: {mod_data.get('next_role', 'N/A')}")
            history_lines.append(f"Transition Reason: {mod_data.get('transition_reason', 'N/A')}")
            history_lines.append("")
            continue
        
        # Skip Brand Guard roles (they audit, don't deliberate)
        if role.startswith("brand_guard_"):
            bg_data = _extract_json(opinion.get("opinion", "{}"))
            original_role = role.replace("brand_guard_", "")
            approved = bg_data.get("approved", False)
            history_lines.append(f"[BRAND GUARD AUDIT for {original_role}]")
            history_lines.append(f"Status: {'APPROVED ✅' if approved else 'REJECTED ❌'}")
            history_lines.append(f"Reasoning: {bg_data.get('reasoning', 'N/A')}")
            history_lines.append(f"Veto Points: {bg_data.get('veto_points', [])}")
            history_lines.append("")
            continue
        
        # Format the main agent opinion
        history_lines.append(f"[{role.upper()} ({model}) - {timestamp}]")
        
        opinion_text = opinion.get("opinion", "")
        try:
            opinion_data = _extract_json(opinion_text)
            # Convert to readable format
            for key, value in opinion_data.items():
                if isinstance(value, list):
                    history_lines.append(f"{key}:")
                    for item in value:
                        history_lines.append(f"  - {item}")
                elif isinstance(value, dict):
                    history_lines.append(f"{key}:")
                    for k2, v2 in value.items():
                        history_lines.append(f"    {k2}: {v2}")
                else:
                    history_lines.append(f"{key}: {value}")
        except:
            history_lines.append(opinion_text)
        
        history_lines.append("")
        history_lines.append("-" * 60)
        history_lines.append("")
    
    history_lines.append("=" * 80)
    history_lines.append("END OF MEETING HISTORY")
    history_lines.append("=" * 80)
    
    return "\n".join(history_lines)


def run_council(
    task_id: str,
    user_input: str,
    role_sequence: list[str],
    synthesis_role: str,
    *,
    compass_weight: Optional[str] = None,
    image_base64: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    output_router: Optional[OutputRouter] = None,
    memory: Optional[MemoryFileManager] = None,
    inject_system_context: bool = True,
    brand_guard_enabled: bool = True,
    moderator_enabled: bool = True,
) -> str:
    """
    Production-grade meeting execution with JSON handoffs, sequential context passing, and Brand Guard audits.
    
    This function is the extracted moderator loop from orchestrator._execute_orchestrated_meeting.
    It preserves all error handling including try/except around synthesis for silent-drop recovery.
    
    Args:
        task_id: Unique identifier for this council session
        user_input: The original task request
        role_sequence: List of role names in deliberation order
        synthesis_role: The role responsible for final synthesis
        compass_weight: Weight of the Sovereign Compass (DEFAULT, MINIMUM, MAXIMUM, IGNORE)
        image_base64: Optional base64-encoded image for vision tasks
        progress_callback: Optional callback for progress updates
        output_router: Optional OutputRouter for routing synthesis output
        memory: Optional MemoryFileManager instance (creates new if not provided)
        inject_system_context: Whether to inject system context (codebase knowledge) into prompts.
            Set to False for non-technical patterns like design_meeting (art/tattoo).
    
    Returns:
        The final synthesized report as a markdown string
    """
    # Initialize memory manager if not provided
    if memory is None:
        memory = MemoryFileManager()
    
    memory.init_task(task_id, user_input, f"ORCHESTRATED_{synthesis_role.upper()}")
    
    msg_start = f"[START] Starting Orchestrated Meeting: {task_id}"
    print(msg_start)
    if progress_callback:
        progress_callback(msg_start)
    
    llm.eject_all_models()
    print(f"[COUNCIL] All models ejected, starting council with {len(role_sequence)} roles + synthesis")
    
    # 1. Moderator Framing
    if moderator_enabled:
        mod_config = get_role_config("moderator")
        if mod_config.get("enabled", True):
            msg_mod = "[MODERATOR] Moderator is framing the discussion..."
            print(f"--> {msg_mod}")
            if progress_callback:
                progress_callback(msg_mod)
            
            try:
                mod_response = llm.generate_response(
                    prompt=f"Task: {user_input}\nFrame the meeting and assign the first speaker from: {', '.join(role_sequence)}",
                    system_prompt=mod_config["system_prompt"],
                    model=mod_config["model"],
                    temperature=mod_config.get("temperature", 0.4),
                    max_tokens=mod_config.get("max_tokens", 512),
                    gpu_layers=mod_config.get("gpu_layers", 0),
                    top_p=mod_config.get("top_p", 0.9),
                    top_k=mod_config.get("top_k", 40),
                    repeat_penalty=mod_config.get("repeat_penalty", 1.1),
                    min_p=mod_config.get("min_p", 0.0),
                    context_window=mod_config.get("context_window", 8192),
                    flash_attention=mod_config.get("flash_attention"),
                    cache_type_k=mod_config.get("k_cache_quant"),
                    cache_type_v=mod_config.get("v_cache_quant"),
                    gpu_offload_ratio=mod_config.get("gpu_offload_ratio"),
                    reasoning_enabled=mod_config.get("reasoning_enabled"),
                    batch_size=mod_config.get("batch_size"),
                )
                mod_data = _extract_json(mod_response)
                memory.save_opinion(task_id, "moderator", mod_config["model"], json.dumps(mod_data))
                print(f"[MODERATOR] Framing complete, next role: {mod_data.get('next_role', 'N/A')}")
            except Exception as e:
                print(f"[MODERATOR] ERROR during framing: {e}")
                import traceback
                traceback.print_exc()
                # Continue without moderator - not fatal
        else:
            print("[MODERATOR] Skipped (disabled in config).")
    else:
        print("[MODERATOR] Skipped (moderator_enabled=False).")
    
    # Initialize meeting history for context
    meeting_history = _format_meeting_history(task_id, memory)

    # 2. Sequential Deliberation with Brand Guard Audit and Sequential Context
    for idx, role_key in enumerate(role_sequence):
        c = get_role_config(role_key)
        if not c.get("enabled", True):
            msg_skip = f"[AGENT] {role_key.upper()} is disabled. Skipping..."
            print(f"--> {msg_skip}")
            if progress_callback:
                progress_callback(msg_skip)
            continue

        msg_role = f"[AGENT] {role_key.upper()} is deliberating..."
        print(f"--> {msg_role}")
        if progress_callback:
            progress_callback(msg_role)

        # Build sequential prompt with meeting history
        sequential_context = f"""
You are the {role_key.upper()} agent in a sequential deliberation.
The original task is: "{user_input}"

BELOW IS THE MEETING HISTORY SO FAR - CRITICAL CONTEXT:
{meeting_history}

INSTRUCTIONS:
1. Review ALL previous opinions in the meeting history above
2. If previous agents agreed on a point, BUILD upon it with your expertise
3. If previous agents identified problems or conflicts, ADDRESS them in your analysis
4. Provide your unique perspective as {role_key} - expand, refine, or challenge previous thoughts
5. If Brand Guard previously rejected something, pivot and correct the trajectory
6. Output your analysis in the specified JSON format for your role
"""

        # Agent Turn
        base_system_prompt = c.get("system_prompt", "")
        if inject_system_context:
            base_system_prompt = _inject_system_context(base_system_prompt)
        final_system_prompt = _inject_compass(base_system_prompt, role_config=c)
        
        print(f"[AGENT] Loading model: {c['model']} for role: {role_key}")
        try:
            agent_opinion = llm.generate_response(
                prompt=f"Context: {user_input}\nDeliberate on your specific area.\n\n{sequential_context}",
                system_prompt=final_system_prompt,
                model=c["model"],
                temperature=c.get("temperature", 0.7),
                top_p=c.get("top_p", 0.9),
                top_k=c.get("top_k", 40),
                repeat_penalty=c.get("repeat_penalty", 1.1),
                max_tokens=c.get("max_tokens", 8192),
                context_window=c.get("context_window", 32768),
                gpu_layers=c.get("gpu_layers", -1),
                image_base64=image_base64 if idx == 0 else None,  # Only first agent sees image if provided
                min_p=c.get("min_p", 0.0),
                flash_attention=c.get("flash_attention"),
                cache_type_k=c.get("k_cache_quant"),
                cache_type_v=c.get("v_cache_quant"),
                gpu_offload_ratio=c.get("gpu_offload_ratio"),
                reasoning_enabled=c.get("reasoning_enabled"),
                batch_size=c.get("batch_size"),
            )
            print(f"[AGENT] {role_key} completed deliberation")
        except Exception as e:
            print(f"[AGENT] ERROR in {role_key}: {e}")
            import traceback
            traceback.print_exc()
            # Continue to next role - don't fail entire council
            continue
            
        parsed_agent = _extract_json(agent_opinion)
        memory.save_opinion(task_id, role_key, c["model"], json.dumps(parsed_agent))

        # Update meeting history for next agent
        meeting_history = _format_meeting_history(task_id, memory)

        # Brand Guard Audit — skipped when compass already injected
        # (compass is injected into every agent's system prompt by
        # _inject_compass above; brand guard after every agent adds
        # unnecessary load/unload cycles in the dev pipeline).
        if brand_guard_enabled:
            bg_config = get_role_config("brand_guard")
            if bg_config.get("enabled", True):
                msg_bg = f"[BRAND_GUARD] Brand Guard is auditing {role_key.upper()}..."
                if progress_callback:
                    progress_callback(msg_bg)

                bg_response = llm.generate_response(
                    prompt=f"Audit this output: {json.dumps(parsed_agent)}",
                    system_prompt=bg_config["system_prompt"],
                    model=bg_config["model"],
                    temperature=bg_config.get("temperature", 0.1),
                    max_tokens=bg_config.get("max_tokens", 512),
                    gpu_layers=bg_config.get("gpu_layers", 0),
                    top_p=bg_config.get("top_p", 0.95),
                    top_k=bg_config.get("top_k", 65),
                    repeat_penalty=bg_config.get("repeat_penalty", 1.1),
                    min_p=bg_config.get("min_p", 0.0),
                    context_window=bg_config.get("context_window", 131072),
                    flash_attention=bg_config.get("flash_attention"),
                    cache_type_k=bg_config.get("k_cache_quant"),
                    cache_type_v=bg_config.get("v_cache_quant"),
                    gpu_offload_ratio=bg_config.get("gpu_offload_ratio"),
                    reasoning_enabled=bg_config.get("reasoning_enabled"),
                    batch_size=bg_config.get("batch_size"),
                )
                bg_data = _extract_json(bg_response)
                memory.save_opinion(task_id, f"brand_guard_{role_key}", bg_config["model"], json.dumps(bg_data))

                if not bg_data.get("approved", True):
                    msg_veto = f"[VETO] BRAND VETO on {role_key}: {bg_data.get('reasoning', 'No reason provided')}"
                    print(msg_veto)
                    if progress_callback:
                        progress_callback(msg_veto)
            else:
                msg_bg_skip = f"[BRAND_GUARD] Audit skipped for {role_key.upper()} (disabled)."
                print(f"--> {msg_bg_skip}")
                if progress_callback:
                    progress_callback(msg_bg_skip)

        llm.eject_all_models()

    # 3. Final Synthesis (Chairman/Overseer)
    msg_synth = f"[SYNTHESIS] {synthesis_role.upper()} is performing the final audit and synthesis..."
    if progress_callback:
        progress_callback(msg_synth)

    # Get formatted meeting history for the synthesis step
    final_meeting_history = _format_meeting_history(task_id, memory)

    opinions = memory.get_all_opinions(task_id)
    c = get_role_config(synthesis_role)

    if c.get("enabled", True):
        # Synthesis call is the load-bearing step of every orchestration —
        # if it raises, we MUST still persist an audit trail (the upstream
        # bug was a silent-drop: exceptions bubbled up, the caller's
        # finally-block archived the task with status=completed, and
        # oversight_analysis stayed empty with no log line to explain why).
        print(f"[SYNTHESIS] Loading model: {c['model']} for synthesis role: {synthesis_role}")
        try:
            base_system_prompt = c.get("system_prompt", "")
            if inject_system_context:
                base_system_prompt = _inject_system_context(base_system_prompt)
            final_system_prompt = _inject_compass(base_system_prompt, role_config=c)
            final_opinion = llm.generate_response(
                prompt=f"""Synthesize the meeting history and provide the definitive blueprint.

ORIGINAL TASK:
{user_input}

FINAL MEETING HISTORY (with sequential context):
{final_meeting_history}

INSTRUCTIONS:
- Analyze all the deliberations above
- Identify consensus points, conflicts, and critical insights
- Weigh Brand Guard approvals/rejections
- Generate a definitive, actionable output that reconciles all perspectives

Output your final blueprint in the specified JSON format for your role.""",
                system_prompt=final_system_prompt,
                model=c["model"],
                temperature=c.get("temperature", 0.7),
                top_p=c.get("top_p", 0.9),
                top_k=c.get("top_k", 40),
                repeat_penalty=c.get("repeat_penalty", 1.1),
                max_tokens=c.get("max_tokens", 8192),
                context_window=c.get("context_window", 32768),
                gpu_layers=c.get("gpu_layers", -1),
                min_p=c.get("min_p", 0.0),
                flash_attention=c.get("flash_attention"),
                cache_type_k=c.get("k_cache_quant"),
                cache_type_v=c.get("v_cache_quant"),
                gpu_offload_ratio=c.get("gpu_offload_ratio"),
                reasoning_enabled=c.get("reasoning_enabled"),
                batch_size=c.get("batch_size"),
            )
            print(f"[SYNTHESIS] {synthesis_role} completed synthesis")
        except Exception as synth_exc:
            import traceback
            tb = traceback.format_exc()
            final_opinion = json.dumps({
                "error": f"Synthesis call raised: {synth_exc!r}",
                "synthesis_role": synthesis_role,
                "traceback": tb,
            })
            err_msg = (
                f"[SYNTHESIS] ❌ {synthesis_role.upper()} raised "
                f"{type(synth_exc).__name__}: {synth_exc}"
            )
            print(err_msg)
            print(tb, file=sys.stderr)
            if progress_callback:
                progress_callback(err_msg)
        memory.save_oversight_analysis(task_id, final_opinion, system_prompt=final_system_prompt)
    else:
        final_opinion = '{"error": "Synthesis role disabled in config."}'
        print(f"[SYNTHESIS] {synthesis_role.upper()} skipped (disabled).")
        # Persist the disabled state explicitly so it's auditable rather
        # than indistinguishable from a hard-crashed run.
        memory.save_oversight_analysis(task_id, final_opinion, system_prompt="")

    # 4. Scribe Synthesis
    msg_scribe = "[SCRIBE] Scribe is generating the master report..."
    if progress_callback:
        progress_callback(msg_scribe)

    s_config = get_role_config("scribe")
    if s_config.get("enabled", True):
        report = llm.generate_response(
            prompt=f"Original Task: {user_input}\nFinal Verdict: {final_opinion}\n\nMeeting History:\n{final_meeting_history}\n\nGenerate a master markdown report that captures the full deliberation process and the definitive outcome.",
            system_prompt=s_config["system_prompt"],
            model=s_config["model"],
            temperature=s_config.get("temperature", 0.3),
            max_tokens=s_config.get("max_tokens", 4096),
            gpu_layers=s_config.get("gpu_layers", -1),
            top_p=s_config.get("top_p", 0.9),
            top_k=s_config.get("top_k", 40),
            repeat_penalty=s_config.get("repeat_penalty", 1.1),
            min_p=s_config.get("min_p", 0.0),
            context_window=s_config.get("context_window", 8192),
            flash_attention=s_config.get("flash_attention"),
            cache_type_k=s_config.get("k_cache_quant"),
            cache_type_v=s_config.get("v_cache_quant"),
            gpu_offload_ratio=s_config.get("gpu_offload_ratio"),
            reasoning_enabled=s_config.get("reasoning_enabled"),
            batch_size=s_config.get("batch_size"),
        )
    else:
        report = f"Scribe role is disabled. Raw final verdict:\n{final_opinion}"
        print("[SCRIBE] Skipped (disabled).")

    memory.complete_task(task_id)

    # A2: Route the synthesis via OutputRouter if injected
    if output_router is not None:
        decision = output_router.route(report)
        return output_router.apply(report, decision)  # apply(content, decision)

    return report