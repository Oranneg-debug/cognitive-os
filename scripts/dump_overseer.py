"""Dump every key the overseer/chairman JSON contains."""
import io
import json
import re
import sys
from pathlib import Path

# Force UTF-8 stdout so emoji / arrows / dashes don't crash on Windows cp1252.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

p = Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
oa = d.get("oversight_analysis", {})
raw = oa.get("raw_analysis", "") if isinstance(oa, dict) else str(oa)

m = re.search(r"```json\s*(.+?)\s*```", raw, re.DOTALL)
if m:
    raw = m.group(1)

try:
    j = json.loads(raw)
except Exception as e:
    print(f"parse failed: {e}", file=sys.stderr)
    print(raw[:1000])
    sys.exit(1)

print("keys:", list(j.keys()))
print()
for k, v in j.items():
    print(f"== {k} ==")
    if isinstance(v, (dict, list)):
        print(json.dumps(v, indent=2)[:2000])
    else:
        print(str(v)[:2000])
    print()
