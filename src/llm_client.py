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
    """
    
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
        image_base64: Optional[str] = None
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
        
        # 1. Explicitly load the model with load-time parameters (structural configuration)
        try:
            # Detect if model is already loaded to avoid redundant calls
            loaded_models = self.client.models.list()
            is_loaded = any(m.id == model for m in loaded_models.data)
            
            if not is_loaded:
                host_url = f"{self.client.base_url.scheme}://{self.client.base_url.host}:{self.client.base_url.port}"
                load_url = f"{host_url}/api/v1/models/load"
                
                # Map -1 to 'max' for LM Studio's preferred offload ratio
                gpu_ratio = "max" if gpu_layers == -1 else None
                
                load_payload = {
                    "model": model,
                    "config": {
                        "contextLength": context_window,
                        "context_window": context_window,
                        "gpuOffloadRatio": gpu_ratio,
                        "gpu_layers": gpu_layers
                    }
                }
                requests.post(load_url, json=load_payload, timeout=600)
                print(f"[LOADED] JIT Loaded: {model} (Context: {context_window}, GPU: {gpu_layers if gpu_layers != -1 else 'max'})")
        except Exception as e:
            print(f"[WARNING] Could not explicitly load model parameters: {e}")

        # 2. Execute the inference request (execution metrics only)
        try:
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
            
    def eject_all_models(self):
        """
        Unload all currently loaded models from LM Studio to free VRAM.
        Uses LM Studio's specific /api/v1/models/unload endpoint.
        """
        try:
            # Get list of currently loaded models via OpenAI standard endpoint
            loaded_models = self.client.models.list()
            
            host_url = f"{self.client.base_url.scheme}://{self.client.base_url.host}:{self.client.base_url.port}"
            unload_url = f"{host_url}/api/v1/models/unload"
            
            for model in loaded_models.data:
                model_id = model.id
                
                # Protect embedding models from being unloaded so RAG stays functional
                if "embed" in model_id.lower():
                    print(f"[SHIELD] Skipping unload of embedder model: {model_id}")
                    continue
                    
                requests.post(unload_url, json={"instance_id": model_id}, timeout=5)
                print(f"[UNLOADED] Unloaded model: {model_id}")
                
        except Exception as e:
            print(f"[WARNING] Could not eject models: {e}")

# Singleton instance for easy import
llm = LLMClient()
