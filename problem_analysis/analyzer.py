"""题目理解与逻辑拆解：analyze_problem(problem_text)。"""
from llm_runner import invoke_structured

from .schemas import ProblemAnalysisOutput, StepItem

PROBLEM_ANALYSIS_PROMPT = """你是一个数学专家和动画脚本设计师。请分析以下数学题目，并生成解题步骤。

题目: {problem_text}

请严格按照结构化输出：输出包含 steps 列表，每个步骤包含 step_id（从 1 开始的整数）、description（该步文字描述）、math_formula（LaTeX 格式公式，如 $x^2 + y^2 = r^2$）、visual_focus（需要突出的视觉元素）、voiceover_text（这一步的旁白文案）。至少生成一个步骤。"""


def analyze_problem(problem_text: str) -> list[StepItem]:
    """
    校验非空后通过 LangChain 调用 LLM，返回结构化 steps。
    空题目抛出 ValueError；LLM 异常向上抛出便于编排层处理。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目文本不能为空")
    prompt = PROBLEM_ANALYSIS_PROMPT.format(problem_text=problem_text.strip())
    result: ProblemAnalysisOutput = invoke_structured(prompt, ProblemAnalysisOutput)
    return result.steps
