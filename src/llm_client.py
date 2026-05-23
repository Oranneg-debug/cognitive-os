import os
import requests
import json
from openai import OpenAI
from typing import Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class GeminiClient:
    """Connector for Google's Gemini API using the new google-genai SDK."""
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
            self.enabled = True
        else:
            self.enabled = False

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None, model: str = "models/gemini-3.1-pro-preview", temperature: float = 0.7, max_tokens: int = 4096) -> str:
        if not self.enabled:
            return "Error: Gemini API key not found in .env"
        
        try:
            # Configure the generation
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            return f"Gemini Error: {str(e)}"

class LLMClient:
    """
    Wrapper for LM Studio API (OpenAI compatible) and Gemini API.
    Connects to the local server, typically at http://localhost:1234/v1

    Lifecycle (load/unload/config) is delegated to ``LMStudioLoader`` —
    see DEV-20260521-001000-B5D5C0DE. The previous regime POSTed load
    configs to a non-existent ``/api/v1/models/load`` endpoint and every
    setting was silently dropped; the LM Studio JIT auto-loader used GUI
    prefs instead. Now: load via lmstudio SDK / `lms` CLI, inference via
    OpenAI client.
    """

    # Singleton loader instance — shared across all LLMClient calls.
    # Lazily constructed to avoid importing the SDK at module-init time
    # (so tools that only need GeminiClient don't pay the import cost).
    _loader = None

    @classmethod
    def _get_loader(cls):
        if cls._loader is None:
            # Local import: keeps `from src.llm_client import GeminiClient`
            # working even on hosts where `lmstudio` isn't installed yet.
            from src.lmstudio_loader import LMStudioLoader, LoaderError  # noqa: F401
            cls._loader = LMStudioLoader()
        return cls._loader

    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", api_key: str = "lm-studio"):
        # LM Studio acts as a drop-in replacement for OpenAI
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.gemini = GeminiClient()
        
    def generate_response(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None, 
        model: str = "local-model",
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        min_p: float = 0.0,
        max_tokens: int = 2048,
        context_window: int = 8192,
        gpu_layers: int = -1,
        image_base64: Optional[str] = None,
        flash_attention: Optional[bool] = None,
        cache_type_k: Optional[str] = None,
        cache_type_v: Optional[str] = None,
        gpu_offload_ratio: Optional[float] = None,
        n_parallel: Optional[int] = None,
        **_extra_load_opts,
    ) -> str:
        """
        Generate a response using the local LLM or Gemini.
        """
        # Route to Gemini if requested
        if model.lower().startswith("gemini"):
            return self.gemini.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )

        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        if image_base64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_base64}}
                ]
            })
        else:
            messages.append({"role": "user", "content": prompt})
        
        # 1. Delegate load lifecycle to the LMStudioLoader.
        #    The OpenAI client below STILL handles inference — we only
        #    use the loader to (re)load the model with the right config.
        #    See DEV-20260521-001000-B5D5C0DE for the migration rationale.
        try:
            loader = self._get_loader()
            # Build the loader-shaped config dict from the kwargs we have.
            # ``normalize_config`` (inside the loader) will canonicalize
            # aliases and reject unknown keys loudly.
            load_cfg: dict = {}
            if context_window:
                load_cfg["context_length"] = context_window
            if flash_attention is not None:
                load_cfg["flash_attention"] = bool(flash_attention)
            if cache_type_k is not None:
                load_cfg["llama_k_cache_quantization_type"] = cache_type_k
            if cache_type_v is not None:
                load_cfg["llama_v_cache_quantization_type"] = cache_type_v
            # GPU offload — preserve the historical semantics:
            #   gpu_offload_ratio explicit  -> use it (float or "max")
            #   gpu_layers == -1            -> "max"
            #   otherwise                   -> no override (use GUI prefs)
            if gpu_offload_ratio is not None:
                load_cfg["gpu"] = {"ratio": gpu_offload_ratio}
            elif gpu_layers == -1:
                load_cfg["gpu"] = {"ratio": "max"}
            # Parallelism — triggers the loader's CLI back-channel.
            if n_parallel is not None:
                load_cfg["n_parallel"] = int(n_parallel)

            result = loader.ensure_loaded(
                model,
                config=load_cfg or None,
                instance_identifier=model,  # match OpenAI client's `model` arg
                ttl=None,                   # no auto-unload during a council
            )
            kv_note = ""
            if cache_type_k or cache_type_v or flash_attention is not None:
                kv_note = (
                    f" | FA={flash_attention} "
                    f"K={cache_type_k or 'f16'} V={cache_type_v or 'f16'}"
                )
            if n_parallel is not None:
                kv_note += f" | n_par={n_parallel}"
            print(
                f"[LOADED] {result.action}: {result.identifier} "
                f"(Context: {context_window}, "
                f"GPU: {gpu_layers if gpu_layers != -1 else 'max'}"
                f"{kv_note}, {result.duration_seconds:.2f}s)"
            )

        except Exception as e:
            # Loader failures are NOT fatal here — the OpenAI client will
            # still attempt inference, and LM Studio will JIT-load using
            # its GUI prefs as a fallback. Log loudly so the failure is
            # visible (the previous regime silently dropped these errors).
            print(f"[WARNING] Loader delegation failed for {model!r}: {e!r}")
            print(f"[WARNING] Falling back to LM Studio JIT auto-load (GUI prefs).")

        # 2. Execute the inference request (execution metrics only)
        try:
            print("-" * 60)
            print(f"🚀 Calling LM Studio with model: {model}")
            print("  INFERENCE PARAMS:")
            print(f"    - temperature: {temperature}")
            print(f"    - top_p: {top_p}")
            print(f"    - top_k: {top_k}")
            print(f"    - max_tokens: {max_tokens}")
            print(f"    - repeat_penalty: {repeat_penalty}")
            print("-" * 60)

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body={
                    "top_k": top_k,
                    "repeat_penalty": repeat_penalty,
                    "min_p": min_p
                }
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error communicating with local LLM: {e}")
            return f"Error: {str(e)}"
            
    def eject_all_models(self, force_all: bool = False):
        """
        Unload all currently loaded models from LM Studio to free VRAM.
        Uses LM Studio's specific /api/v1/models/unload endpoint.
        
        Args:
            force_all: If True, bypasses the shield and unloads embedding models as well.
        """
        try:
            # Get list of currently loaded models via OpenAI standard endpoint
            loaded_models = self.client.models.list()
            
            host_url = f"{self.client.base_url.scheme}://{self.client.base_url.host}:{self.client.base_url.port}"
            unload_url = f"{host_url}/api/v1/models/unload"
            
            for model in loaded_models.data:
                model_id = model.id
                
                # Protect embedding models from being unloaded so RAG stays functional
                # UNLESS force_all is True (e.g., during startup flush)
                if not force_all and "embed" in model_id.lower():
                    print(f"[SHIELD] Skipping unload of embedder model: {model_id}")
                    continue
                    
                requests.post(unload_url, json={"instance_id": model_id}, timeout=5)
                print(f"[UNLOADED] Unloaded model: {model_id}")
                
        except Exception as e:
            print(f"[WARNING] Could not eject models: {e}")

# Singleton instance for easy import
llm = LLMClient()
