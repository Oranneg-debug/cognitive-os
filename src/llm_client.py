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
    Wrapper for llama-swap (OpenAI-compatible) and Gemini API.

    llama-swap sits in front of one or more llama-server instances and
    automatically starts / stops the right backend when the OpenAI client
    sends ``model=<name>``.  Model lifecycle (context size, GPU layers,
    flash-attention, KV-cache quantisation, …) is configured once in
    ``llama-swap.yaml`` — callers only need to supply inference-time
    parameters (temperature, top_p, max_tokens, etc.).

    Default endpoint: http://127.0.0.1:1234/v1
    Override via INFERENCE_BASE_URL / INFERENCE_API_KEY env vars.
    """

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
    ):
        base_url = base_url or os.getenv("INFERENCE_BASE_URL", "http://127.0.0.1:1234/v1")
        api_key = api_key or os.getenv("INFERENCE_API_KEY", "not-needed")
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
        image_base64: Optional[str] = None,
        reasoning_enabled: Optional[bool] = None,
        **_extra_load_opts,
    ) -> str:
        """
        Generate a response using the local LLM (via llama-swap) or Gemini.

        llama-swap auto-starts the correct backend when it sees ``model=X``,
        so there is no explicit load/unload step here.  Loader-specific
        parameters (context_window, gpu_layers, flash_attention, cache_type_k,
        cache_type_v, gpu_offload_ratio, batch_size) are accepted via
        ``**_extra_load_opts`` for backward compatibility but are silently
        ignored — those settings live in llama-swap.yaml now.
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
        
        # Log any ignored loader opts (once, at debug level) so devs can
        # tell if stale config keys are being passed from master_config.
        if _extra_load_opts:
            ignored = ", ".join(sorted(_extra_load_opts.keys()))
            print(f"[llm_client] Ignored loader-only opts (handled by llama-swap.yaml): {ignored}")

        # Execute the inference request — llama-swap routes to the right
        # backend automatically based on the model name.
        try:
            print("-" * 60)
            print(f"🚀 Calling llama-swap with model: {model}")
            print("  INFERENCE PARAMS:")
            print(f"    - temperature: {temperature}")
            print(f"    - top_p: {top_p}")
            print(f"    - top_k: {top_k}")
            print(f"    - max_tokens: {max_tokens}")
            print(f"    - repeat_penalty: {repeat_penalty}")
            print("-" * 60)

            # Build extra_body dynamically so we don't send None values.
            extra: dict = {
                "top_k": top_k,
                "repeat_penalty": repeat_penalty,
                "min_p": min_p,
            }
            if reasoning_enabled is not None:
                extra["reasoning_enabled"] = bool(reasoning_enabled)

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error communicating with local LLM: {e}")
            return f"Error: {str(e)}"
            
    def eject_all_models(self, force_all: bool = False):
        """
        Unload all currently loaded models from llama-swap to free VRAM.
        Uses llama-swap's ``POST /unload`` endpoint which stops the
        currently running llama-server backend.
        
        Args:
            force_all: If True, bypasses the shield and unloads embedding models as well.
        """
        try:
            # Derive the host URL from the OpenAI client's base_url
            # (e.g. http://127.0.0.1:1234/v1 -> http://127.0.0.1:1234)
            host_url = f"{self.client.base_url.scheme}://{self.client.base_url.host}:{self.client.base_url.port}"

            if not force_all:
                # Check loaded models first so we can shield embedding models
                try:
                    loaded_models = self.client.models.list()
                    for m in loaded_models.data:
                        if "embed" in m.id.lower():
                            print(f"[SHIELD] Embedding model loaded ({m.id}) — skipping unload to protect RAG")
                            return
                except Exception:
                    pass  # If we can't list models, proceed with unload anyway

            unload_url = f"{host_url}/api/models/unload"
            resp = requests.post(unload_url, timeout=10)
            resp.raise_for_status()
            print(f"[UNLOADED] llama-swap models unloaded (status {resp.status_code})")
                
        except Exception as e:
            print(f"[WARNING] Could not eject models via llama-swap: {e}")

# Singleton instance for easy import
llm = LLMClient()


def flush_vram(force_all: bool = False) -> None:
    """
    Top-level function to flush VRAM by ejecting all loaded models.
    Wraps the singleton LLMClient.eject_all_models() method.
    
    Args:
        force_all: If True, bypasses the shield and unloads embedding models as well.
    """
    llm.eject_all_models(force_all=force_all)


def restore_default_role() -> None:
    """
    No-op under llama-swap.

    Under LM Studio this restored the default profile via ``lms profile
    apply default``.  With llama-swap the baseline model is managed by
    TTL-based auto-unload and preload hooks in llama-swap.yaml — there
    is no profile state to restore.
    """
    print("[RESTORE_ROLE] No-op: llama-swap manages model lifecycle via TTL and preload hooks.")
