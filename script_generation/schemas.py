"""脚本生成阶段：输出 schema（manim_code、image_prompts 等）。"""
from pydantic import BaseModel, Field


class ScriptGenerationOutput(BaseModel):
    """多模态脚本生成 LLM 输出。"""

    manim_code: str = Field(..., description="Manim Python 代码，含 SolutionScene 类和 self.wait() 占位")
    image_prompts: list[str] = Field(..., description="与步骤一一对应的图像提示词列表，用于可选 SD")
