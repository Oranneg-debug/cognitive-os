"""Verify what get_role_config returns for the key council roles."""
from src.orchestrator import get_role_config, MasterConfig

MasterConfig._load_config()
for r in ("simple", "scribe", "moderator", "brand_guard"):
    rc = get_role_config(r) or {}
    model = rc.get("model", "???")
    ctx = rc.get("context_window")
    gpu = rc.get("gpu_layers")
    print(f"{r:14s} model={model:55s} ctx={ctx} gpu_layers={gpu}")
