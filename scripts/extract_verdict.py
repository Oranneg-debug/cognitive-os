"""Extract a coherent verdict from a council_memory JSON file.

The scribe role keeps failing because LM Studio re-loads ministral at 8K
between roles. But the council_memory JSON has every individual role's
output recorded — the verdict IS there, we just have to assemble it ourselves.
"""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
d = json.loads(path.read_text(encoding="utf-8"))

print(f"=== TASK {d.get('task_id')} ===")
print(f"status:  {d.get('status')}")
print(f"pattern: {d.get('pattern_used')}")
print(f"created: {d.get('timestamp_created')}")
print(f"input first 200 chars: {(d.get('user_input') or '')[:200]}")
print()

ops = d.get("models_participated", [])
print(f"=== {len(ops)} ROLES ===\n")

for op in ops:
    role = op.get("role", "?")
    model = op.get("model_name", "?")
    ts = op.get("timestamp_completed", "?")
    raw = op.get("opinion", "")
    
    # Detect error opinions
    is_err = False
    if isinstance(raw, str) and raw.lstrip().startswith("{"):
        try:
            j = json.loads(raw)
            if "error" in j and "raw" in j:
                is_err = True
        except Exception:
            pass
    
    print(f"--- {role} ({model}) @ {ts} ---")
    if is_err:
        print("  [ROLE FAILED]")
        try:
            j = json.loads(raw)
            print(f"  error: {j.get('error', '')[:200]}")
            print(f"  raw:   {j.get('raw', '')[:300]}")
        except Exception:
            print(f"  unparseable: {raw[:300]}")
    else:
        # Try to extract a clean opinion
        if isinstance(raw, str) and raw.lstrip().startswith("{"):
            try:
                j = json.loads(raw)
                # Common shapes
                for key in ("verdict", "decision", "reasoning", "report", "synthesis",
                            "executive_summary", "approved", "technical_analysis",
                            "actionable_steps", "veto_points", "transition_reason",
                            "key_insight", "next_step"):
                    if key in j:
                        v = j[key]
                        if isinstance(v, (dict, list)):
                            v = json.dumps(v, indent=2)[:600]
                        print(f"  {key}: {v}")
            except Exception:
                print(f"  {raw[:600]}")
        else:
            print(f"  {str(raw)[:600]}")
    print()
