import json
from src.llm_client import llm
from src.memory_file_system import MemoryFileManager
from src.sentry_router import SentryRouter

# Claude Council / Boardroom Roles
ROLES = {
    "strategist": "You are the Strategist / First Principles thinker. Analyze long-term implications, systems thinking, and question underlying assumptions. What is the real problem being solved?",
    "specialist": "You are the Specialist / Executor. Focus on technical accuracy, domain expertise, and the immediate actionable next steps. Be precise and avoid fluff.",
    "critic": "You are the Critic / Contrarian. Find fatal flaws, logical gaps, and play devil's advocate. Why will this fail?",
    "creative": "You are the Creative / Expansionist. Uncover hidden opportunities. What is the most unconventional, provocative, or expansive approach?",
    "logical": "You are the Logical Outsider. Evaluate this with zero context. Look for logical inconsistencies and step-by-step feasibility.",
    "overseer": "You are the Overseer / Chairman of the Council. You cross-reference opinions, detect consensus, weigh technical feasibility over pure creativity when there is risk, and synthesize a final actionable master document."
}

# Map your specific LM Studio model identifiers here!
# You can find the exact model ID in LM Studio by hovering over the loaded model,
# or looking at the local server logs when it loads.
# Example: "lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF"
MODEL_ROLES = {
    "strategist": "hermes-4-70b",
    "specialist": "qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max",
    "critic":     "deepseek-r1-distill-qwen-32b-uncensored@q6_k",
    "creative":   "hermes-4.3-36b",
    "logical":    "gemma-4-31b-it",
    "overseer":   "llama-4-scout-17b-16e-instruct"
}

# Configure inference settings per role
# Adjust these to fine-tune how "creative" or "strict" each role behaves
# max_tokens dictates how long the model's generated response is allowed to be
MODEL_CONFIG = {
    "strategist": {"temperature": 0.7, "top_p": 0.9, "top_k": 40, "max_tokens": 8192},
    "specialist": {"temperature": 0.2, "top_p": 0.8, "top_k": 20, "max_tokens": 8192},
    "critic":     {"temperature": 0.5, "top_p": 0.9, "top_k": 40, "max_tokens": 8192},
    "creative":   {"temperature": 0.9, "top_p": 0.95, "top_k": 50, "max_tokens": 8192},
    "logical":    {"temperature": 0.1, "top_p": 0.8, "top_k": 20, "max_tokens": 8192},
    "overseer":   {"temperature": 0.4, "top_p": 0.9, "top_k": 40, "max_tokens": 64000} 
}

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
        else:
            return f"Pattern {pattern} is not yet fully implemented locally."
            
    def execute_simple(self, user_input: str) -> str:
        """Single model pass (Reflex Layer). Fast, agentic."""
        return llm.generate_response(
            prompt=user_input, 
            system_prompt="You are a fast, precise assistant. Be concise.", 
            model="local-model", # Default fallback
            temperature=0.3
        )

    def execute_standard(self, user_input: str) -> str:
        """Single model + preset (Operational Brain)."""
        return llm.generate_response(
            prompt=user_input, 
            system_prompt="You are an expert specialist. Provide a well-structured, creative but balanced response.", 
            model="local-model",
            temperature=0.7
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
            model_id = MODEL_ROLES[role_name]
            msg_role = f"🧠 {role_name.upper()} is deliberating... (Loading: {model_id})"
            print(f"--> {msg_role}")
            if progress_callback: progress_callback(msg_role)
            
            system_prompt = ROLES[role_name]
            config = MODEL_CONFIG[role_name]
            
            # This API call tells LM Studio specifically which model to use.
            opinion = llm.generate_response(
                prompt=f"Task: {user_input}\nProvide your perspective.",
                system_prompt=system_prompt,
                model=model_id,
                temperature=config["temperature"],
                top_p=config["top_p"],
                top_k=config["top_k"],
                max_tokens=config["max_tokens"]
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
        oversight_config = MODEL_CONFIG["overseer"]
        oversight_analysis = llm.generate_response(
            prompt=oversight_prompt,
            system_prompt=ROLES["overseer"],
            model=MODEL_ROLES["overseer"],
            temperature=oversight_config["temperature"],
            top_p=oversight_config["top_p"],
            top_k=oversight_config["top_k"],
            max_tokens=oversight_config["max_tokens"]
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
        final_output = llm.generate_response(
            prompt=synthesis_prompt,
            system_prompt=ROLES["overseer"],
            model=MODEL_ROLES["overseer"],
            temperature=oversight_config["temperature"],
            top_p=oversight_config["top_p"],
            top_k=oversight_config["top_k"],
            max_tokens=oversight_config["max_tokens"]
        )
        
        self.memory.complete_task(task_id)
        
        if progress_callback: progress_callback("🎉 Council process complete!")
        return final_output
