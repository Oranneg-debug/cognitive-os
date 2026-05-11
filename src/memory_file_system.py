import json
import os
import hashlib
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class MemoryFileManager:
    """
    Manages JSON-based memory files for Sequential Boardroom pattern.
    Ensures that each model gives independent opinions without seeing previous outputs.
    """
    
    def __init__(self, base_path: str = "council_memory"):
        self.base_path = base_path
        self.active_path = os.path.join(base_path, "active")
        self.archived_path = os.path.join(base_path, "archived")
        
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directory structure"""
        for path in [self.active_path, self.archived_path]:
            os.makedirs(path, exist_ok=True)
            
    def generate_task_id(self, user_input: str) -> str:
        """Generate unique task ID based on input hash and timestamp"""
        input_hash = hashlib.md5(user_input.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"task_{timestamp}_{input_hash}"
        
    def init_task(self, task_id: str, user_input: str, pattern: str = "SEQUENTIAL_BOARDROOM"):
        """Initialize a new task file"""
        file_path = os.path.join(self.active_path, f"{task_id}.json")
        memory_data = {
            "task_id": task_id,
            "timestamp_created": datetime.now().isoformat(),
            "timestamp_completed": None,
            "user_input": user_input,
            "input_hash": hashlib.md5(user_input.encode()).hexdigest()[:8],
            "pattern_used": pattern,
            "models_participated": [],
            "oversight_analysis": {},
            "final_output_path": None,
            "status": "in_progress"
        }
        self._write_json(file_path, memory_data)
        
    def save_opinion(self, task_id: str, role: str, model_name: str, opinion_text: str):
        """Save a single model's opinion to the memory file"""
        file_path = os.path.join(self.active_path, f"{task_id}.json")
        memory_data = self._read_json(file_path)
        
        if not memory_data:
            print(f"Task {task_id} not found.")
            return False
            
        opinion_entry = {
            "role": role,
            "model_name": model_name,
            "timestamp_completed": datetime.now().isoformat(),
            "opinion": opinion_text
        }
        
        memory_data["models_participated"].append(opinion_entry)
        self._write_json(file_path, memory_data)
        return True
        
    def save_oversight_analysis(self, task_id: str, analysis: str):
        """Save the oversight model's cross-reference analysis"""
        file_path = os.path.join(self.active_path, f"{task_id}.json")
        memory_data = self._read_json(file_path)
        
        if memory_data:
            memory_data["oversight_analysis"] = {"raw_analysis": analysis}
            self._write_json(file_path, memory_data)
            
    def get_all_opinions(self, task_id: str) -> List[Dict]:
        """Extract just the opinions list from a task"""
        file_path = os.path.join(self.active_path, f"{task_id}.json")
        memory_data = self._read_json(file_path)
        if memory_data:
            return memory_data.get("models_participated", [])
        return []
        
    def complete_task(self, task_id: str, output_path: str = None):
        """Mark the entire task as completed and archive it"""
        file_path = os.path.join(self.active_path, f"{task_id}.json")
        memory_data = self._read_json(file_path)
        
        if not memory_data:
            return
            
        memory_data["timestamp_completed"] = datetime.now().isoformat()
        memory_data["status"] = "completed"
        if output_path:
            memory_data["final_output_path"] = output_path
            
        self._write_json(file_path, memory_data)
        
        # Archive
        today = datetime.now()
        archive_dir = os.path.join(self.archived_path, f"{today.year}-{today.month:02d}")
        os.makedirs(archive_dir, exist_ok=True)
        dest_path = os.path.join(archive_dir, f"{task_id}.json")
        shutil.move(file_path, dest_path)
        
    def _read_json(self, file_path: str) -> Optional[Dict]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
            
    def _write_json(self, file_path: str, data: Dict):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
