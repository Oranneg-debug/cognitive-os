import requests
import psutil
from datetime import datetime
from typing import Dict

class SentryRouter:
    """
    Pattern Selector for Cognitive OS Orchestrator.
    Routes requests to one of six orchestration patterns.
    """
    
    def __init__(self):
        self.patterns = {
            "SIMPLE": "Single model pass, Reflex Layer",
            "STANDARD": "Single model + preset, Operational Brain",
            "TECHNICAL_MEETING": "Draft (Specialist) → Expand (Creative) → Refine (Critic) → Synthesize pipeline",
            "DESIGN_MEETING": "Draft (junior_designer) → Expand (creative_expansionist) → Refine (Critic) → Synthesize + Image Prompts (senior_designer)",
            "SEQUENTIAL_BOARDROOM": "Local: Independent opinions + memory file",
            "ORACLE_COUNCIL": "Strategic oversight with MAXIMUM compass (local or online frontier models)",
            "NFT_CREATION": "NFT Metadata generation + Minting simulation",
            "DEVELOPMENT_LIFECYCLE": "Dev proposal → Beta review → Alpha polish → Finalize release"
        }
        
    def classify_request(self, user_input: str) -> Dict[str, any]:
        """Main classification function"""
        complexity, domain = self._assess_complexity(user_input)
        is_online = self._check_connectivity()
        available_vram_gb = self._get_available_vram()
        
        pattern = self._select_pattern(complexity, domain, is_online, user_input)
        
        return {
            "pattern": pattern,
            "complexity": complexity,
            "domain": domain,
            "is_online": is_online,
            "available_vram_gb": available_vram_gb,
            "timestamp": datetime.now().isoformat()
        }
        
    def _assess_complexity(self, text: str) -> tuple[str, str]:
        low_keywords = ["tag", "summary", "extract", "convert", "format", "clean", "organize", "list", "count"]
        
        # Domains
        creative_keywords = ["design", "idea", "creative", "tattoo", "brainstorm", "concept", "story", "poem", "art", "visualize", "nft", "mint", "crypto"]
        technical_keywords = ["code", "script", "refactor", "bug", "technical", "implement", "function", "optimize", "system", "architecture"]
        strategic_keywords = ["strategy", "plan", "analysis", "decision", "framework", "roadmap", "business", "life systems", "future", "boardroom", "comprehensive"]
        
        text_lower = text.lower()
        
        low_count = sum(1 for kw in low_keywords if kw in text_lower)
        creative_count = sum(1 for kw in creative_keywords if kw in text_lower)
        technical_count = sum(1 for kw in technical_keywords if kw in text_lower)
        strategic_count = sum(1 for kw in strategic_keywords if kw in text_lower)
        
        domain_counts = {"creative": creative_count, "technical": technical_count, "strategic": strategic_count}
        domain = max(domain_counts, key=domain_counts.get)
        if domain_counts[domain] == 0:
            domain = "technical" # default
            
        total_high_med = creative_count + technical_count + strategic_count
        length_score = len(text.split()) / 50
        
        if strategic_count >= 2 or total_high_med >= 3 or (total_high_med >= 1 and length_score > 3):
            complexity = "high"
        elif total_high_med >= 1 or length_score > 1:
            complexity = "medium"
        else:
            complexity = "low"
            
        text_lower_stripped = text_lower.strip()
        # Overrides based on explicit user requests (Slash/Hash commands for Obsidian)
        if text_lower_stripped.startswith("/design") or text_lower_stripped.startswith("#design") or text_lower_stripped.startswith("/creative") or text_lower_stripped.startswith("design meeting") or text_lower_stripped.startswith("design council") or text_lower_stripped.startswith("creative council"):
            complexity = "high"
            domain = "creative"
        elif text_lower_stripped.startswith("/technical") or text_lower_stripped.startswith("#technical") or text_lower_stripped.startswith("/small") or text_lower_stripped.startswith("technical meeting") or text_lower_stripped.startswith("small council") or text_lower_stripped.startswith("technical council"):
            complexity = "high"
            domain = "technical"
        elif text_lower_stripped.startswith("/oracle") or text_lower_stripped.startswith("#oracle"):
            complexity = "high"
            domain = "oracle"
        elif text_lower_stripped.startswith("/boardroom") or text_lower_stripped.startswith("#boardroom") or text_lower_stripped.startswith("/strategic") or text_lower_stripped.startswith("boardroom"):
            complexity = "high"
            domain = "strategic"
        elif text_lower_stripped.startswith("/simple") or text_lower_stripped.startswith("#simple") or text_lower_stripped.startswith("/vision") or text_lower_stripped.startswith("#vision"):
            complexity = "low"
            domain = "technical"
        elif text_lower_stripped.startswith("/standard") or text_lower_stripped.startswith("#standard"):
            complexity = "medium"
            domain = "technical"
        elif text_lower_stripped.startswith("/nft") or text_lower_stripped.startswith("#nft") or text_lower_stripped.startswith("nft creation"):
            complexity = "high"
            domain = "creative"
        elif text_lower_stripped.startswith("/dev") or text_lower_stripped.startswith("#dev") or text_lower_stripped.startswith("development lifecycle") or text_lower_stripped.startswith("dev route"):
            complexity = "high"
            domain = "technical"
            
        return complexity, domain
            
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
        
    def _select_pattern(self, complexity: str, domain: str, is_online: bool, user_input: str = "") -> str:
        text_lower = user_input.lower().strip()

        # Explicitly check for command prefixes first
        if text_lower.startswith("#boardroom") or text_lower.startswith("/boardroom"):
            return "SEQUENTIAL_BOARDROOM"
        if text_lower.startswith("#design") or text_lower.startswith("/design"):
            return "DESIGN_MEETING"
        if text_lower.startswith("#technical") or text_lower.startswith("/technical"):
            return "TECHNICAL_MEETING"
        if text_lower.startswith("#oracle") or text_lower.startswith("/oracle"):
            return "ORACLE_COUNCIL"
        if text_lower.startswith("#dev") or text_lower.startswith("/dev"):
            return "DEVELOPMENT_LIFECYCLE"
        if text_lower.startswith("#nft") or text_lower.startswith("/nft") or text_lower.startswith("nft creation"):
            return "NFT_CREATION"
            
        if complexity == "low":
            return "SIMPLE"
        elif complexity == "medium":
            return "STANDARD"
        else:
            # ORACLE_COUNCIL handles both local and online frontier models
            if domain == "strategic" or domain == "oracle":
                return "ORACLE_COUNCIL"
            elif domain == "creative":
                return "DESIGN_MEETING"
            else:
                return "TECHNICAL_MEETING"
