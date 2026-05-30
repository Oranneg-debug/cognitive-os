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

        # C1 (Phase 5): feature flag — if OutputRouter is disabled, force legacy
        # ObsidianWriter path by clearing the injected router.
        from src.integration_flags import is_output_router_enabled
        if not is_output_router_enabled():
            if self.output_router is not None:
                print("[LEGACY] integration.output_router_enabled=false; reverting Orchestrator to ObsidianWriter path")
            self.output_router = None

        # The heavy boot-time side-effects (VRAM flush + proposal-sync health
        # check) used to fire here. They were moved into :meth:`boot` so that
        # ``Orchestrator()`` itself is cheap to construct — tests, scripts,
        # and any tooling that imports ``src.api`` no longer eject the user's
        # in-use models. The FastAPI lifespan calls ``boot()`` explicitly on
        # real server startup; nothing else should.
        self._has_booted = False

    def boot(self) -> None:
        """Run the heavy startup side-effects exactly once.

        Called from the FastAPI lifespan (``src.api:lifespan``) when the
        process is the actual API server. Idempotent — subsequent calls
        are no-ops, so re-entry via reload paths is safe.

        Operations:
          1. ``llm.eject_all_models(force_all=True)`` — clears VRAM so the
             council starts from a known state.
          2. ``self._perform_startup_sync_check()`` — proposal-sync health
             check (logs RED/YELLOW/GREEN).

        DO NOT call this from tests, scripts, or any code that just imports
        ``src.api`` for its routes / models. The whole point of the boot/
        construct split is that import is now side-effect-free.
        """
        if self._has_booted:
            return
        self._has_booted = True

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
                for filename in status_dict['missing_in_vault'][:3]:  # Show first 3
                    print(f"      - {filename}")
            
            if status_dict["conflicts"]:
                print(f"   🚨 Conflicts detected: {len(status_dict['conflicts'])} files")
                for conflict in status_dict['conflicts'][:3]:  # Show first 3
                    print(f"      - {conflict['filename']}")
            
            print()
            
        except ImportError:
            print("   ⚠️ Sync manager not available (proposal_sync module missing)")
        except Exception as e:
            print(f"   ⚠️ Could not perform startup sync check: {e}")

    def process_request(self, user_input: str, image_base64: str = None, progress_callback=None, compass_weight: str = None, model_presets: list = None, document_base64: str = None, is_pdf: bool = False, source_file_path: str = None):
        """
        Main entry point for all pattern-based orchestration.
        
        Handles PDF document processing, pattern classification, and dispatches
        to the appropriate pattern executor via PATTERN_REGISTRY.
        
        Args:
            user_input: The original request text
            image_base64: Optional base64-encoded image
            progress_callback: Optional callback for progress updates
            compass_weight: Weight of the Sovereign Compass (DEFAULT/MINIMUM/MAXIMUM/IGNORE)
            model_presets: Optional list of model presets
            document_base64: Optional base64-encoded PDF document
            is_pdf: Flag indicating if document_base64 contains a PDF
            source_file_path: Optional path to source file
            
        Returns:
            The synthesized output from the pattern executor
        """
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
        
        # 2. Dispatch to pattern executor via PATTERN_REGISTRY
        from src.patterns import PATTERN_REGISTRY, PatternRequest
        
        req = PatternRequest(
            user_input=user_input,
            image_base64=image_base64,
            compass_weight=compass_weight,
            source_file_path=source_file_path,
            progress_callback=progress_callback,
            output_router=self.output_router,
        )
        
        if pattern in PATTERN_REGISTRY:
            return PATTERN_REGISTRY[pattern](req)
        else:
            return f"Pattern {pattern} is not yet fully implemented locally."

    def continue_development_lifecycle(self, proposal_id: str, next_phase: str, proposal_content: str) -> str:
        """
        Continue the development lifecycle for a proposal moved on the Kanban board.

        SCOPE (2026-05-26): This method handles ONLY alpha / finalized /
        deployed transitions. The proposal-stage severity dispatcher AND
        the beta-stage council+handoff hook both live in
        ``src/api.py::transition_card`` BackgroundTasks now — see the
        comment block above that function. The old branches that ran a
        council on the beta_testing entry have been removed; that work
        was moved to api.py so the dashboard transition endpoint is the
        single trigger surface (no more file-watcher).

        Args:
            proposal_id:      The DEV-/ARCH-/NLST-… ID of the proposal.
            next_phase:       'alpha' | 'finalized' | 'deployed'
            proposal_content: Full markdown content of the proposal file.
        """
        from src.dev_route import DevRouteManager
        dev_manager = DevRouteManager()

        print(f"[LIFECYCLE] Starting phase '{next_phase}' for {proposal_id}")

        # ------------------------------------------------------------------
        # ALPHA: Full boardroom produces the Alpha Polish execution plan.
        # ------------------------------------------------------------------
        if next_phase == "alpha":
            user_input = (
                f"The following proposal has passed Beta Testing. "
                f"Produce a comprehensive Alpha Polish plan covering UI/UX refinements, "
                f"performance optimisations, and final pre-release hardening.\n\n"
                f"Proposal ID: {proposal_id}\n\n"
                f"{proposal_content}"
            )
            # Use the SequentialBoardroom pattern via the registry
            from src.patterns import PATTERN_REGISTRY, PatternRequest
            req = PatternRequest(
                user_input=user_input,
                compass_weight="DEFAULT",
                source_file_path=None,
                output_router=self.output_router,
            )
            report = PATTERN_REGISTRY["ALPHA_COUNCIL"](req)
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