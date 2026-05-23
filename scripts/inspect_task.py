"""Quick inspector for an active council task JSON."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
d = json.loads(path.read_text(encoding="utf-8"))

print("status:", d.get("status"))
print("pattern:", d.get("pattern_used"))
print("user_input first 200:", (d.get("user_input") or "")[:200])
print()
print(f"=== ROLES SO FAR ({len(d.get('models_participated', []))}) ===")
for op in d.get("models_participated", []):
    role = op.get("role")
    model = op.get("model_name")
    ts = op.get("timestamp_completed")
    raw = op.get("opinion", "")
    err = None
    if isinstance(raw, str) and '"error"' in raw[:400]:
        try:
            j = json.loads(raw)
            err = j.get("error") or j.get("raw")
        except Exception:
            err = raw[:300]
    print(f"  {ts} | {role:38s} | {model}")
    if err:
        print(f"    ERROR: {str(err)[:300]}")
