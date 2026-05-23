"""Extract the chairman's audit_report / definitive_blueprint / final_decision
from oversight_analysis.raw_analysis (which is markdown-wrapped JSON).
"""
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
d = json.loads(path.read_text(encoding="utf-8"))

raw_analysis = (d.get("oversight_analysis") or {}).get("raw_analysis", "")
# Strip ```json ... ``` markdown fence
m = re.search(r"```json\s*(.+?)\s*```", raw_analysis, re.DOTALL)
if m:
    raw_analysis = m.group(1)

try:
    chair = json.loads(raw_analysis)
except Exception as e:
    print(f"ERROR parsing chairman analysis: {e}", file=sys.stderr)
    print("--- raw text:")
    print(raw_analysis[:2000])
    sys.exit(1)

print("=" * 70)
print("CHAIRMAN'S VERDICT")
print("=" * 70)
print()
print("FINAL DECISION:")
print(f"  {chair.get('final_decision', '(missing)')}")
print()
print("AUDIT REPORT:")
print(chair.get("audit_report", "(missing)"))
print()
print("DEFINITIVE BLUEPRINT:")
print(chair.get("definitive_blueprint", "(missing)"))
print()
print("VETO POINTS (binding mandates):")
for vp in chair.get("veto_points", []):
    print(f"  - {vp}")
