"""题目分析阶段：steps JSON 的 schema 定义。"""
from pydantic import BaseModel, Field


class StepItem(BaseModel):
    step_id: int = Field(..., description="步骤序号")
    description: str = Field(..., description="该步文字描述")
    math_formula: str = Field(..., description="LaTeX 格式公式，如 $x^2 + y^2 = r^2$")
    visual_focus: str = Field(..., description="需要突出的视觉元素")
    voiceover_text: str = Field(..., description="该步旁白文案")


class ProblemAnalysisOutput(BaseModel):
    """LLM 题目分析输出，与 spec 一致。"""

    steps: list[StepItem] = Field(..., description="解题步骤列表", min_length=1)
