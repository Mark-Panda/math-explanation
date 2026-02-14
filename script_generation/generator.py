"""
两阶段脚本生成：
  阶段 A — 生成动画方案（轻量请求，含图片时走多模态）
  阶段 B — 逐步生成每步的 animate 函数体（每步一次小请求，纯文本）
  最后拼装为完整 HTML 片段
"""
import json
import logging

from config import get_settings
from llm_runner import invoke_multimodal_structured, invoke_structured

from problem_analysis.schemas import StepItem

from .schemas import AnimationPlanOutput, ScriptGenerationOutput, StepCodeOutput

logger = logging.getLogger(__name__)

# ==================== 阶段 A：动画方案 ====================

PLAN_PROMPT = """你是数学动画设计师。基于以下解题步骤，为每一步设计网页动画方案。

解题步骤:
{steps_json}

请输出：
1. shared_css: 所有步骤共享的 CSS 样式（用于动画容器内的元素样式，如 .formula, .highlight, .step-title 等）
2. shared_svg: 如果题目涉及几何图形，输出一段 SVG 代码作为底图（后续步骤会在此基础上添加动画元素）；如果不涉及几何，留空字符串 ""
3. step_plans: 每步的动画方案，包含：
   - step_id: 步骤序号
   - animation_description: 具体描述该步动画要做什么（显示哪些公式/文字、什么动画效果、颜色变化等）
   - image_prompt: 该步的图像提示词（教科书风格、极简、白色背景）

要求：
- 动画容器尺寸 800×600px，背景白色
- 公式用 Unicode 数学符号（x²、√、∑、π 等），不用 MathJax/KaTeX
- 动画效果用纯 CSS（fadeIn、slideIn 等），不用外部库
- 几何图形用 SVG 绘制
- step_plans 数量必须与输入步骤数一致"""

PLAN_PROMPT_WITH_IMAGE = """你是数学动画设计师。基于以下解题步骤和附带的原始题目图片，为每一步设计网页动画方案。

解题步骤:
{steps_json}

请仔细观察图片中的图形、公式和标注，设计动画时要准确还原。

请输出：
1. shared_css: 所有步骤共享的 CSS 样式
2. shared_svg: 如果题目涉及几何图形，输出 SVG 底图（准确还原图片中的图形、顶点标注、角度等）；否则留空 ""
3. step_plans: 每步的动画方案，包含 step_id、animation_description、image_prompt

要求：
- 动画容器 800×600px，白色背景
- 公式用 Unicode 数学符号，不用 MathJax/KaTeX
- 动画效果用纯 CSS，不用外部库
- 几何图形用 SVG，准确还原原图
- step_plans 数量与步骤数一致"""

# ==================== 阶段 B：逐步生成代码 ====================

STEP_CODE_PROMPT = """你是前端动画工程师。请为以下数学讲解步骤编写 JavaScript 代码。

**背景**：
- 动画容器 `<div id="animation-container">` 尺寸 800×600px，白色背景
- 已有的共享样式: {shared_css_summary}
- 已有的 SVG 底图: {shared_svg_summary}
{prev_steps_summary}

**当前步骤 {step_id}**：
- 描述：{description}
- 公式：{math_formula}
- 视觉重点：{visual_focus}
- 旁白：{voiceover_text}
- 动画方案：{animation_description}

请输出 `animate_body`：即 `function(container) {{ ... }}` 的函数体 JavaScript 代码。

要求：
- 代码通过 `container` 参数（即 animation-container 元素）操作 DOM
- 使用 innerHTML 追加或 createElement 创建元素
- 可以使用已有的共享 CSS class
- 动画用 CSS animation 或 transition，元素添加后自动播放
- 公式用 Unicode 数学符号，不用 MathJax/KaTeX
- 几何图形操作已有的 SVG 底图（如改变颜色、添加标注等）
- **不要**使用 window、document.body、alert 等全局操作
- **不要**使用任何外部库
- 只输出函数体代码，不要 function 声明"""


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


def _generate_plan(
    steps: list[StepItem],
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
) -> AnimationPlanOutput:
    """阶段 A：生成动画方案（轻量请求）。"""
    steps_json = json.dumps(_steps_to_dict_list(steps), ensure_ascii=False, indent=2)
    timeout = get_settings().llm_request_timeout  # 用普通请求超时，不需要脚本超时

    if image_base64:
        prompt = PLAN_PROMPT_WITH_IMAGE.format(steps_json=steps_json)
        return invoke_multimodal_structured(
            prompt,
            AnimationPlanOutput,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            timeout=timeout,
        )
    else:
        prompt = PLAN_PROMPT.format(steps_json=steps_json)
        return invoke_structured(prompt, AnimationPlanOutput, timeout=timeout)


def _generate_step_code(
    step: StepItem,
    plan: AnimationPlanOutput,
    step_plan_desc: str,
    prev_steps_info: str,
) -> str:
    """阶段 B：生成单步的 animate 函数体。"""
    css_summary = f'已定义样式: {plan.shared_css[:200]}...' if len(plan.shared_css) > 200 else (plan.shared_css or "无")
    svg_summary = "有 SVG 底图" if plan.shared_svg else "无 SVG 底图"

    prompt = STEP_CODE_PROMPT.format(
        shared_css_summary=css_summary,
        shared_svg_summary=svg_summary,
        prev_steps_summary=prev_steps_info,
        step_id=step.step_id,
        description=step.description,
        math_formula=step.math_formula,
        visual_focus=step.visual_focus,
        voiceover_text=step.voiceover_text,
        animation_description=step_plan_desc,
    )
    result: StepCodeOutput = invoke_structured(
        prompt,
        StepCodeOutput,
        timeout=get_settings().llm_request_timeout,
    )
    return result.animate_body


def _assemble_html(
    plan: AnimationPlanOutput,
    step_codes: list[str],
) -> str:
    """将方案和各步代码拼装为完整的 HTML 片段。"""
    # CSS
    css_block = ""
    if plan.shared_css:
        css_block = f"<style>\n{plan.shared_css}\n</style>"

    # SVG 底图
    svg_block = ""
    if plan.shared_svg:
        svg_block = plan.shared_svg

    # 构建 stepAnimations 数组
    steps_js_items = []
    for i, code in enumerate(step_codes):
        # 清理可能的 markdown 代码块包裹
        clean_code = code.strip()
        if clean_code.startswith("```"):
            lines = clean_code.splitlines()
            lines = lines[1:]  # 去掉 ```javascript
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_code = "\n".join(lines)

        steps_js_items.append(
            f"  {{\n"
            f"    duration: STEP_PLACEHOLDER,\n"
            f"    animate: function(container) {{\n"
            f"      {clean_code}\n"
            f"    }}\n"
            f"  }}"
        )

    steps_js = ",\n".join(steps_js_items)

    html = f"""{css_block}
<div id="animation-container" style="width:800px;height:600px;background:#f6f8fa;position:relative;overflow:hidden;margin:0 auto;">
{svg_block}
</div>
<script>
window.stepAnimations = [
{steps_js}
];
</script>"""
    return html


def generate_animation_html_and_prompts(
    steps: list[StepItem],
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
) -> ScriptGenerationOutput:
    """
    两阶段生成网页动画代码：
    1. 阶段 A：生成动画方案（含图片时走多模态，单次轻量请求）
    2. 阶段 B：逐步生成每步 JS 代码（每步一次小请求，纯文本）
    3. 拼装为完整 HTML 片段
    """
    if not steps:
        raise ValueError("steps 不能为空")
    for i, s in enumerate(steps):
        if not isinstance(s, StepItem):
            raise ValueError(f"steps[{i}] 需为 StepItem")
        if not (s.description and s.voiceover_text):
            raise ValueError(f"steps[{i}] 缺少 description 或 voiceover_text")

    n = len(steps)

    # ---------- 阶段 A：动画方案 ----------
    logger.info("[script_gen] 阶段A: 生成动画方案，步骤数=%d，有图片=%s", n, bool(image_base64))
    plan = _generate_plan(steps, image_base64=image_base64, image_mime_type=image_mime_type)

    # 校验 step_plans 数量
    if len(plan.step_plans) < n:
        # 补齐
        for i in range(len(plan.step_plans), n):
            from .schemas import StepAnimationPlan
            plan.step_plans.append(StepAnimationPlan(
                step_id=steps[i].step_id,
                animation_description=f"显示步骤 {steps[i].step_id} 的内容：{steps[i].description}",
            ))
    elif len(plan.step_plans) > n:
        plan.step_plans = plan.step_plans[:n]

    logger.info("[script_gen] 阶段A 完成，shared_css 长度=%d，shared_svg 长度=%d",
                len(plan.shared_css), len(plan.shared_svg))

    # ---------- 阶段 B：逐步生成代码 ----------
    step_codes: list[str] = []
    for i, step in enumerate(steps):
        prev_info = ""
        if i > 0:
            prev_summaries = [
                f"  步骤{steps[j].step_id}: {plan.step_plans[j].animation_description[:80]}"
                for j in range(i)
            ]
            prev_info = f"\n**前序步骤已完成**:\n" + "\n".join(prev_summaries)

        logger.info("[script_gen] 阶段B: 生成步骤 %d/%d 的代码", i + 1, n)
        code = _generate_step_code(
            step,
            plan,
            plan.step_plans[i].animation_description,
            prev_info,
        )
        step_codes.append(code)
        logger.info("[script_gen] 步骤 %d 代码长度=%d", i + 1, len(code))

    # ---------- 拼装 ----------
    animation_html = _assemble_html(plan, step_codes)
    image_prompts = [sp.image_prompt for sp in plan.step_plans]

    logger.info("[script_gen] 拼装完成，animation_html 长度=%d", len(animation_html))

    return ScriptGenerationOutput(
        animation_html=animation_html,
        image_prompts=image_prompts,
    )
