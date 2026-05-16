import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.orchestrator import Orchestrator
from src.llm_client import llm

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
