import json
from src.llm_client import llm
from src.memory_file_system import MemoryFileManager
from src.sentry_router import SentryRouter

# ==============================================================================
# 🧠 COGNITIVE OS - GLOBAL MODEL CONFIGURATION
# ==============================================================================
# Define all roles, their specific models, system prompts, and inference params here.
# This makes it easy to change and maintain inference behavior across the entire script.

ROLES_CONFIG = {
    "simple": {
        "model": "local-model", # Default fallback
        "system_prompt": "You are a fast, precise assistant. Be concise.",
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 2048,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "standard": {
        "model": "local-model",
        "system_prompt": "You are an expert specialist. Provide a well-structured, creative but balanced response.",
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 4096,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "strategist": {
        "model": "hermes-4-70b",
        "system_prompt": "You are the Strategist / First Principles thinker. Analyze long-term implications, systems thinking, and question underlying assumptions. What is the real problem being solved?",
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "specialist": {
        "model": "qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max",
        "system_prompt": "You are the Specialist / Executor. Focus on technical accuracy, domain expertise, and the immediate actionable next steps. Be precise and avoid fluff.",
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "critic": {
        "model": "deepseek-r1-distill-qwen-32b-uncensored@q6_k",
        "system_prompt": "You are the Critic / Contrarian. Find fatal flaws, logical gaps, and play devil's advocate. Why will this fail?",
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "creative": {
        "model": "hermes-4.3-36b",
        "system_prompt": "You are the Creative / Expansionist. Uncover hidden opportunities. What is the most unconventional, provocative, or expansive approach?",
        "temperature": 0.9,
        "top_p": 0.95,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "logical": {
        "model": "gemma-4-31b-it",
        "system_prompt": "You are the Logical Outsider. Evaluate this with zero context. Look for logical inconsistencies and step-by-step feasibility.",
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "max_tokens": 8192,
        "context_window": 8192,
        "gpu_layers": -1
    },
    "overseer": {
        "model": "llama-4-scout-17b-16e-instruct",
        "system_prompt": "You are the Overseer / Chairman of the Council. You cross-reference opinions, detect consensus, weigh technical feasibility over pure creativity when there is risk, and synthesize a final actionable master document.",
        "temperature": 0.4,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 64000,
        "context_window": 32768,
        "gpu_layers": -1
    }
}
# ==============================================================================

class Orchestrator:
    def __init__(self):
        self.sentry = SentryRouter()
        self.memory = MemoryFileManager()
        
    def process_request(self, user_input: str, progress_callback=None):
        # 1. Routing
        classification = self.sentry.classify_request(user_input)
        pattern = classification["pattern"]
        msg = f"[{pattern}] Selected for complexity: {classification['complexity']}"
        print(msg)
        if progress_callback: progress_callback(msg)
        
        # 2. Execution
        if pattern == "SIMPLE":
            return self.execute_simple(user_input)
        elif pattern == "STANDARD":
            return self.execute_standard(user_input)
        elif pattern == "SEQUENTIAL_BOARDROOM" or pattern == "ONLINE_BOARDROOM":
            if pattern == "ONLINE_BOARDROOM":
                msg_fallback = "⚠️  [Notice: Online API models not yet hooked up. Falling back to Local SEQUENTIAL_BOARDROOM for testing]"
                print(msg_fallback)
                if progress_callback: progress_callback(msg_fallback)
            return self.execute_sequential_boardroom(user_input, progress_callback)
        elif pattern == "SMALL_COUNCIL":
            return self.execute_small_council(user_input, progress_callback)
        elif pattern == "DESIGN_COUNCIL":
            return self.execute_design_council(user_input, progress_callback)
        else:
            return f"Pattern {pattern} is not yet fully implemented locally."
            
    def execute_simple(self, user_input: str) -> str:
        """Single model pass (Reflex Layer). Fast, agentic."""
        c = ROLES_CONFIG["simple"]
        return llm.generate_response(
            prompt=user_input, 
            system_prompt=c["system_prompt"], 
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )

    def execute_standard(self, user_input: str) -> str:
        """Single model + preset (Operational Brain)."""
        c = ROLES_CONFIG["standard"]
        return llm.generate_response(
            prompt=user_input, 
            system_prompt=c["system_prompt"], 
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )

    def execute_sequential_boardroom(self, user_input: str, progress_callback=None) -> str:
        """
        True Sequential Boardroom: Dynamically loads different models for different roles.
        """
        task_id = self.memory.generate_task_id(user_input)
        self.memory.init_task(task_id, user_input, "SEQUENTIAL_BOARDROOM")
        
        msg_start = f"🚀 Started Sequential Boardroom\nTask ID: {task_id}"
        print(msg_start)
        if progress_callback: progress_callback(msg_start)
        
        # Eject any currently loaded models to ensure 42GB VRAM is fully available
        msg_eject = "🧹 Ejecting active models to clear VRAM..."
        print(f"--> {msg_eject}")
        if progress_callback: progress_callback(msg_eject)
        llm.eject_all_models()
        
        # Phase 1: Independent Deliberation
        for role_name in ["strategist", "specialist", "critic", "creative", "logical"]:
            c = ROLES_CONFIG[role_name]
            model_id = c["model"]
            msg_role = f"🧠 {role_name.upper()} is deliberating... (Loading: {model_id})"
            print(f"--> {msg_role}")
            if progress_callback: progress_callback(msg_role)
            
            # This API call tells LM Studio specifically which model to use.
            opinion = llm.generate_response(
                prompt=f"Task: {user_input}\nProvide your perspective.",
                system_prompt=c["system_prompt"],
                model=model_id,
                temperature=c["temperature"],
                top_p=c["top_p"],
                top_k=c["top_k"],
                repeat_penalty=c["repeat_penalty"],
                max_tokens=c["max_tokens"],
                context_window=c["context_window"],
                gpu_layers=c["gpu_layers"]
            )
            self.memory.save_opinion(task_id, role_name, model_id, opinion)
            if progress_callback: progress_callback(f"✅ {role_name.upper()} finished!")
            
        # Phase 2: Oversight Cross-Reference
        msg_overseer = "👁️ OVERSEER is generating cross-reference analysis..."
        print(f"--> {msg_overseer}")
        if progress_callback: progress_callback(msg_overseer)
        
        opinions = self.memory.get_all_opinions(task_id)
        opinions_json = json.dumps(opinions, indent=2)
        
        oversight_prompt = f"""
        Analyze these independent opinions for the task: "{user_input}"
        
        Opinions:
        {opinions_json}
        
        Identify:
        1. Consensus points
        2. Conflicts and Outliers
        3. Resolution (weigh technical safety over creative risk)
        """
        c = ROLES_CONFIG["overseer"]
        oversight_analysis = llm.generate_response(
            prompt=oversight_prompt,
            system_prompt=c["system_prompt"],
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )
        self.memory.save_oversight_analysis(task_id, oversight_analysis)
        
        # Phase 3: Final Synthesis
        msg_synth = "📝 OVERSEER is synthesizing the final master document..."
        print(f"--> {msg_synth}")
        if progress_callback: progress_callback(msg_synth)
        
        synthesis_prompt = f"""
        Based on the original task, the raw opinions, and your oversight analysis, generate the final, definitive response.
        
        Task: {user_input}
        
        Oversight Analysis:
        {oversight_analysis}
        
        Generate a beautifully structured markdown document as the final output.
        """
        c = ROLES_CONFIG["overseer"]
        final_output = llm.generate_response(
            prompt=synthesis_prompt,
            system_prompt=c["system_prompt"],
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )
        
        self.memory.complete_task(task_id)
        
        if progress_callback: progress_callback("🎉 Council process complete!")
        return final_output

    def _run_3_model_council(self, user_input: str, role_draft: str, role_refine: str, role_synthesize: str, pattern_name: str, custom_synthesis_instructions: str, progress_callback=None) -> str:
        task_id = self.memory.generate_task_id(user_input)
        self.memory.init_task(task_id, user_input, pattern_name)
        
        msg_start = f"🚀 Started {pattern_name}\nTask ID: {task_id}"
        print(msg_start)
        if progress_callback: progress_callback(msg_start)
        
        msg_eject = "🧹 Ejecting active models to clear VRAM..."
        print(f"--> {msg_eject}")
        if progress_callback: progress_callback(msg_eject)
        llm.eject_all_models()
        
        # Phase 1: Draft
        c = ROLES_CONFIG[role_draft]
        model_id = c["model"]
        msg_role = f"🧠 {role_draft.upper()} is generating draft... (Loading: {model_id})"
        print(f"--> {msg_role}")
        if progress_callback: progress_callback(msg_role)
        
        draft_opinion = llm.generate_response(
            prompt=f"Task: {user_input}\nProvide a comprehensive initial draft.",
            system_prompt=c["system_prompt"],
            model=model_id,
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )
        self.memory.save_opinion(task_id, role_draft, model_id, draft_opinion)
        if progress_callback: progress_callback(f"✅ {role_draft.upper()} finished!")
        
        llm.eject_all_models()
        
        # Phase 2: Refine
        c = ROLES_CONFIG[role_refine]
        model_id = c["model"]
        msg_role = f"🧠 {role_refine.upper()} is critiquing draft... (Loading: {model_id})"
        print(f"--> {msg_role}")
        if progress_callback: progress_callback(msg_role)
        
        refine_opinion = llm.generate_response(
            prompt=f"Task: {user_input}\n\nDraft to critique:\n{draft_opinion}\n\nProvide your critique and refinement suggestions.",
            system_prompt=c["system_prompt"],
            model=model_id,
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )
        self.memory.save_opinion(task_id, role_refine, model_id, refine_opinion)
        if progress_callback: progress_callback(f"✅ {role_refine.upper()} finished!")
        
        llm.eject_all_models()
        
        # Phase 3: Synthesize
        msg_synth = f"📝 {role_synthesize.upper()} is synthesizing the final document..."
        print(f"--> {msg_synth}")
        if progress_callback: progress_callback(msg_synth)
        
        synthesis_prompt = f"""
        Based on the original task, the initial draft, and the critique, generate the final, definitive response.
        
        Task: {user_input}
        
        Initial Draft ({role_draft}):
        {draft_opinion}
        
        Critique ({role_refine}):
        {refine_opinion}
        
        {custom_synthesis_instructions}
        """
        
        c = ROLES_CONFIG[role_synthesize]
        final_output = llm.generate_response(
            prompt=synthesis_prompt,
            system_prompt=c["system_prompt"],
            model=c["model"],
            temperature=c["temperature"],
            top_p=c["top_p"],
            top_k=c["top_k"],
            repeat_penalty=c["repeat_penalty"],
            max_tokens=c["max_tokens"],
            context_window=c["context_window"],
            gpu_layers=c["gpu_layers"]
        )
        
        self.memory.complete_task(task_id)
        if progress_callback: progress_callback(f"🎉 {pattern_name} process complete!")
        return final_output

    def execute_small_council(self, user_input: str, progress_callback=None) -> str:
        """Technical Draft -> Critic -> Overseer"""
        return self._run_3_model_council(
            user_input=user_input,
            role_draft="specialist",
            role_refine="critic",
            role_synthesize="overseer",
            pattern_name="SMALL_COUNCIL",
            custom_synthesis_instructions="Generate a beautifully structured markdown document as the final output. Weigh technical accuracy highly.",
            progress_callback=progress_callback
        )

    def execute_design_council(self, user_input: str, progress_callback=None) -> str:
        """Creative Draft -> Critic -> Overseer + Image Prompts"""
        return self._run_3_model_council(
            user_input=user_input,
            role_draft="creative",
            role_refine="critic",
            role_synthesize="overseer",
            pattern_name="DESIGN_COUNCIL",
            custom_synthesis_instructions="Generate a beautifully structured markdown document as the final output. Explicitly include 2-3 specific, detailed prompts for image generation (like Midjourney or Stable Diffusion) at the very end of the document to help visualize the concepts.",
            progress_callback=progress_callback
        )
