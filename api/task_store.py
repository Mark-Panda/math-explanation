"""内存任务状态存储：task_id -> status, result_path, error, current_step。与 history_store 联动持久化。"""
from dataclasses import dataclass
from typing import Optional
import uuid

from api.history_store import (
    create_record as history_create,
    update_problem as history_update_problem,
    update_progress as history_update_progress,
    update_status as history_update_status,
    get_record as history_get_record,
)

@dataclass
class TaskState:
    task_id: str
    status: str  # pending | running | success | failed
    result_path: Optional[str] = None
    error: Optional[str] = None
    current_step: Optional[str] = None  # 当前执行步骤，用于前端进度展示


_tasks: dict[str, TaskState] = {}


def create_task(problem_preview: str = "", problem_text: Optional[str] = None) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = TaskState(task_id=task_id, status="pending")
    history_create(task_id, problem_preview=problem_preview, problem_text=problem_text)
    return task_id


def set_running(task_id: str) -> None:
    """置为运行中；若任务不在内存（如断点重试从历史加载），先放入 _tasks 以便 set_progress/get_task 生效。"""
    if task_id not in _tasks:
        rec = history_get_record(task_id)
        if rec:
            _tasks[task_id] = TaskState(
                task_id=rec.task_id,
                status="running",
                result_path=rec.video_path,
                error=rec.error,
                current_step=None,
            )
        else:
            _tasks[task_id] = TaskState(task_id=task_id, status="running")
    else:
        _tasks[task_id].status = "running"
        _tasks[task_id].current_step = None
    history_update_status(task_id, "running")


def set_progress(task_id: str, current_step: str) -> None:
    """更新任务当前步骤，供前端进度显示；同时持久化以便断点重试时任意 worker 都能返回进度。"""
    if task_id in _tasks:
        _tasks[task_id].current_step = current_step
    history_update_progress(task_id, current_step)


def set_success(task_id: str, result_path: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = "success"
        _tasks[task_id].result_path = result_path
        _tasks[task_id].error = None
        _tasks[task_id].current_step = None
    history_update_status(task_id, "success", video_path=result_path)


def set_failed(task_id: str, error: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = "failed"
        _tasks[task_id].error = error
        _tasks[task_id].result_path = None
        _tasks[task_id].current_step = None
    history_update_status(task_id, "failed", error=error)


def update_task_problem(task_id: str, problem_text: str) -> None:
    """OCR 或流程中得到题目文本后更新历史记录，便于重新生成。"""
    history_update_problem(task_id, problem_text)


def get_task(task_id: str) -> Optional[TaskState]:
    """先查内存，未命中则从持久化历史恢复为 TaskState（无 current_step）。"""
    if task_id in _tasks:
        return _tasks[task_id]
    rec = history_get_record(task_id)
    if not rec:
        return None
    return TaskState(
        task_id=rec.task_id,
        status=rec.status,
        result_path=rec.video_path,
        error=rec.error,
        current_step=getattr(rec, "current_step", None),
    )


def delete_task(task_id: str) -> None:
    """从内存中移除任务（与删除历史记录时配合使用）。"""
    _tasks.pop(task_id, None)
