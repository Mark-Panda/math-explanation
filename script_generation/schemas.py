"""脚本生成阶段：输出 schema（animation_html、image_prompts 等）。"""
from pydantic import BaseModel, Field


class StepAnimationPlan(BaseModel):
    """单步动画方案（第一阶段 LLM 输出）。"""
    step_id: int = Field(..., description="步骤序号")
    animation_description: str = Field(..., description="该步动画的具体视觉方案：显示什么、怎么动、用什么颜色等")
    image_prompt: str = Field(default="", description="该步的图像提示词")


class AnimationPlanOutput(BaseModel):
    """第一阶段：所有步骤的动画方案。"""
    shared_css: str = Field(default="", description="所有步骤共享的 CSS 样式代码")
    shared_svg: str = Field(default="", description="如果需要共享的 SVG 基础图形（如几何题的底图），放在这里")
    step_plans: list[StepAnimationPlan] = Field(..., description="每步的动画方案")


class StepCodeOutput(BaseModel):
    """第二阶段：单步的 animate 函数体 JS 代码。"""
    animate_body: str = Field(..., description="animate(container) 函数体的 JavaScript 代码（不含 function 声明）")


class ScriptGenerationOutput(BaseModel):
    """最终组装后的输出。"""
    animation_html: str = Field(..., description="自包含的 HTML/CSS/JS 动画代码片段，含 stepAnimations 数组和 STEP_PLACEHOLDER 占位")
    image_prompts: list[str] = Field(..., description="与步骤一一对应的图像提示词列表，用于可选 SD")
