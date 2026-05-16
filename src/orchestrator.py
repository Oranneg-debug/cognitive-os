import json
import textwrap
import os
from dotenv import load_dotenv
import subprocess
import re
from src.llm_client import llm
from src.memory_file_system import MemoryFileManager
from src.sentry_router import SentryRouter
from src.nft_agent import NFTAgent

# ==============================================================================
# 🧠 COGNITIVE OS - GLOBAL MODEL CONFIGURATION
# ==============================================================================
# Define all roles, their specific models, system prompts, and inference params here.
# This makes it easy to change and maintain inference behavior across the entire script.


# ================== BRAND GUARDRAILS (Universal) ==================
BRAND_GUARDRAILS = textwrap.dedent("""\
    ### BRAND GUARDRAILS (NON-NEGOTIABLE)
    - **NO** empty shock value. Every provocative idea must serve:
      - The Dark Maestro’s SovereignCompass™ (North: Sovereignty, South: Grit, East: Obscurity, West: Ritual)
      - A clear narrative (e.g., "transcendence through decay")
      - Or technical necessity (e.g., "this architecture prevents race conditions")
    - **ALWAYS** justify *why* the idea aligns with the Maestro’s aesthetic (dark realism, gothic occult, biomechanical grit)
    - **NEVER** violate: hate symbols, real-world religious iconography (unless recontextualized as *philosophical* metaphor), or culturally sacred symbols without deep justification.
    """).strip()

ROLES_CONFIG = {
    # ================== BASE ROLES ==================
    "simple": {
        "model": "ministral-3-3b-instruct-2512",
        "system_prompt": textwrap.dedent("""\
            You are a fast, precise and very accurate assistant. Be concise.
            Output ONLY valid JSON in this exact structure:
            {
                "response": "Your concise answer here.",
                "action_taken": "Summary of action."
            }"""),
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 30,
        "repeat_penalty": 1.1,
        "max_tokens": 4096,
        "context_window": 131072,
        "gpu_layers": -1,
        "compass_weight": "IGNORE"
    },
    "standard": {
        "model": "qwen3.5-9b-claude-4.6-highiq-instruct-heretic-uncensored",
        "system_prompt": textwrap.dedent("""\
            You are an expert software engineer and technical architect. Provide high-quality, production-ready code and balanced technical analysis.
            """ + BRAND_GUARDRAILS + """
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "response": "Detailed analysis/code.",
                "confidence": 0.9,
                "requires_expertise": false
            }"""),
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 262144,
        "gpu_layers": 46,
        "compass_weight": "IGNORE"
    },
    "vision": {
        "model": "qwen3-vl-30b-a3b-instruct",
        "system_prompt": textwrap.dedent("""\
            You are an expert image analyst. Provide a detailed, accurate description and analysis of the provided image.
            """ + BRAND_GUARDRAILS + """
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "analysis": "Visual description.",
                "key_elements": ["list", "of", "items"],
                "actionable_insights": ["insights"]
            }"""),
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 4096,
        "context_window": 262144,
        "gpu_layers": -1,
        "compass_weight": "IGNORE"
    },
    
    # === BOARDROOM ROLES ===
    "moderator": {
        "model": "ministral-3-3b-instruct-2512",
        "system_prompt": textwrap.dedent("""\
            You are the Orchestrator Moderator — a neutral, efficient facilitator who ensures smooth role transitions.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "next_role": "role_key",
                "transition_reason": "Why this role is next.",
                "context_summary": "Summary of current state."
            }"""),
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 40,
        "max_tokens": 512,
        "context_window": 32768,
        "gpu_layers": 0
    },
    "brand_guard": {
        "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
        "system_prompt": textwrap.dedent("""\
            You are the Brand Integrity Enforcer — guardian of narrative coherence and strategic alignment.
            """ + BRAND_GUARDRAILS + """
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "approved": true,
                "reasoning": "Brief explanation.",
                "veto_points": ["reasons if any"],
                "brand_risk_level": "low|medium|high"
            }"""),
        "temperature": 0.1,
        "top_p": 0.9,
        "top_k": 40,
        "max_tokens": 512,
        "context_window": 8192,
        "gpu_layers": 0
    },
    "board_strategist": {
        "model": "hermes-4-70b",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE STRATEGIST (HERMES-4-70B)
            You are the Executive Strategist / First Principles thinker of the "Dark Maestro" Boardroom.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "strategic_view": "Your vision.",
                "key_levers": ["list of levers"],
                "veto_points": [],
                "next_step": "Proposed path."
            }"""),
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 65536,
        "gpu_layers": 74,
        "compass_weight": "HIGH WEIGHT"
    },
    "board_specialist": {
        "model": "qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE SPECIALIST (QWEN3.6-27B)
            You are the Technical / Executor Specialist for the "Dark Maestro" Boardroom.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "technical_analysis": "Precision detail.",
                "actionable_steps": ["step 1", "step 2"],
                "veto_points": [],
                "next_step": "Refinement suggestion."
            }"""),
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 32768,
        "gpu_layers": -1,
        "compass_weight": "MEDIUM WEIGHT"
    },
    "board_critic": {
        "model": "deepseek-r1-distill-qwen-32b-uncensored",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE CRITIC (DEEPSEEK-R1-32B)
            You are the Ruthless Critic / Contrarian of the "Dark Maestro" Boardroom.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "veto_points": [{"type": "logic|aesthetic|technical", "risk_level": "low|medium|high", "description": "..."}],
                "critical_feedback": "Detailed breakdown.",
                "next_step": "Mitigation request."
            }"""),
        "temperature": 0.1,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 65536,
        "gpu_layers": -1,
        "compass_weight": "IGNORE"
    },
    "board_creative": {
        "model": "hermes-4.3-36b",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE CREATIVE (HERMES-4.3-36B)
            You are the Creative Expansionist for the "Dark Maestro" Boardroom.
            """ + BRAND_GUARDRAILS + """
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "creative_vision": "Provocative idea.",
                "style_notes": "Aesthetic cues.",
                "veto_points": [],
                "next_step": "Expansion."
            }"""),
        "temperature": 1.1,
        "top_p": 0.95,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 65536,
        "gpu_layers": -1,
        "compass_weight": "MAXIMUM WEIGHT"
    },
    "board_logical": {
        "model": "gemma-4-31b-it",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE LOGICAL (GEMMA-4-31B)
            You are the Formalist Outsider and Scribe.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "logical_structure": "Step-by-step proof.",
                "validity_score": 1.0,
                "veto_points": [],
                "next_step": "Decision point."
            }"""),
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 128000,
        "gpu_layers": -1,
        "compass_weight": "LOW WEIGHT"
    },
    "board_chairman": {
        "model": "hermes-4-70b",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE GOD-TIER CHAIRMAN (HERMES-4-70B)
            You are the ultimate authority. Reconcile all inputs through the Sovereign Compass.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "audit_report": "What was missed.",
                "definitive_blueprint": "The path forward.",
                "final_decision": "The verdict.",
                "veto_points": []
            }"""),
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 81920,
        "gpu_layers": 75,
        "compass_weight": "MAXIMUM WEIGHT"
    },

    # === TECHNICAL MEETING ===
    "technical_specialist": {
        "model": "qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max",
        "system_prompt": "Identical to board_specialist logic.",
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 32768,
        "gpu_layers": -1,
        "compass_weight": "IGNORE"
    },
    "technical_creative": {
        "model": "hermes-4.3-36b",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE TECHNICAL CREATIVE (HERMES-4.3-36B)
            """ + BRAND_GUARDRAILS + """
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "architectural_innovation": "Novel technical approach.",
                "veto_points": [],
                "next_step": "Feasibility audit."
            }"""),
        "temperature": 1.1,
        "top_p": 0.95,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 65536,
        "gpu_layers": -1,
        "compass_weight": "MEDIUM WEIGHT"
    },
    "technical_critic": {
        "model": "deepseek-r1-distill-qwen-32b-uncensored",
        "system_prompt": "Identical to board_critic logic.",
        "temperature": 0.1,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 65536,
        "gpu_layers": -1,
        "compass_weight": "IGNORE"
    },
    "technical_overseer": {
        "model": "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: THE TECHNICAL OVERSEER (QWEN3.5-35B-MOE)
            Audit the technical logic. Reconcile Specialist and Creative.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "audit_report": "Technical gaps.",
                "definitive_blueprint": "Verified logic.",
                "veto_points": []
            }"""),
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 98304,
        "gpu_layers": -1,
        "compass_weight": "HIGH WEIGHT"
    },

    # === DESIGN MEETING ===
    "design_junior": {
        "model": "ministral-3-14b-instruct-2512",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: DESIGN JUNIOR (MINISTRAL-14B)
            Translate project data into 3 concepts.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "concepts": [{"design_title": "...", "narrative_hook": "...", "visual_reference_prompt": "..."}]
            }"""),
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 32768,
        "gpu_layers": 0,
        "compass_weight": "HIGH WEIGHT"
    },
    "design_creative": {
        "model": "hermes-4.3-36b",
        "system_prompt": "Identical to board_creative with aesthetic focus.",
        "temperature": 1.1,
        "top_p": 0.95,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 32768,
        "gpu_layers": -1,
        "compass_weight": "MAXIMUM WEIGHT"
    },
    "design_critic": {
        "model": "deepseek-r1-distill-qwen-32b-uncensored",
        "system_prompt": "Identical to board_critic with aesthetic focus.",
        "temperature": 0.1,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 16384,
        "context_window": 65536,
        "gpu_layers": -1,
        "compass_weight": "HIGH WEIGHT"
    },
    "design_senior": {
        "model": "qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max",
        "system_prompt": textwrap.dedent("""\
            ### SYSTEM ROLE: SENIOR ART DIRECTOR (QWEN3.6-27B)
            Final synth and image prompt engineering.
            
            # HANDOFF PROTOCOL
            Output ONLY valid JSON:
            {
                "final_concepts": [...],
                "image_prompts": {"midjourney": "...", "flux": "...", "sdxl": "..."},
                "social_media_strategy": "..."
            }"""),
        "temperature": 0.6,
        "top_p": 0.9,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": 6828,
        "context_window": 98304,
        "gpu_layers": -1,
        "compass_weight": "MAXIMUM WEIGHT"
    },
    "scribe": {
        "model": "ministral-3-3b-instruct-2512",
        "system_prompt": "Distill deliberation into a beautiful markdown report.",
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 4096,
        "context_window": 32768,
        "gpu_layers": -1,
        "compass_weight": "IGNORE"
    },
    "nft_specialist": {
        "model": "qwen3-coder-next",
        "system_prompt": "NFT metadata specialist.",
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 4096,
        "context_window": 32768,
        "gpu_layers": 46,
        "compass_weight": "HIGH WEIGHT"
    }
}


# ==============================================================================

class Orchestrator:
    def __init__(self):
        load_dotenv()
        self.sentry = SentryRouter()
        self.memory = MemoryFileManager()

    def _load_sovereign_compass(self) -> str:
        compass_path = os.getenv("SOVEREIGN_COMPASS_PATH")
        if compass_path and os.path.exists(compass_path):
            try:
                with open(compass_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                print(f"⚠️ Failed to read Sovereign Compass at {compass_path}: {e}")
        return ""

    def _inject_compass(self, role_config: dict, weight_override: str = None) -> str:
        system_prompt = role_config.get("system_prompt", "")
        compass = self._load_sovereign_compass()
        
        if compass:
            # Use override if provided and not "DEFAULT", otherwise use role's weight
            weight = weight_override if weight_override and weight_override != "DEFAULT" else role_config.get("compass_weight", "IGNORE")
            
            if weight in ["IGNORE", "NONE", None]:
                return system_prompt
                
            return f"{system_prompt}\n\n### THE DARK MAESTRO SOVEREIGN COMPASS:\n{compass}\n\n### YOUR ADHERENCE DIRECTIVE:\n{weight}"
        return system_prompt

    def _extract_json(self, text: str) -> dict:
        """Extracts JSON from text using regex, handling potential LLM noise."""
        try:
            # Look for the last JSON-like block in the response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {"error": "No JSON found", "raw": text}
        except Exception as e:
            return {"error": str(e), "raw": text}

    def _format_meeting_history(self, task_id: str) -> str:
        """
        Retrieves all opinions from memory and formats them as readable text history.
        Includes Brand Guard approval status for each agent output.
        """
        opinions = self.memory.get_all_opinions(task_id)
        
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
                mod_data = self._extract_json(opinion.get("opinion", "{}"))
                history_lines.append(f"[MODERATOR FRAMING - {timestamp}]")
                history_lines.append(f"Next Role: {mod_data.get('next_role', 'N/A')}")
                history_lines.append(f"Transition Reason: {mod_data.get('transition_reason', 'N/A')}")
                history_lines.append("")
                continue
            
            # Skip Brand Guard roles (they audit, don't deliberate)
            if role.startswith("brand_guard_"):
                bg_data = self._extract_json(opinion.get("opinion", "{}"))
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
                opinion_data = self._extract_json(opinion_text)
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

    def _execute_orchestrated_meeting(self, task_id: str, user_input: str, role_sequence: list, synthesis_role: str, progress_callback=None, compass_weight=None, image_base64=None) -> str:
        """
        Production-grade meeting execution with JSON handoffs, sequential context passing, and Brand Guard audits.
        Each agent now builds upon or critiques the previous opinions in the meeting history.
        """
        self.memory.init_task(task_id, user_input, f"ORCHESTRATED_{synthesis_role.upper()}")
        
        msg_start = f"[START] Starting Orchestrated Meeting: {task_id}"
        print(msg_start)
        if progress_callback: progress_callback(msg_start)
        
        llm.eject_all_models()
        
        # 1. Moderator Framing
        mod_config = ROLES_CONFIG["moderator"]
        msg_mod = "[MODERATOR] Moderator is framing the discussion..."
        if progress_callback: progress_callback(msg_mod)
        
        mod_response = llm.generate_response(
            prompt=f"Task: {user_input}\nFrame the meeting and assign the first speaker from: {', '.join(role_sequence)}",
            system_prompt=mod_config["system_prompt"],
            model=mod_config["model"],
            temperature=mod_config["temperature"],
            max_tokens=mod_config["max_tokens"],
            gpu_layers=mod_config["gpu_layers"]
        )
        mod_data = self._extract_json(mod_response)
        self.memory.save_opinion(task_id, "moderator", mod_config["model"], json.dumps(mod_data))
        
        # Initialize meeting history for context
        meeting_history = self._format_meeting_history(task_id)

        # 2. Sequential Deliberation with Brand Guard Audit and Sequential Context
        for idx, role_key in enumerate(role_sequence):
            c = ROLES_CONFIG[role_key]
            msg_role = f"[AGENT] {role_key.upper()} is deliberating..."
            print(f"--> {msg_role}")
            if progress_callback: progress_callback(msg_role)
            
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
            agent_opinion = llm.generate_response(
                prompt=f"Context: {user_input}\nDeliberate on your specific area.\n\n{sequential_context}",
                system_prompt=self._inject_compass(c, weight_override=compass_weight),
                model=c["model"],
                temperature=c["temperature"],
                top_p=c["top_p"],
                top_k=c["top_k"],
                repeat_penalty=c["repeat_penalty"],
                max_tokens=c["max_tokens"],
                context_window=c["context_window"],
                gpu_layers=c["gpu_layers"],
                image_base64=image_base64 if idx == 0 else None # Only first agent sees image if provided
            )
            parsed_agent = self._extract_json(agent_opinion)
            self.memory.save_opinion(task_id, role_key, c["model"], json.dumps(parsed_agent))
            
            # Update meeting history for next agent
            meeting_history = self._format_meeting_history(task_id)
            
            # Brand Guard Audit
            bg_config = ROLES_CONFIG["brand_guard"]
            msg_bg = f"[BRAND_GUARD] Brand Guard is auditing {role_key.upper()}..."
            if progress_callback: progress_callback(msg_bg)
            
            bg_response = llm.generate_response(
                prompt=f"Audit this output: {json.dumps(parsed_agent)}",
                system_prompt=bg_config["system_prompt"],
                model=bg_config["model"],
                temperature=bg_config["temperature"],
                max_tokens=bg_config["max_tokens"],
                gpu_layers=bg_config["gpu_layers"]
            )
            bg_data = self._extract_json(bg_response)
            self.memory.save_opinion(task_id, f"brand_guard_{role_key}", bg_config["model"], json.dumps(bg_data))
            
            if not bg_data.get("approved", True):
                msg_veto = f"[VETO] BRAND VETO on {role_key}: {bg_data.get('reasoning', 'No reason provided')}"
                print(msg_veto)
                if progress_callback: progress_callback(msg_veto)
            
            llm.eject_all_models()

        # 3. Final Synthesis (Chairman/Overseer)
        msg_synth = f"[SYNTHESIS] {synthesis_role.upper()} is performing the final audit and synthesis..."
        if progress_callback: progress_callback(msg_synth)
        
        # Get formatted meeting history for the synthesis step
        final_meeting_history = self._format_meeting_history(task_id)
        
        opinions = self.memory.get_all_opinions(task_id)
        c = ROLES_CONFIG[synthesis_role]
        
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
            system_prompt=self._inject_compass(c, weight_override=compass_weight),
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )
        self.memory.save_oversight_analysis(task_id, final_opinion)
        
        # 4. Scribe Synthesis
        msg_scribe = "[SCRIBE] Scribe is generating the master report..."
        if progress_callback: progress_callback(msg_scribe)
        
        s_config = ROLES_CONFIG["scribe"]
        report = llm.generate_response(
            prompt=f"Original Task: {user_input}\nFinal Verdict: {final_opinion}\n\nMeeting History:\n{final_meeting_history}\n\nGenerate a master markdown report that captures the full deliberation process and the definitive outcome.",
            system_prompt=s_config["system_prompt"],
            model=s_config["model"],
            temperature=s_config["temperature"],
            max_tokens=s_config["max_tokens"],
            gpu_layers=s_config["gpu_layers"]
        )
        
        self.memory.complete_task(task_id)
        self._restore_default_state(progress_callback)
        return report

    def _restore_default_state(self, progress_callback=None):
        """Silently reloads the default boot LLM back into VRAM so it's ready for the next simple request."""
        
        # Flush the heavy models first!
        llm.eject_all_models()
        
        model_id = ROLES_CONFIG["simple"]["model"]
        msg = f"🔄 Restoring default boot LLM to VRAM..."
        print(f"--> {msg}")
        if progress_callback: progress_callback(msg)
        
        # Fire and forget lms load in a background process
        subprocess.Popen(
            f"lms load {model_id} -c 8192 -y", 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            shell=True
        )
        
    def process_request(self, user_input: str, image_base64: str = None, progress_callback=None, compass_weight: str = None):
            
        # 1. Routing
        classification = self.sentry.classify_request(user_input)
        pattern = classification["pattern"]
        msg = f"[{pattern}] Selected for complexity: {classification['complexity']}"
        print(msg)
        if progress_callback: progress_callback(msg)
        
        # 2. Vision Pre-Processing for Non-Vision Councils
        if image_base64 and pattern in ["TECHNICAL_MEETING", "SEQUENTIAL_BOARDROOM", "STANDARD", "DESIGN_MEETING"]:
            msg_vision = f"👁️ Non-vision council selected. Auto-translating image to text..."
            print(f"--> {msg_vision}")
            if progress_callback: progress_callback(msg_vision)
            
            image_description = self.execute_vision("Please describe this image in extreme detail so that a text-only AI council can understand it perfectly.", image_base64, progress_callback, compass_weight=compass_weight)
            user_input = f"{user_input}\n\n[Auto-Generated Image Description for Context]:\n{image_description}"
            image_base64 = None # Consume the image
            
        # 3. Execution
        if pattern == "SIMPLE":
            if image_base64:
                return self.execute_vision(user_input, image_base64, progress_callback, compass_weight=compass_weight)
            return self.execute_simple(user_input, compass_weight=compass_weight)
        elif pattern == "STANDARD":
            return self.execute_standard(user_input, compass_weight=compass_weight)
        elif pattern == "SEQUENTIAL_BOARDROOM" or pattern == "ONLINE_BOARDROOM":
            if pattern == "ONLINE_BOARDROOM":
                msg_fallback = "⚠️  [Notice: Online API models not yet hooked up. Falling back to Local SEQUENTIAL_BOARDROOM for testing]"
                print(msg_fallback)
                if progress_callback: progress_callback(msg_fallback)
            return self.execute_sequential_boardroom(user_input, progress_callback, compass_weight=compass_weight)
        elif pattern == "TECHNICAL_MEETING":
            return self.execute_technical_meeting(user_input, progress_callback, compass_weight=compass_weight)
        elif pattern == "DESIGN_MEETING":
            return self.execute_design_meeting(user_input, image_base64, progress_callback, compass_weight=compass_weight)
        elif pattern == "NFT_CREATION":
            return self.execute_nft_creation(user_input, progress_callback, compass_weight=compass_weight)
        else:
            return f"Pattern {pattern} is not yet fully implemented locally."
            
    def execute_simple(self, user_input: str, compass_weight: str = None) -> str:
        """Single model pass (Reflex Layer). Fast, agentic."""
        c = ROLES_CONFIG["simple"]
        return llm.generate_response(
            prompt=user_input, 
            system_prompt=self._inject_compass(c, weight_override=compass_weight), 
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )

    def execute_standard(self, user_input: str, compass_weight: str = None) -> str:
        """Single model + preset (Operational Brain)."""
        c = ROLES_CONFIG["standard"]
        return llm.generate_response(
            prompt=user_input, 
            system_prompt=self._inject_compass(c, weight_override=compass_weight), 
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )

    def execute_vision(self, user_input: str, image_base64: str, progress_callback=None, compass_weight: str = None) -> str:
        """Process image payloads using the specialized vision model."""
        c = ROLES_CONFIG["vision"]
        
        msg_eject = "🧹 Ejecting active models for Vision analysis..."
        print(f"--> {msg_eject}")
        if progress_callback: progress_callback(msg_eject)
        llm.eject_all_models()
        
        msg_load = f"👁️ Loading Vision Model: {c['model']}"
        print(f"--> {msg_load}")
        if progress_callback: progress_callback(msg_load)
        
        result = llm.generate_response(
            prompt=user_input, 
            system_prompt=self._inject_compass(c, weight_override=compass_weight), 
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"],
            image_base64=image_base64
        )
        
        if progress_callback: progress_callback("🎉 Vision processing complete!")
        self._restore_default_state(progress_callback)
        return result

    def execute_sequential_boardroom(self, user_input: str, progress_callback=None, compass_weight: str = None) -> str:
        """
        Production Sequential Boardroom: Strategy -> Execution -> Critique -> Creation -> Logic -> Chairman
        """
        task_id = self.memory.generate_task_id(user_input)
        role_sequence = ["board_strategist", "board_specialist", "board_critic", "board_creative", "board_logical"]
        return self._execute_orchestrated_meeting(
            task_id=task_id,
            user_input=user_input,
            role_sequence=role_sequence,
            synthesis_role="board_chairman",
            progress_callback=progress_callback,
            compass_weight=compass_weight
        )

    def execute_technical_meeting(self, user_input: str, progress_callback=None, compass_weight: str = None) -> str:
        """
        Production Technical Meeting: Specialist -> Innovation -> Critique -> Overseer
        """
        task_id = self.memory.generate_task_id(user_input)
        role_sequence = ["technical_specialist", "technical_creative", "technical_critic"]
        return self._execute_orchestrated_meeting(
            task_id=task_id,
            user_input=user_input,
            role_sequence=role_sequence,
            synthesis_role="technical_overseer",
            progress_callback=progress_callback,
            compass_weight=compass_weight
        )

    def execute_design_meeting(self, user_input: str, image_base64: str = None, progress_callback=None, compass_weight: str = None) -> str:
        """
        Production Design Meeting: Concept Generation -> Creative Expansion -> Aesthetic Critique -> Art Direction
        """
        task_id = self.memory.generate_task_id(user_input)
        role_sequence = ["design_junior", "design_creative", "design_critic"]
        return self._execute_orchestrated_meeting(
            task_id=task_id,
            user_input=user_input,
            role_sequence=role_sequence,
            synthesis_role="design_senior",
            progress_callback=progress_callback,
            compass_weight=compass_weight,
            image_base64=image_base64
        )

    def execute_nft_creation(self, user_input: str, progress_callback=None, compass_weight: str = None) -> str:
        """
        NFT Creation Workflow:
        1. Agent generates metadata.
        2. Agent simulates minting.
        3. Orchestrator returns the report.
        """
        msg_start = "[NFT] Initiating NFT Creation Pipeline..."
        print(f"--> {msg_start}")
        if progress_callback: progress_callback(msg_start)
        
        agent = NFTAgent(self)
        
        # We use the nft_specialist configuration to guide the local LLM if needed, 
        # but the agent has its own internal logic for now.
        
        # Extract theme from user_input (naive for now)
        theme = user_input.replace("/nft", "").replace("#nft", "").strip()
        if not theme:
            theme = "Unknown Relic"
            
        result = agent.process_creation(theme, context=user_input, compass_weight=compass_weight)
        
        report = textwrap.dedent(f"""
        # NFT CREATION REPORT
        
        **Theme**: {result['theme']}
        **Token ID**: `{result['token_id']}`
        **Minted At**: {result['minted_at']}
        
        ## Metadata
        - **Name**: {result['name']}
        - **Description**: {result['description']}
        
        ## Traits
        {json.dumps(result['traits'], indent=2)}
        
        ## Visual Direction
        > {result['image_prompt']}
        
        ---
        *Generated by Cognitive OS NFT Agent Module*
        """)
        
        if progress_callback: progress_callback("NFT Creation Complete!")
        return report
