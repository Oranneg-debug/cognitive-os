import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Cognitive OS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
    
    # 2. Save to mock Obsidian vault (for backup/logging)
    pattern = orchestrator.sentry.classify_request(request.prompt)["pattern"]
    task_id = orchestrator.memory.generate_task_id(request.prompt)
    
    file_path = obsidian.write_note(
        title=f"API Request - {request.prompt[:20]}",
        content=result,
        pattern_used=pattern,
        task_id=task_id
    )

    # 3. Retrieve full memory task data to return to the frontend
    task_data = orchestrator.memory.get_task_data(task_id)
    
    return {
        "status": "success",
        "pattern": pattern,
        "task_id": task_id,
        "saved_path": file_path,
        "response": result,
        "opinions": task_data.get("models_participated", []),
        "oversight": task_data.get("oversight_analysis", {}).get("raw_analysis", "")
    }

def main():
    print("🌐 Starting FastAPI Server on port 5000...")
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000, reload=True)

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000)
