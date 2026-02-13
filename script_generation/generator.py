"""多模态脚本生成：generate_manim_code_and_prompts(steps_data)。支持传入原图辅助 Manim 代码生成。"""
from config import get_settings
from llm_runner import invoke_multimodal_structured, invoke_structured

from problem_analysis.schemas import StepItem

from .schemas import ScriptGenerationOutput

SCRIPT_PROMPT = """基于以下解题步骤，生成两部分内容：
1. Manim Python 代码：用于绘制数学图形和动画。必须包含一个名为 SolutionScene 的类，在 construct 方法中按步骤实现子动画，每个步骤后用 self.wait() 占位（我们会根据语音时长替换）。
2. image_prompts：与每个步骤一一对应的图像提示词列表，风格为数学教科书、极简、白色背景，用于可选的概念图生成。

解题步骤数据（JSON）:
{steps_json}

要求：
- 输出为结构化数据：manim_code（字符串）、image_prompts（字符串列表，长度与步骤数相同）。
- Manim 代码中必须出现 SolutionScene 和 self.wait()。
"""

SCRIPT_PROMPT_WITH_IMAGE = """基于以下解题步骤和附带的原始题目图片，生成两部分内容：
1. Manim Python 代码：用于绘制数学图形和动画。必须包含一个名为 SolutionScene 的类，在 construct 方法中按步骤实现子动画，每个步骤后用 self.wait() 占位（我们会根据语音时长替换）。
2. image_prompts：与每个步骤一一对应的图像提示词列表，风格为数学教科书、极简、白色背景，用于可选的概念图生成。

解题步骤数据（JSON）:
{steps_json}

**重要 - 图形与公式准确性要求**：
请仔细观察附带的原始题目图片，确保 Manim 代码中：
1. **几何图形**必须与原图一致：顶点位置、标注字母、角度、边长、虚线/实线等
2. **坐标系和函数图像**必须还原原图中的坐标范围、刻度、函数形状
3. **公式渲染**使用 MathTex/Tex，LaTeX 语法必须与原图中的公式完全一致
4. **标注和辅助元素**（如角标记、平行标记、阴影区域）需要在动画中体现
5. 图形的比例和相对位置关系应尽量还原原图

要求：
- 输出为结构化数据：manim_code（字符串）、image_prompts（字符串列表，长度与步骤数相同）。
- Manim 代码中必须出现 SolutionScene 和 self.wait()。
"""


def _steps_to_dict_list(steps: list[StepItem]) -> list[dict]:
    return [
        {
            "step_id": s.step_id,
            "description": s.description,
            "math_formula": s.math_formula,
            "visual_focus": s.visual_focus,
            "voiceover_text": s.voiceover_text,
        }
        for s in steps
    ]


def generate_manim_code_and_prompts(
    steps: list[StepItem],
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
) -> ScriptGenerationOutput:
    """
    校验 steps 非空且每项含必需字段后，通过 LangChain 调用 LLM，返回 manim_code 与 image_prompts。
    当提供 image_base64 时，使用多模态调用让 LLM 同时看到原图以生成更准确的图形和公式代码。
    若 image_prompts 长度与 steps 不一致，补齐或截断到与 steps 一致。
    """
    if not steps:
        raise ValueError("steps 不能为空")
    for i, s in enumerate(steps):
        if not isinstance(s, StepItem):
            raise ValueError(f"steps[{i}] 需为 StepItem")
        if not (s.description and s.voiceover_text):
            raise ValueError(f"steps[{i}] 缺少 description 或 voiceover_text")
    import json
    steps_json = json.dumps(_steps_to_dict_list(steps), ensure_ascii=False, indent=2)
    script_timeout = get_settings().llm_script_timeout

    if image_base64:
        prompt = SCRIPT_PROMPT_WITH_IMAGE.format(steps_json=steps_json)
        result: ScriptGenerationOutput = invoke_multimodal_structured(
            prompt,
            ScriptGenerationOutput,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            timeout=script_timeout,
        )
    else:
        prompt = SCRIPT_PROMPT.format(steps_json=steps_json)
        result = invoke_structured(prompt, ScriptGenerationOutput, timeout=script_timeout)

    # 与步骤数一致：补齐或截断
    n = len(steps)
    if len(result.image_prompts) < n:
        result.image_prompts.extend([""] * (n - len(result.image_prompts)))
    elif len(result.image_prompts) > n:
        result.image_prompts = result.image_prompts[:n]
    # 返回格式校验：必须包含 SolutionScene 和 self.wait()
    if "SolutionScene" not in result.manim_code:
        raise ValueError("LLM 返回的 manim_code 中未包含 SolutionScene")
    if "self.wait()" not in result.manim_code:
        raise ValueError("LLM 返回的 manim_code 中未包含 self.wait() 占位")
    return result
