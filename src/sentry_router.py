import requests
import psutil
from datetime import datetime
from typing import Dict

class SentryRouter:
    """
    Pattern Selector for Cognitive OS Orchestrator.
    Routes requests to one of five orchestration patterns.
    """
    
    def __init__(self):
        self.patterns = {
            "SIMPLE": "Single model pass, Reflex Layer",
            "STANDARD": "Single model + preset, Operational Brain",
            "SMALL_COUNCIL": "Draft → Refine → Synthesize pipeline",
            "SEQUENTIAL_BOARDROOM": "Local: Independent opinions + memory file",
            "ONLINE_BOARDROOM": "Frontier models via API (Parallel)"
        }
        
    def classify_request(self, user_input: str) -> Dict[str, any]:
        """Main classification function"""
        complexity = self._assess_complexity(user_input)
        is_online = self._check_connectivity()
        available_vram_gb = self._get_available_vram()
        
        pattern = self._select_pattern(complexity, is_online, available_vram_gb)
        
        return {
            "pattern": pattern,
            "complexity": complexity,
            "is_online": is_online,
            "available_vram_gb": available_vram_gb,
            "timestamp": datetime.now().isoformat()
        }
        
    def _assess_complexity(self, text: str) -> str:
        low_keywords = ["tag", "summary", "extract", "convert", "format", "clean", "organize", "list", "count"]
        medium_keywords = ["write", "concept", "design", "idea", "draft", "journal", "story", "poem", "creative", "tattoo"]
        high_keywords = ["strategy", "plan", "system", "analysis", "decision", "architecture", "design", "framework", "roadmap", "business", "life systems", "future"]
        
        text_lower = text.lower()
        low_count = sum(1 for kw in low_keywords if kw in text_lower)
        medium_count = sum(1 for kw in medium_keywords if kw in text_lower)
        high_count = sum(1 for kw in high_keywords if kw in text_lower)
        
        length_score = len(text.split()) / 50
        
        if high_count >= 2 or (high_count >= 1 and length_score > 3):
            return "high"
        elif medium_count >= 2 or (medium_count >= 1 and low_count == 0):
            return "medium"
        else:
            return "low"
            
    def _check_connectivity(self) -> bool:
        try:
            response = requests.get("https://www.google.com", timeout=3)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
            
    def _get_available_vram(self) -> float:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # Try to parse up to 2 GPUs (Dual RTX 3090)
                total_free = 0.0
                for line in lines:
                    free_mb = float(line.split(',')[0])
                    total_free += free_mb / 1024
                return round(total_free, 2)
            return 48.0
        except Exception:
            return 48.0 # Fallback
            
    def _select_pattern(self, complexity: str, is_online: bool, vram_gb: float) -> str:
        if complexity == "low":
            return "SIMPLE"
        elif complexity == "medium":
            return "STANDARD"
        else:
            if is_online:
                return "ONLINE_BOARDROOM"
            else:
                if vram_gb >= 42:
                    return "SEQUENTIAL_BOARDROOM"
                else:
                    return "SMALL_COUNCIL"
