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
    video_url: str | None = Field(None, description="成功时的结果视频 URL（相对或绝对）")
    error: str | None = Field(None, description="失败时的错误信息")
