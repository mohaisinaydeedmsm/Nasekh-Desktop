import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

@dataclass
class TaskItem:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = "unknown"
    status: str = "pending" # pending, processing, completed, failed
    payload: Dict[str, Any] = field(default_factory=dict)

class TaskManager:
    def __init__(self, queue_file: str = "queue_state.json"):
        self.queue_file = queue_file
        self.tasks: List[TaskItem] = []

    def add_task(self, task_type: str, payload: Dict[str, Any]) -> str:
        new_task = TaskItem(task_type=task_type, payload=payload)
        self.tasks.append(new_task)
        return new_task.task_id

    def remove_task(self, task_id: str) -> bool:
        initial_len = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.task_id != task_id]
        return len(self.tasks) < initial_len

    def update_task_status(self, task_id: str, new_status: str) -> bool:
        for t in self.tasks:
            if t.task_id == task_id:
                t.status = new_status
                return True
        return False

    def get_pending_tasks(self) -> List[TaskItem]:
        return [t for t in self.tasks if t.status == "pending"]

    def save_queue(self):
        try:
            with open(self.queue_file, "w", encoding="utf-8") as f:
                json.dump([asdict(t) for t in self.tasks], f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save queue state: {e}")

    def load_queue(self):
        if not os.path.exists(self.queue_file):
            return
        
        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.tasks = []
            for item in data:
                task = TaskItem(**item)
                # Reset processing tasks to pending so they can be resumed
                if task.status == "processing":
                    task.status = "pending"
                self.tasks.append(task)
        except Exception as e:
            print(f"Failed to load queue state: {e}")
