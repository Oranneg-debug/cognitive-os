import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter

app = FastAPI(title="Cognitive OS API")
orchestrator = Orchestrator()
obsidian = ObsidianWriter()

class PromptRequest(BaseModel):
    prompt: str

@app.post("/process")
def process_prompt(request: PromptRequest):
    """
    Receives a prompt from Obsidian or other interfaces,
    runs the Cognitive OS, and saves the result.
    Defined as 'def' instead of 'async def' so FastAPI 
    automatically runs this in a background thread to prevent blocking.
    """
    print(f"\n🌐 API Request Received: {request.prompt[:50]}...")
    
    # 1. Run Council
    result = orchestrator.process_request(request.prompt)
    
    # 2. Save to Obsidian
    pattern = orchestrator.sentry.classify_request(request.prompt)["pattern"]
    task_id = orchestrator.memory.generate_task_id(request.prompt)
    
    file_path = obsidian.write_note(
        title=f"API Request - {request.prompt[:20]}",
        content=result,
        pattern_used=pattern,
        task_id=task_id
    )
    
    return {
        "status": "success",
        "pattern": pattern,
        "task_id": task_id,
        "saved_path": file_path,
        "response": result
    }

def main():
    print("🌐 Starting FastAPI Server on port 5000...")
    uvicorn.run("src.api:app", host="1234", port=5000, reload=True) # host="0.0.0.0" to allow network access

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000)
