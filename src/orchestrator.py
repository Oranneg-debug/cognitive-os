import json
import sys
import textwrap
import os
from datetime import datetime
from dotenv import load_dotenv
import subprocess
import re
import yaml

# Force UTF-8 on stdout/stderr so emoji-heavy log lines don't blow up under
# Windows PowerShell's default cp1252 codec (Python 3.14 + LM Studio combo).
# `errors='replace'` keeps a stray glyph from ever masking a real exception.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from src.llm_client import llm
from src.memory_file_system import MemoryFileManager
from src.sentry_router import SentryRouter
from src.nft_agent import NFTAgent
from src.document_processor import extract_text_from_pdf

# Governance Foundation imports (A2, ARCH-2007E0A1)
from src.output_router import OutputRouter


# ==============================================================================
# 🧠 COGNITIVE OS - EMBEDDER OPTIMIZATION HELPERS
# ==============================================================================

def _flush_embedder():
    """Flush the embedder model from VRAM. Call this before operations that need heavy model loading."""
    print("[EMBEDDER] Flushing embedder from VRAM...")
    llm.eject_all_models()

# ==============================================================================
# 🧠 COGNITIVE OS - MASTER CONFIGURATION LOADER (LIVE RELOAD)
# ==============================================================================
class MasterConfig:
    _instance = None
    _config = None
    _last_modified_time = None
    _config_path = os.path.join(os.path.dirname(__file__), '..', 'dev', 'master_config.md')

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MasterConfig, cls).__new__(cls)
            cls._load_config()
        return cls._instance

    @classmethod
    def _load_config(cls):
        """Loads or reloads the master config from the YAML file."""
        try:
            with open(cls._config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract the YAML block
            yaml_match = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
            if not yaml_match:
                raise ValueError("Could not find a YAML code block in master_config.md")
            
            yaml_content = yaml_match.group(1)
            cls._config = yaml.safe_load(yaml_content)
            cls._last_modified_time = os.path.getmtime(cls._config_path)
            print("[OK] Master config loaded successfully.")

        except Exception as e:
            # Never let the diagnostic print itself raise (e.g. encoding issues)
            # — the real exception below is what matters.
            try:
                print(f"[FATAL] Could not load master_config.md: {e!r}")
            except Exception:
                pass
            # Fallback to an empty config to prevent crashing the whole system
            cls._config = {"models": {}, "roles": {}, "model_presets": []}

    @classmethod
    def get_config(cls) -> dict:
        """
        Returns the current configuration, reloading if the file has changed.
        """
        try:
            current_mod_time = os.path.getmtime(cls._config_path)
            if cls._last_modified_time is None or current_mod_time > cls._last_modified_time:
                print("🔄 master_config.md has changed. Reloading...")
                cls._load_config()
        except FileNotFoundError:
            print(f"🚨 WARNING: master_config.md not found at {cls._config_path}. Using cached or empty config.")
        
        return cls._config

def get_config() -> dict:
    """Singleton accessor for the master config."""
    return MasterConfig().get_config()

def get_role_config(role_key: str) -> dict:
    """Get the full configuration for a specific role from the master config."""
    config = get_config()
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

def get_model_presets() -> list:
    """Get all available model presets from the master config."""
    return get_config().get("model_presets", [])

class Orchestrator:
    def __init__(self, output_router: OutputRouter = None):
        load_dotenv()
        self.sentry = SentryRouter()
        self.memory = MemoryFileManager()
        self.output_router = output_router  # A2: Direct injection from api.py
        # Initialize config on startup
        get_config()
        
        # Ensure a clean slate on startup by flushing ALL models (including embedder)
        print("🧹 Performing startup VRAM flush (Absolute)...")
        try:
            llm.eject_all_models(force_all=True)
        except Exception as e:
            print(f"⚠️ Startup flush failed (LM Studio might not be fully ready yet): {e}")
        
        # Perform startup sync health check
        self._perform_startup_sync_check()
    
    def _perform_startup_sync_check(self):
        """
        Perform a sync health check on startup and log any issues.
        """
        try:
            from src.proposal_sync import ProposalSyncManager
            
            print("\n🔍 Performing startup proposal sync health check...")
            sync_manager = ProposalSyncManager()
            status = sync_manager.check_sync_status()
            status_dict = status.to_dict()
            
            health_emoji = {
                "green": "🟢",
                "yellow": "🟡",
                "red": "🔴"
            }.get(status_dict["health"], "⚪")
            
            print(f"   Sync Status: {health_emoji} {status_dict['health'].upper()}")
            print(f"   Backend Proposals: {status_dict['backend_count']}")
            print(f"   Vault Proposals: {status_dict['vault_count']}")
            
            if status_dict["missing_in_vault"]:
                print(f"   ⚠️ Missing in vault: {len(status_dict['missing_in_vault'])} files")
                for filename in status_dict["missing_in_vault"][:3]:  # Show first 3
                    print(f"      - {filename}")
            
            if status_dict["conflicts"]:
                print(f"   🚨 Conflicts detected: {len(status_dict['conflicts'])} files")
                for conflict in status_dict["conflicts"][:3]:  # Show first 3
                    print(f"      - {conflict['filename']}")
            
            print()
            
        except ImportError:
            print("   ⚠️ Sync manager not available (proposal_sync module missing)")
        except Exception as e:
            print(f"   ⚠️ Could not perform startup sync check: {e}")

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
            weight = weight_override if weight_override and weight_override != "DEFAULT" else role_config.get("compass_weight", "IGNORE")
            
            if weight in ["IGNORE", "NONE", None]:
                return system_prompt
                
            return f"{system_prompt}\n\n### THE DARK MAESTRO SOVEREIGN COMPASS:\n{compass}\n\n### YOUR ADHERENCE DIRECTIVE:\n{weight}"
        return system_prompt

    def _extract_json(self, text: str) -> dict:
        try:
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

    def _execute_orchestrated_meeting(self, task_id: str, user_input: str, role_sequence: list, synthesis_role: str, progress_callback=None, compass_weight=None, image_base64=None, source_file_path: str = None) -> str:
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
        mod_config = get_role_config("moderator")
        if mod_config.get("enabled", True):
            msg_mod = "[MODERATOR] Moderator is framing the discussion..."
            if progress_callback: progress_callback(msg_mod)
            
            mod_response = llm.generate_response(
                prompt=f"Task: {user_input}\nFrame the meeting and assign the first speaker from: {', '.join(role_sequence)}",
                system_prompt=mod_config["system_prompt"],
                model=mod_config["model"],
                temperature=mod_config.get("temperature", 0.4),
                max_tokens=mod_config.get("max_tokens", 512),
                gpu_layers=mod_config.get("gpu_layers", 0)
            )
            mod_data = self._extract_json(mod_response)
            self.memory.save_opinion(task_id, "moderator", mod_config["model"], json.dumps(mod_data))
        else:
            print("[MODERATOR] Skipped (disabled in config).")
        
        # Initialize meeting history for context
        meeting_history = self._format_meeting_history(task_id)

        # 2. Sequential Deliberation with Brand Guard Audit and Sequential Context
        for idx, role_key in enumerate(role_sequence):
            c = get_role_config(role_key)
            if not c.get("enabled", True):
                msg_skip = f"[AGENT] {role_key.upper()} is disabled. Skipping..."
                print(f"--> {msg_skip}")
                if progress_callback: progress_callback(msg_skip)
                continue

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
                temperature=c.get("temperature", 0.7),
                top_p=c.get("top_p", 0.9),
                top_k=c.get("top_k", 40),
                repeat_penalty=c.get("repeat_penalty", 1.1),
                max_tokens=c.get("max_tokens", 8192),
                context_window=c.get("context_window", 32768),
                gpu_layers=c.get("gpu_layers", -1),
                image_base64=image_base64 if idx == 0 else None # Only first agent sees image if provided
            )
            parsed_agent = self._extract_json(agent_opinion)
            self.memory.save_opinion(task_id, role_key, c["model"], json.dumps(parsed_agent))
            
            # Update meeting history for next agent
            meeting_history = self._format_meeting_history(task_id)
            
            # Brand Guard Audit
            bg_config = get_role_config("brand_guard")
            if bg_config.get("enabled", True):
                msg_bg = f"[BRAND_GUARD] Brand Guard is auditing {role_key.upper()}..."
                if progress_callback: progress_callback(msg_bg)
                
                bg_response = llm.generate_response(
                    prompt=f"Audit this output: {json.dumps(parsed_agent)}",
                    system_prompt=bg_config["system_prompt"],
                    model=bg_config["model"],
                    temperature=bg_config.get("temperature", 0.1),
                    max_tokens=bg_config.get("max_tokens", 512),
                    gpu_layers=bg_config.get("gpu_layers", 0)
                )
                bg_data = self._extract_json(bg_response)
                self.memory.save_opinion(task_id, f"brand_guard_{role_key}", bg_config["model"], json.dumps(bg_data))
                
                if not bg_data.get("approved", True):
                    msg_veto = f"[VETO] BRAND VETO on {role_key}: {bg_data.get('reasoning', 'No reason provided')}"
                    print(msg_veto)
                    if progress_callback: progress_callback(msg_veto)
            else:
                msg_bg_skip = f"[BRAND_GUARD] Audit skipped for {role_key.upper()} (disabled)."
                print(f"--> {msg_bg_skip}")
                if progress_callback: progress_callback(msg_bg_skip)
            
            llm.eject_all_models()

        # 3. Final Synthesis (Chairman/Overseer)
        msg_synth = f"[SYNTHESIS] {synthesis_role.upper()} is performing the final audit and synthesis..."
        if progress_callback: progress_callback(msg_synth)
        
        # Get formatted meeting history for the synthesis step
        final_meeting_history = self._format_meeting_history(task_id)
        
        opinions = self.memory.get_all_opinions(task_id)
        c = get_role_config(synthesis_role)
        
        if c.get("enabled", True):
            # Synthesis call is the load-bearing step of every orchestration —
            # if it raises, we MUST still persist an audit trail (the upstream
            # bug was a silent-drop: exceptions bubbled up, the caller's
            # finally-block archived the task with status=completed, and
            # oversight_analysis stayed empty with no log line to explain why).
            try:
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
                    temperature=c.get("temperature", 0.7),
                    top_p=c.get("top_p", 0.9),
                    top_k=c.get("top_k", 40),
                    repeat_penalty=c.get("repeat_penalty", 1.1),
                    max_tokens=c.get("max_tokens", 8192),
                    context_window=c.get("context_window", 32768),
                    gpu_layers=c.get("gpu_layers", -1)
                )
            except Exception as synth_exc:
                import traceback
                final_opinion = json.dumps({
                    "error": f"Synthesis call raised: {synth_exc!r}",
                    "synthesis_role": synthesis_role,
                    "traceback": traceback.format_exc(limit=4),
                })
                err_msg = (
                    f"[SYNTHESIS] ❌ {synthesis_role.upper()} raised "
                    f"{type(synth_exc).__name__}: {synth_exc}"
                )
                print(err_msg)
                if progress_callback: progress_callback(err_msg)
            self.memory.save_oversight_analysis(task_id, final_opinion)
        else:
            final_opinion = '{"error": "Synthesis role disabled in config."}'
            print(f"[SYNTHESIS] {synthesis_role.upper()} skipped (disabled).")
            # Persist the disabled state explicitly so it's auditable rather
            # than indistinguishable from a hard-crashed run.
            self.memory.save_oversight_analysis(task_id, final_opinion)
        
        # 4. Scribe Synthesis
        msg_scribe = "[SCRIBE] Scribe is generating the master report..."
        if progress_callback: progress_callback(msg_scribe)
        
        s_config = get_role_config("scribe")
        if s_config.get("enabled", True):
            report = llm.generate_response(
                prompt=f"Original Task: {user_input}\nFinal Verdict: {final_opinion}\n\nMeeting History:\n{final_meeting_history}\n\nGenerate a master markdown report that captures the full deliberation process and the definitive outcome.",
                system_prompt=s_config["system_prompt"],
                model=s_config["model"],
                temperature=s_config.get("temperature", 0.3),
                max_tokens=s_config.get("max_tokens", 4096),
                gpu_layers=s_config.get("gpu_layers", -1)
            )
        else:
            report = f"Scribe role is disabled. Raw final verdict:\n{final_opinion}"
            print("[SCRIBE] Skipped (disabled).")
        
        self.memory.complete_task(task_id)
        self._restore_default_state(progress_callback)
        
        # A2: Route the synthesis via OutputRouter if injected
        if self.output_router is not None:
            decision = self.output_router.route(report)
            return self.output_router.apply(decision, report)
        
        return report

    def _restore_default_state(self, progress_callback=None):
        """Silently reloads the default boot LLM back into VRAM so it's ready for the next simple request.

        NOTE 2026-05-23: ctx + device are read from master_config.md instead
        of being hardcoded. The previous `-c 8192` literal was the fifth
        silent-drop incident discovered during the governance bootstrap
        (see dev/decisions/_bootstrap_approvals_2026-05-22.md). With ctx
        hardcoded to 8192 here, every council run would reset ministral
        back to 8K immediately after running — guaranteeing the *next*
        council's scribe role failed with n_keep > n_ctx.
        """

        # Flush the heavy models first!
        llm.eject_all_models()

        role_cfg = get_role_config("simple") or {}
        model_id = role_cfg["model"]

        # ctx: prefer the role config, fall back to a safe 32K.
        ctx = (
            role_cfg.get("context_window")
            or role_cfg.get("context_length")
            or 32768
        )
        # Device: -1 means "all GPU layers"; 0 means CPU. Anything else
        # we pass through as-is.
        gpu_layers = role_cfg.get("gpu_layers", 0)
        if gpu_layers == 0:
            gpu_flag = "--gpu off"
        elif gpu_layers == -1:
            gpu_flag = "--gpu max"
        else:
            # Fractional offload not exposed via the CLI; let LM Studio
            # use whatever the saved per-model default is.
            gpu_flag = ""

        cmd = f"lms load {model_id} -c {int(ctx)} {gpu_flag} -y".strip()
        msg = f"🔄 Restoring default boot LLM to VRAM ({model_id} @ {ctx} ctx)..."
        print(f"--> {msg}")
        print(f"[RESTORE] {cmd}")
        if progress_callback:
            progress_callback(msg)

        # Fire and forget lms load in a background process
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )

    def process_request(self, user_input: str, image_base64: str = None, progress_callback=None, compass_weight: str = None, model_presets: list = None, document_base64: str = None, is_pdf: bool = False, source_file_path: str = None):
        # Handle PDF document processing if provided
        if is_pdf and document_base64:
            try:
                pdf_text = extract_text_from_pdf(document_base64)
                # Ensure the routing prefix remains at the start of the string!
                user_input = f"{user_input}\n\n[Attached PDF Content:]\n\n{pdf_text}"
                if progress_callback: progress_callback("[DOC_PROCESSOR] PDF content extracted and added to input.")
            except ValueError as e:
                error_msg = f"[DOC_PROCESSOR_ERROR] Failed to process PDF: {e}"
                print(error_msg)
                if progress_callback: progress_callback(error_msg)
                return error_msg # Return error if PDF processing fails

        # 1. Routing
        classification = self.sentry.classify_request(user_input)
        pattern = classification["pattern"]
        msg = f"[{pattern}] Selected for complexity: {classification['complexity']}"
        print(msg)
        if progress_callback: progress_callback(msg)
        
        # 2. Execution
        if pattern == "SIMPLE":
            if image_base64:
                return self.execute_vision(user_input, image_base64, progress_callback, compass_weight=compass_weight, source_file_path=source_file_path)
            return self.execute_simple(user_input, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "STANDARD":
            return self.execute_standard(user_input, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "SEQUENTIAL_BOARDROOM" or pattern == "ONLINE_BOARDROOM":
            if pattern == "ONLINE_BOARDROOM":
                msg_fallback = "⚠️  [Notice: Online API models not yet hooked up. Falling back to Local SEQUENTIAL_BOARDROOM for testing]"
                print(msg_fallback)
                if progress_callback: progress_callback(msg_fallback)
            return self.execute_sequential_boardroom(user_input, progress_callback, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "ORACLE_COUNCIL":
            return self.execute_oracle_council(user_input, progress_callback, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "TECHNICAL_MEETING":
            return self.execute_technical_meeting(user_input, progress_callback, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "DESIGN_MEETING":
            return self.execute_design_meeting(user_input, image_base64, progress_callback, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "NFT_CREATION":
            return self.execute_nft_creation(user_input, progress_callback, compass_weight=compass_weight, source_file_path=source_file_path)
        elif pattern == "DEVELOPMENT_LIFECYCLE":
            from src.dev_route import DevRouteManager
            dev_manager = DevRouteManager()
            
            # Clean the input to remove the trigger tag
            clean_input = re.sub(r'#dev|/dev', '', user_input, flags=re.IGNORECASE).strip()
            
            if not clean_input:
                 return "Error: Please provide a description for your proposal along with the tag."
                 
            print("📝 Creating new development proposal from request...")
            # Forward source_file_path so the proposal can link back to the
            # originating Obsidian note (e.g. a message under AI-Help/cognitive-os).
            result = dev_manager.process_dev_proposal(
                clean_input,
                origin="Obsidian-Plugin",
                source_file_path=source_file_path
            )
            source_note = os.path.splitext(os.path.basename(source_file_path))[0] if source_file_path else None
            source_msg = f"\nSource note: [[{source_note}]]" if source_note else ""
            return f"✅ Proposal Created: {result['proposal_id']}\nStatus: Added to Kanban Backlog.{source_msg}"
        else:
            return f"Pattern {pattern} is not yet fully implemented locally."

    def execute_simple(self, user_input: str, progress_callback=None, compass_weight: str = None, image_base64: str = None, source_file_path: str = None) -> str:
        """
        Basic single-model query for low-complexity tasks. No complex orchestration.
        """
        # This will be a direct call to the LLM, not _execute_orchestrated_meeting
        # Add logic to handle source_file_path if needed for simple pattern output
        # For now, just pass user_input directly
        print("[SIMPLE] Executing simple request...")
        c = get_role_config("simple")
        response = llm.generate_response(
            prompt=user_input,
            system_prompt=self._inject_compass(c, weight_override=compass_weight),
            model=c["model"],
            temperature=c.get("temperature", 0.7),
            max_tokens=c.get("max_tokens", 4096),
            context_window=c.get("context_window", 32768),
            gpu_layers=c.get("gpu_layers", -1),
            image_base64=image_base64
        )
        return response

    def execute_standard(self, user_input: str, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
        """
        Standard single-model query with a preset context. No complex orchestration.
        """
        # Similar to simple, direct LLM call
        print("[STANDARD] Executing standard request...")
        c = get_role_config("standard")
        response = llm.generate_response(
            prompt=user_input,
            system_prompt=self._inject_compass(c, weight_override=compass_weight),
            model=c["model"],
            temperature=c.get("temperature", 0.7),
            max_tokens=c.get("max_tokens", 4096),
            context_window=c.get("context_window", 32768),
            gpu_layers=c.get("gpu_layers", -1)
        )
        return response

    def execute_vision(self, user_input: str, image_base64: str, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
        """
        Executes a vision-based request using a model that supports images.
        """
        print("[VISION] Executing vision request...")
        c = get_role_config("vision")
        response = llm.generate_response(
            prompt=user_input,
            system_prompt=self._inject_compass(c, weight_override=compass_weight),
            model=c["model"],
            temperature=c.get("temperature", 0.7),
            max_tokens=c.get("max_tokens", 4096),
            context_window=c.get("context_window", 32768),
            gpu_layers=c.get("gpu_layers", -1),
            image_base64=image_base64
        )
        return response

    def execute_nft_creation(self, user_input: str, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
        """
        Executes the NFT creation lifecycle.
        """
        print("[NFT_CREATION] Executing NFT creation request...")
        nft_agent = NFTAgent()
        return nft_agent.create_nft_metadata(user_input)

    def execute_oracle_council(self, user_input: str, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
        """
        Oracle Council Protocol: Rigorous highest-tier execution logic.
        """
        task_id = self.memory.generate_task_id(user_input)
        role_sequence = ["board_strategist", "board_critic", "board_logical"]
        return self._execute_orchestrated_meeting(
            task_id=task_id,
            user_input=user_input,
            role_sequence=role_sequence,
            synthesis_role="board_chairman",
            progress_callback=progress_callback,
            compass_weight="MAXIMUM",
            source_file_path=source_file_path
        )

    def execute_sequential_boardroom(self, user_input: str, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
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
            compass_weight=compass_weight,
            source_file_path=source_file_path
        )

    def execute_technical_meeting(self, user_input: str, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
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
            compass_weight=compass_weight,
            source_file_path=source_file_path
        )

    def execute_design_meeting(self, user_input: str, image_base64: str = None, progress_callback=None, compass_weight: str = None, source_file_path: str = None) -> str:
        """
        Production Design Meeting: Junior Designer -> Creative Expansionist -> Critic -> Senior Designer
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
            image_base64=image_base64,
            source_file_path=source_file_path
        )

    def continue_development_lifecycle(self, proposal_id: str, next_phase: str, proposal_content: str) -> str:
        """
        Continue the development lifecycle for a proposal moved on the Kanban board.

        Called by kanban_processor when a card is dragged to a new column.
        Each phase runs the appropriate council/meeting and writes the result
        back into the proposal file via DevRouteManager.

        Args:
            proposal_id:      The DEV-… ID of the proposal (e.g. DEV-20260518-123456-ABCD)
            next_phase:       The target lifecycle phase: 'beta', 'alpha', 'finalized', 'deployed'
            proposal_content: Full markdown content of the proposal file at the time of the move

        Returns:
            str: Human-readable result message
        """
        from src.dev_route import DevRouteManager
        dev_manager = DevRouteManager()

        print(f"[LIFECYCLE] Starting phase '{next_phase}' for {proposal_id}")

        # ------------------------------------------------------------------
        # BETA: Technical council reviews the proposal, then a handoff
        #       document is generated for the developer to work from in VS Code.
        #       Card stays in Beta Testing (🔍 Review) until the human is done.
        # ------------------------------------------------------------------
        if next_phase == "beta":
            user_input = (
                f"Review the following development proposal thoroughly.\n\n"
                f"Your output MUST contain four clearly-headed sections:\n"
                f"1. **Summary** — what this system does and its purpose\n"
                f"2. **Difficulties & Constraints** — technical challenges, limitations, risks\n"
                f"3. **Implementation Tasks** — a numbered list of concrete coding tasks\n"
                f"4. **Technical Recommendations** — architecture, libraries, patterns to use\n\n"
                f"Proposal ID: {proposal_id}\n\n"
                f"{proposal_content}"
            )
            report = self.execute_technical_meeting(
                user_input=user_input,
                source_file_path=None
            )
            # Generate handoff document in vault + source backup, and link proposal
            handoff_result = dev_manager.generate_beta_handoff(proposal_id, report)
            if "error" in handoff_result:
                raise RuntimeError(f"Handoff generation failed: {handoff_result['error']}")
            return (
                f"✅ Beta Council review complete for {proposal_id}.\n"
                f"Handoff saved to: {handoff_result['filename']}\n"
                f"Open the handoff in VS Code and work through the task checklist.\n"
                f"Move the card to Alpha Polish when all tasks are ticked off."
            )

        # ------------------------------------------------------------------
        # ALPHA: Full boardroom produces the Alpha Polish execution plan.
        # ------------------------------------------------------------------
        elif next_phase == "alpha":
            user_input = (
                f"The following proposal has passed Beta Testing. "
                f"Produce a comprehensive Alpha Polish plan covering UI/UX refinements, "
                f"performance optimisations, and final pre-release hardening.\n\n"
                f"Proposal ID: {proposal_id}\n\n"
                f"{proposal_content}"
            )
            report = self.execute_sequential_boardroom(
                user_input=user_input,
                source_file_path=None
            )
            handoff_result = dev_manager.generate_alpha_handoff(proposal_id, report)
            if "error" in handoff_result:
                raise RuntimeError(f"Alpha handoff generation failed: {handoff_result['error']}")
            return (
                f"✅ Alpha Polish plan created for {proposal_id}.\n"
                f"Handoff saved to: {handoff_result['filename']}\n"
                f"Open the handoff in VS Code and work through the task checklist.\n"
                f"Move the card to Finalized when all tasks are ticked off."
            )

        # ------------------------------------------------------------------
        # FINALIZED / DEPLOYED: Mark the proposal as released.
        # ------------------------------------------------------------------
        elif next_phase in ("finalized", "deployed"):
            dev_manager.finalize_release(
                proposal_id,
                {
                    "version_number": "1.0.0",
                    "release_notes": f"Released via Kanban board transition to '{next_phase}'.",
                    "models_deployed": []
                },
                user_approved=True
            )
            return f"✅ Proposal {proposal_id} finalised and released."

        else:
            raise ValueError(f"Unknown lifecycle phase '{next_phase}' for proposal {proposal_id}")
