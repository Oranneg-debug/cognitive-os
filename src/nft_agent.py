import logging
import json
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from src.llm_client import llm

logger = logging.getLogger(__name__)

@dataclass
class NFTMetadata:
    name: str
    description: str
    traits: Dict[str, Any]
    theme: str
    image_prompt: Optional[str] = None
    token_id: Optional[str] = None
    minted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)

class NFTAgent:
    """
    NFT Agent Module for Cognitive OS.
    Handles metadata generation, rarity logic, and 'minting' orchestration.
    Aligned with the 'Dark Maestro' aesthetic.
    """
    
    # Predefined pools for fallback generation (Dark Maestro themed)
    FALLBACK_NAMES = [
        "The Obsidian Codex", "Whisper of the Hollow Crown",
        "Sigil of the Silent Choir", "Veil of Ash and Amber"
    ]
    
    FALLBACK_TRAITS = {
        "Essence": "Ethereal Shadow",
        "Artifact": "Rusted Reliquary",
        "Sigil": "The Weeping Crown",
        "Chant": "Lament of the Forgotten",
        "Rarity": "Mythic"
    }

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    def _infer_darkness_level(self, compass_weight: Any) -> Dict[str, Any]:
        """Map compass_weight to thematic descriptors and intensity modifiers."""
        # Handle cases where compass_weight might be a string like "IGNORE" or None
        if compass_weight == "IGNORE" or compass_weight is None:
            darkness = 0.5
        else:
            try:
                darkness = max(0.0, min(1.0, float(compass_weight)))
            except (ValueError, TypeError):
                darkness = 0.5
        
        # Tone & imagery scaling
        tone_prefixes = {
            "luminal": ("Subtle", "Scholarly", "Muted"),
            "balanced": ("Ethereal", "Ancient", "Balanced"),
            "umbra": ("Infernal", "Apocalyptic", "Blazing")
        }
        
        if darkness < 0.33:
            prefix = tone_prefixes["luminal"]
            intensity = "subtle"
        elif darkness < 0.67:
            prefix = tone_prefixes["balanced"]
            intensity = "moderate"
        else:
            prefix = tone_prefixes["umbra"]
            intensity = "severe"

        return {
            "prefix": prefix,
            "intensity": intensity,
            "darkness": darkness
        }

    def _extract_json(self, text: str) -> str:
        """Extract the most plausible JSON object from LLM output."""
        # Try to find markdown code blocks first
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if not json_match:
            # Fallback to finding anything that looks like a JSON object
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        
        if json_match:
            return json_match.group(1 if "```json" in text else 0).strip()
        
        # Last-resort: try to parse the whole string
        try:
            json.loads(text.strip())
            return text.strip()
        except:
            raise ValueError("No valid JSON found in response")

    def generate_metadata(self, theme: str, context: str = "", compass_weight: Any = 0.5) -> NFTMetadata:
        """
        Generate rich NFT metadata with dynamic darkness scaling.
        """
        logger.info(f"NFT Agent: Generating metadata for theme: {theme} (Weight: {compass_weight})")
        
        # Infer darkness profile
        darkness_info = self._infer_darkness_level(compass_weight)
        prefix = darkness_info["prefix"][0]
        intensity = darkness_info["intensity"]
        
        # Build dynamic prompt with darkness modulation
        prompt = f"""
        Generate rich NFT metadata for the theme: "{theme}"
        Context: {context or "None provided."}
        
        Darkness Intensity: {intensity} ({prefix})
        
        Return a JSON object with:
        - "name": A {prefix} yet evocative title (e.g., "The Gilded Tomb of Silent Kings").
        - "description": A poetic, atmospheric paragraph (3-4 sentences) that evokes Gothic grandeur,
          occult symbolism, and high-prestige mystique. Use rich metaphors and archaic diction.
        - "traits": A dictionary with keys: "Essence", "Artifact", "Sigil", "Chant", "Rarity".
        - "image_prompt": A detailed Midjourney/DALL-E prompt (>= 20 words) that captures the
          {intensity} essence of the theme. Include lighting, texture, and mood cues.
          
        Requirements:
        * Avoid clichés like 'dark lord' or 'zombie'. Aim for sophistication.
        * For {intensity} darkness: Use stark contrasts (light/shadow), decay motifs,
          and esoteric references (e.g., alchemy, forgotten gods).
        """
        
        try:
            response_raw = llm.generate_response(
                prompt=prompt,
                system_prompt="You are a Dark Maestro - a master of gothic aesthetics, occult scholarship, and NFT curation.",
                model="qwen3-coder-next",
                temperature=0.85
            )
            
            json_str = self._extract_json(response_raw)
            data = json.loads(json_str)
            
        except Exception as e:
            logger.error(f"NFT Agent: Generation failed: {e}. Using fallback.")
            data = {
                "name": self.FALLBACK_NAMES[0],
                "description": f"A relic from the {darkness_info['prefix'][1]} archives, veiled in {darkness_info['prefix'][2]} shadows.",
                "traits": self.FALLBACK_TRAITS,
                "image_prompt": f"An ornate obsidian tablet etched with {darkness_info['prefix'][0].lower()} sigils, lit by a single candle in total darkness."
            }
        
        # Ensure traits are present
        if not isinstance(data.get("traits"), dict):
            data["traits"] = self.FALLBACK_TRAITS.copy()
            
        return NFTMetadata(
            name=data.get("name", "Untitled"),
            description=data.get("description", ""),
            traits=data.get("traits", {}),
            theme=theme,
            image_prompt=data.get("image_prompt", "")
        )

    def mint_mock(self, metadata: NFTMetadata) -> str:
        """
        Simulates minting on the blockchain.
        """
        token_id = f"ANT-{uuid.uuid4().hex[:8].upper()}"
        metadata.token_id = token_id
        metadata.minted_at = datetime.now().isoformat()
        logger.info(f"NFT Minted: {token_id}")
        return token_id

    def process_creation(self, theme: str, context: str = "", compass_weight: Any = 0.5) -> Dict[str, Any]:
        """
        Full lifecycle: Metadata -> (In future: Image) -> Mint
        """
        # 1. Generate Metadata
        metadata = self.generate_metadata(theme, context, compass_weight)
        
        # 2. Simulate Minting
        self.mint_mock(metadata)
        
        return metadata.to_dict()
