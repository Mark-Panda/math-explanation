"""内存任务状态存储：task_id -> status, video_path, error。"""
from dataclasses import dataclass
from typing import Optional
import uuid

@dataclass
class TaskState:
    task_id: str
    status: str  # pending | running | success | failed
    video_path: Optional[str] = None
    error: Optional[str] = None


_tasks: dict[str, TaskState] = {}


def create_task() -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = TaskState(task_id=task_id, status="pending")
    return task_id


def set_running(task_id: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = "running"


def set_success(task_id: str, video_path: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = "success"
        _tasks[task_id].video_path = video_path
        _tasks[task_id].error = None


def set_failed(task_id: str, error: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = "failed"
        _tasks[task_id].error = error
        _tasks[task_id].video_path = None


def get_task(task_id: str) -> Optional[TaskState]:
    return _tasks.get(task_id)
