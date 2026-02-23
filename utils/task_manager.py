import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime
import uuid


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class GenerationTask:
    task_id: str
    message_id: str
    chat_id: str
    user_id: str
    status: TaskStatus = TaskStatus.PENDING
    events: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    stop_requested: bool = False
    thread: Optional[threading.Thread] = None
    
    def add_event(self, event: Dict[str, Any]):
        self.events.append(event)
        self.updated_at = datetime.utcnow()
    
    def request_stop(self):
        self.stop_requested = True
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "status": self.status.value,
            "event_count": len(self.events),
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "stop_requested": self.stop_requested,
        }


class TaskManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._tasks: Dict[str, GenerationTask] = {}
        self._message_to_task: Dict[str, str] = {} 
        self._cleanup_interval = 3600 
        self._initialized = True
        
       
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        def cleanup_worker():
            while True:
                time.sleep(self._cleanup_interval)
                self._cleanup_old_tasks()
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_old_tasks(self):
        now = datetime.utcnow()
        to_remove = []
        
        for task_id, task in self._tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.STOPPED, TaskStatus.ERROR]:
                age = (now - task.updated_at).total_seconds()
                if age > self._cleanup_interval:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            self._remove_task(task_id)
    
    def _remove_task(self, task_id: str):
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if task.message_id in self._message_to_task:
                del self._message_to_task[task.message_id]
            del self._tasks[task_id]
    
    def create_task(self, message_id: str, chat_id: str, user_id: str) -> GenerationTask:
        task_id = str(uuid.uuid4())
        task = GenerationTask(
            task_id=task_id,
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
        )
        
        self._tasks[task_id] = task
        self._message_to_task[message_id] = task_id
        
        return task
    
    def get_task(self, task_id: str) -> Optional[GenerationTask]:
        return self._tasks.get(task_id)
    
    def get_task_by_message_id(self, message_id: str) -> Optional[GenerationTask]:
        task_id = self._message_to_task.get(message_id)
        if task_id:
            return self._tasks.get(task_id)
        return None
    
    def stop_task(self, message_id: str) -> bool:
        task = self.get_task_by_message_id(message_id)
        if task and task.status == TaskStatus.RUNNING:
            task.request_stop()
            return True
        return False

task_manager = TaskManager()
