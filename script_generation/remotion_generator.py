"""
基于 Remotion skill 规则，用 LLM 生成数学讲解的 Remotion（React/TSX）代码。
产出为单文件组件，props 与现有 MathExplanation 一致，便于接入流水线与 Remotion 渲染。
"""
import json
import logging

from config import get_settings
from llm_runner import invoke_structured
from pydantic import BaseModel, Field

from problem_analysis.schemas import StepItem

from .remotion_context import load_remotion_skill_context

logger = logging.getLogger(__name__)


class RemotionCodeOutput(BaseModel):
    """LLM 输出的 Remotion TSX 代码。"""
    tsx_code: str = Field(..., description="完整的 React/TSX 组件代码，含 export 与类型定义")


REMOTION_GENERATE_PROMPT = """你是一位熟悉 Remotion 的前端工程师。请根据下列「Remotion 最佳实践」规则和本题的解题步骤，生成一段完整的 Remotion 组件代码（TSX）。

## Remotion 最佳实践（必须遵守）

{remotion_skill_context}

## 本题解题步骤

{steps_json}

## 要求

1. **组件接口**：必须与以下类型一致，以便与现有流水线对接。
   - 定义并导出类型：
     - `StepInput`: {{ stepId: number; description: string; mathFormula: string; voiceoverText: string; durationSeconds: number; }}
     - `MathExplanationGeneratedProps`: {{ steps: StepInput[]; audioFileNames?: string[]; audioUrls?: string[]; }}
   - 组件接收 props: `MathExplanationGeneratedProps`，组件名导出为 `MathExplanationGenerated`。

2. **时序与音频**：
   - 使用 `<Series>` 与 `<Series.Sequence>` 按步骤顺序播放，每步时长 `durationInFrames = Math.ceil(step.durationSeconds * fps)`，并设置 `premountFor={5}`。
   - 每步内使用 `<Audio>`（来自 `@remotion/media`）播放该步旁白：优先用 `audioUrls[i]`，否则用 `staticFile(\`audio/${{audioFileNames[i]}}\`)`。

3. **动画**：
   - 所有动画必须用 `useCurrentFrame()` 和 `interpolate()`（或 `spring()`）驱动，禁止使用 CSS transition/animation 或 Tailwind 动画类。
   - 每步内容可做淡入（opacity 0→1）等简单效果，时长用 `fps` 换算成 frame。

4. **样式**：
   - 画布 800×600，背景 #f6f8fa，字体 system-ui；公式与描述清晰可读，步骤序号小字展示。

5. **只输出一个 TSX 文件的内容**：包含 import（remotion、@remotion/media）、类型定义和组件实现，不要包含 Root.tsx 或 Composition 注册代码。

请直接输出符合上述要求的 TSX 代码。"""


def _steps_to_json(steps: list[StepItem]) -> str:
    """将步骤转为供 LLM 使用的 JSON（含占位时长，后续会被真实时长替换）。"""
    items = [
        {
            "stepId": s.step_id,
            "description": s.description,
            "mathFormula": s.math_formula or "",
            "voiceoverText": s.voiceover_text or "",
            "durationSeconds": 3.0,
        }
        for s in steps
    ]
    return json.dumps(items, ensure_ascii=False, indent=2)


def generate_remotion_code(
    steps: list[StepItem],
    *,
    animation_style: str | None = None,
) -> str:
    """
    根据解题步骤与 Remotion skill 规则，调用 LLM 生成 Remotion 组件 TSX 代码。

    :param steps: 题目分析得到的步骤列表
    :param animation_style: 可选，动画风格描述，会追加到 prompt
    :return: 完整 TSX 代码字符串（可写入 MathExplanation.generated.tsx）
    """
    if not steps:
        raise ValueError("steps 不能为空")

    skill_context = load_remotion_skill_context()
    if not skill_context.strip():
        logger.warning("[remotion_gen] Remotion skill 规则未加载到，将仅依赖 prompt 要求生成")

    steps_json = _steps_to_json(steps)
    style_instruction = ""
    if animation_style and animation_style.strip():
        style_instruction = f"\n**动画风格**：{animation_style.strip()}"

    prompt = REMOTION_GENERATE_PROMPT.format(
        remotion_skill_context=skill_context or "（无额外规则，请严格按下方要求实现）",
        steps_json=steps_json,
    )
    if style_instruction:
        prompt = prompt.rstrip() + "\n" + style_instruction

    timeout = get_settings().llm_request_timeout
    result: RemotionCodeOutput = invoke_structured(
        prompt,
        RemotionCodeOutput,
        timeout=timeout,
    )
    code = result.tsx_code.strip()

    # 若被包在 ```tsx ... ``` 中则去掉
    if code.startswith("```"):
        lines = code.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)

    # 简单校验：必须包含与流水线对接的关键字
    required = ["steps", "Series", "useCurrentFrame", "durationSeconds"]
    for kw in required:
        if kw not in code:
            logger.warning("[remotion_gen] 生成代码中未包含 %s，可能无法与流水线对接", kw)

    logger.info("[remotion_gen] 生成 TSX 长度=%d", len(code))
    return code
