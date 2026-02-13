"""题目理解与逻辑拆解：analyze_problem(problem_text)。支持多模态（文本+图片）分析。"""
from llm_runner import invoke_multimodal_structured, invoke_structured

from .schemas import ProblemAnalysisOutput, StepItem

PROBLEM_ANALYSIS_PROMPT = """你是一个数学专家和动画脚本设计师。请分析以下数学题目，并生成解题步骤。

题目: {problem_text}

请严格按照结构化输出：输出包含 steps 列表，每个步骤包含 step_id（从 1 开始的整数）、description（该步文字描述）、math_formula（LaTeX 格式公式，如 $x^2 + y^2 = r^2$）、visual_focus（需要突出的视觉元素）、voiceover_text（这一步的旁白文案）。至少生成一个步骤。"""

PROBLEM_ANALYSIS_PROMPT_WITH_IMAGE = """你是一个数学专家和动画脚本设计师。请结合题目文字和附带的原始题目图片，分析数学题目并生成解题步骤。

题目文字: {problem_text}

**重要**：请仔细观察附带的原始题目图片，特别注意：
1. 图片中的几何图形的形状、标注、角度、边长等细节
2. 图片中的公式是否与文字描述一致，以图片为准
3. 坐标系、函数图像的精确信息
4. 图形之间的位置关系和特殊标记（虚线、阴影等）

请严格按照结构化输出：输出包含 steps 列表，每个步骤包含 step_id（从 1 开始的整数）、description（该步文字描述）、math_formula（LaTeX 格式公式，如 $x^2 + y^2 = r^2$）、visual_focus（需要突出的视觉元素，需与图片中实际图形一致）、voiceover_text（这一步的旁白文案）。至少生成一个步骤。"""


def analyze_problem(
    problem_text: str,
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
) -> list[StepItem]:
    """
    校验非空后通过 LangChain 调用 LLM，返回结构化 steps。
    当提供 image_base64 时，使用多模态结构化调用让 LLM 同时看到原图。
    空题目抛出 ValueError；LLM 异常向上抛出便于编排层处理。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目文本不能为空")

    if image_base64:
        prompt = PROBLEM_ANALYSIS_PROMPT_WITH_IMAGE.format(problem_text=problem_text.strip())
        result: ProblemAnalysisOutput = invoke_multimodal_structured(
            prompt,
            ProblemAnalysisOutput,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
    else:
        prompt = PROBLEM_ANALYSIS_PROMPT.format(problem_text=problem_text.strip())
        result = invoke_structured(prompt, ProblemAnalysisOutput)

    return result.steps
