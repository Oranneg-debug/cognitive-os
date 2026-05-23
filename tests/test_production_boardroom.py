import sys
import os
import pytest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.orchestrator import Orchestrator
from src.llm_client import llm

# This test fires a REAL boardroom council with live LLM calls, takes
# ~5-10 minutes, costs significant GPU time, and creates artifacts in
# council_memory/ and the vault. It is NOT a unit test — it is a manual
# smoke script. Skipped by default to keep `pytest tests/` fast and side-
# effect free. Run explicitly with:
#   pytest tests/test_production_boardroom.py -m manual --run-live-council
# or:
#   python tests/test_production_boardroom.py
@pytest.mark.manual
@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_COUNCIL"),
    reason="Live council smoke test; set RUN_LIVE_COUNCIL=1 to enable. "
           "Fires a real boardroom (~5-10 min, GPU heavy, writes artifacts).",
)
def test_production_boardroom():
    print("INITIALIZING PRODUCTION BOARDROOM TEST...")
    orchestrator = Orchestrator()
    
    user_input = "Develop a strategic plan for a high-end tattoo studio called 'The Obsidian Quill' that focuses on bio-mechanical dark realism and uses AI-generated concept art."
    
    print(f"\nUser Input: {user_input}\n")
    
    def progress_callback(msg):
        print(f"[{msg}]")

    try:
        report = orchestrator.execute_sequential_boardroom(
            user_input=user_input,
            progress_callback=progress_callback,
            compass_weight="MAXIMUM"
        )
        
        print("\n" + "="*50)
        print("MASTER REPORT GENERATED")
        print("="*50)
        print(report)
        print("="*50)
        
    except Exception as e:
        print(f"TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_production_boardroom()
