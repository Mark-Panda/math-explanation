"""请求/响应模型：题目字段、错误码、任务状态、结果 path/url。"""
from pydantic import BaseModel, Field


class GenerateVideoRequest(BaseModel):
    problem: str = Field(..., min_length=1, description="数学题目文本")


class GenerateVideoResponse(BaseModel):
    task_id: str = Field(..., description="任务 ID，用于轮询状态")
    status: str = Field("pending", description="pending | running | success | failed")


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str = Field(..., description="pending | running | success | failed")
    result_url: str | None = Field(None, description="成功时的结果 HTML 动画 URL（相对或绝对）")
    error: str | None = Field(None, description="失败时的错误信息")
    current_step: str | None = Field(None, description="当前执行步骤，用于前端进度显示")


class HistoryItem(BaseModel):
    task_id: str
    problem_preview: str = ""
    status: str
    result_path: str | None = None
    error: str | None = None
    created_at: str = ""


class RegenerateRequest(BaseModel):
    task_id: str = Field(..., description="要基于其题目重新生成的任务 ID")


class RegenerateResponse(BaseModel):
    task_id: str = Field(..., description="新任务 ID")
    status: str = Field(default="pending", description="pending")
