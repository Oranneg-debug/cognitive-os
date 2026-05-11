import os
import requests
from openai import OpenAI
from typing import Optional

class LLMClient:
    """
    Wrapper for LM Studio API (OpenAI compatible).
    Connects to the local server, typically at http://localhost:1234/v1
    """
    
    def __init__(self, base_url: str = "http://192.168.1.223:1234/v1", api_key: str = "lm-studio"):
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
        max_tokens: int = 2048
    ) -> str:
        """
        Generate a response using the local LLM.
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body={"top_k": top_k} # Passes top_k directly to LM Studio
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
                requests.post(unload_url, json={"instance_id": model_id}, timeout=5)
                print(f"🧹 Unloaded model: {model_id}")
                
        except Exception as e:
            print(f"⚠️ Could not eject models: {e}")

# Singleton instance for easy import
llm = LLMClient()
