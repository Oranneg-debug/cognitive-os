import os
import requests
from openai import OpenAI
from typing import Optional

class LLMClient:
    """
    Wrapper for LM Studio API (OpenAI compatible).
    Connects to the local server, typically at http://localhost:1234/v1
    """
    
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", api_key: str = "lm-studio"):
        # LM Studio acts as a drop-in replacement for OpenAI
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        
    def generate_response(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None, 
        model: str = "local-model",
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        max_tokens: int = 2048,
        context_window: int = 8192,
        gpu_layers: int = -1,
        image_base64: Optional[str] = None
    ) -> str:
        """
        Generate a response using the local LLM.
        """
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
            host_url = f"{self.client.base_url.scheme}://{self.client.base_url.host}:{self.client.base_url.port}"
            load_url = f"{host_url}/api/v1/models/load"
            
            # Map -1 to 'max' for LM Studio's preferred offload ratio, but also provide gpu_layers
            gpu_ratio = "max" if gpu_layers == -1 else None
            
            load_payload = {
                "model": model,
                "config": {
                    "contextLength": context_window,
                    "context_window": context_window,  # Provided as fallback
                    "gpuOffloadRatio": gpu_ratio,
                    "gpu_layers": gpu_layers           # Provided as fallback
                }
            }
            requests.post(load_url, json=load_payload, timeout=600)
        except Exception as e:
            print(f"⚠️ Could not explicitly load model parameters: {e}")

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
                    "repeat_penalty": repeat_penalty
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
            
            # Construct the LM Studio specific admin API URL
            # e.g. http://192.168.1.223:1234/api/v1/models/unload
            host_url = f"{self.client.base_url.scheme}://{self.client.base_url.host}:{self.client.base_url.port}"
            unload_url = f"{host_url}/api/v1/models/unload"
            
            for model in loaded_models.data:
                model_id = model.id
                
                # Protect embedding models from being unloaded so RAG stays functional
                if "embed" in model_id.lower():
                    print(f"🛡️ Skipping unload of embedder model: {model_id}")
                    continue
                    
                requests.post(unload_url, json={"instance_id": model_id}, timeout=5)
                print(f"🧹 Unloaded model: {model_id}")
                
        except Exception as e:
            print(f"⚠️ Could not eject models: {e}")

# Singleton instance for easy import
llm = LLMClient()
