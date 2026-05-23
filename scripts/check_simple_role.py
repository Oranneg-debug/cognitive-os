"""Quick check: what command will _restore_default_state generate now?"""
from src.orchestrator import get_role_config, MasterConfig

MasterConfig._load_config()  # force re-read
rc = get_role_config("simple") or {}
print(f"simple context_window: {rc.get('context_window')}")
print(f"simple gpu_layers:     {rc.get('gpu_layers')}")
print(f"simple model:          {rc.get('model')}")
print()
ctx = rc.get("context_window") or rc.get("context_length") or 32768
gpu_layers = rc.get("gpu_layers", 0)
if gpu_layers == 0:
    gpu_flag = "--gpu off"
elif gpu_layers == -1:
    gpu_flag = "--gpu max"
else:
    gpu_flag = ""
cmd = f"lms load {rc['model']} -c {int(ctx)} {gpu_flag} -y".strip()
print(f"NEW GENERATED CMD: {cmd}")
