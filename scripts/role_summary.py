"""One-line per role summary of a task JSON."""
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
print("status: ", d.get("status"))
print("pattern:", d.get("pattern_used"))
print()
print("=== roles ===")
for op in d.get("models_participated", []):
    role = op.get("role")
    ts = op.get("timestamp_completed")
    raw = str(op.get("opinion", ""))
    err = ""
    if raw.startswith("{") and ('"error"' in raw[:120] or "Error: Error code" in raw[:60]):
        err = " [FAILED]"
    print(f"  {ts} | {role:38s} | {len(raw):>6} chars{err}")
print()
oa = d.get("oversight_analysis", {})
raw_oa = oa.get("raw_analysis", "") if isinstance(oa, dict) else str(oa)
print("=== oversight_analysis raw (first 600) ===")
print(raw_oa[:600])
