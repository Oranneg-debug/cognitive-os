import sys
from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter

def main():
    print("🧠 Antigravity Cognitive OS Initialized")
    print("---------------------------------------")
    
    # Initialize Core Systems
    orchestrator = Orchestrator()
    obsidian = ObsidianWriter()
    
    print("\nSystem ready. Enter your prompt (or type 'exit' to quit):")
    
    while True:
        try:
            user_input = input("\n> ")
            if user_input.strip().lower() in ['exit', 'quit']:
                break
            if not user_input.strip():
                continue
                
            print("\n⚙️ Processing request...")
            
            # Step 1: Routing & Execution
            result = orchestrator.process_request(user_input)
            
            # Step 2: Write to Obsidian
            # For SIMPLE/STANDARD, we don't have a task_id stored the same way, but let's mock it
            pattern = orchestrator.sentry.classify_request(user_input)["pattern"]
            title_preview = user_input[:30] + "..." if len(user_input) > 30 else user_input
            
            # Use a generic task_id if it's not boardroom
            task_id = orchestrator.memory.generate_task_id(user_input)
            
            obsidian.write_note(
                title=f"AI Output - {title_preview}",
                content=result,
                pattern_used=pattern,
                task_id=task_id
            )
            
            print("\n✅ Task Complete!")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
