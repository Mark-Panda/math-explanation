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
- 若有步骤需要「画辅助线」（如垂线、角平分线等），在 shared_svg 中必须预画该辅助线并设唯一 id（如 id=\"de-line\"）、初始 opacity:0 或 class 隐藏，便于步骤代码通过 querySelector 找到并做显示动画；不要依赖步骤代码从零创建线段导致不一致
- step_plans 数量必须与输入步骤数一致
{animation_style_instruction}"""

PLAN_PROMPT_WITH_IMAGE = """你是数学动画设计师。基于以下解题步骤和附带的原始题目图片，为每一步设计网页动画方案。

解题步骤:
{steps_json}

请仔细观察附带的原始题目图片，设计动画时要准确还原。

**shared_svg 必须与原图一致（重要）**：
- 连线关系：只画原图中实际存在的线段，谁连谁必须与原图一致。**四边形 ABCD 必须包含五条线：边 AB、边 BC、边 CD、边 DA，以及对角线 BD**（题目若画了 BD）。每条对应一个 <path> 或 <line>，**不可遗漏任何一条**；尤其 BC 是顶点 B 与 C 的连线（常为底边），必须单独画出，不得与其它边合并或省略。
- 顶点与标注：字母 A、B、C、D 等的位置和相对关系要与原图一致（如原图 A 在左上则 SVG 中 A 也在左上，不要与其它顶点对调）
- 形状与比例：图形的大致形状、夹角、哪边更长要与原图一致，不要画成随意示意图；使用 viewBox=\"0 0 800 600\"，在 800×600 范围内按原图估计各点坐标
- 若原图中有辅助线（如垂线 DE），在 shared_svg 中预画并设 id、初始隐藏；若原图没有的线不要预先画成实线
- 为便于步骤动画引用，给关键线段设 id：如 id=\"bc-line\"（BC 边）、id=\"ad-line\"（AD 边）、id=\"bd-line\"（对角线 BD）等，便于后续步骤高亮或标注

请输出：
1. shared_css: 所有步骤共享的 CSS 样式
2. shared_svg: 如果题目涉及几何图形，输出 SVG 底图（按上述要求与原图一致）；否则留空 ""
3. step_plans: 每步的动画方案，包含 step_id、animation_description、image_prompt

要求：
- 动画容器 800×600px，白色背景
- 公式用 Unicode 数学符号，不用 MathJax/KaTeX
- 动画效果用纯 CSS，不用外部库
- 若有步骤需要「画辅助线」（如垂线 DE、角平分线等），在 shared_svg 中必须预画该辅助线并设唯一 id（如 id=\"de-line\"）、初始 opacity:0 或 class 隐藏，便于步骤代码找到并做显示动画
- step_plans 数量与步骤数一致
{animation_style_instruction}"""

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
- 代码通过 `container` 参数（即 animation-container 元素）操作 DOM；获取 SVG 用 container.querySelector('svg')，获取底图内元素用 container.querySelector('#id')，不要用 document.getElementById 或 svg.getElementById
- 使用 innerHTML 追加或 createElement/createElementNS 创建元素
- 可以使用已有的共享 CSS class
- 动画用 CSS animation 或 transition，元素添加后自动播放
- 公式用 Unicode 数学符号，不用 MathJax/KaTeX
- 几何图形操作已有的 SVG 底图（如改变颜色、添加标注等）
- **不要**使用 window、document.body、alert、playVoice 等全局或未定义函数；**不要**在代码里播放音频，旁白由系统按步自动播放，本代码只负责画面与公式
- 若本步要「显示辅助线」：底图中已有带 id 的辅助线（如 #de-line）时，用 container.querySelector('#de-line') 获取后设置 style.opacity 或 class 使其可见并做绘制/高亮动画；若需创建新线段再用 createElementNS('http://www.w3.org/2000/svg', 'line') 或 path 并 append 到 container.querySelector('svg')
- **不要**使用任何外部库
- 只输出函数体代码，不要 function 声明
{animation_style_instruction}"""


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


def _style_instruction(animation_style: str | None) -> str:
    """若配置了动画风格，返回追加到 prompt 的「动画风格要求」句段，否则返回空串。"""
    if not animation_style or not animation_style.strip():
        return ""
    return "\n**动画风格要求**：" + animation_style.strip()


def _generate_plan(
    steps: list[StepItem],
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    animation_style: str | None = None,
) -> AnimationPlanOutput:
    """阶段 A：生成动画方案（轻量请求）。"""
    steps_json = json.dumps(_steps_to_dict_list(steps), ensure_ascii=False, indent=2)
    timeout = get_settings().llm_request_timeout  # 用普通请求超时，不需要脚本超时
    style_instruction = _style_instruction(animation_style)

    if image_base64:
        prompt = PLAN_PROMPT_WITH_IMAGE.format(steps_json=steps_json, animation_style_instruction=style_instruction)
        return invoke_multimodal_structured(
            prompt,
            AnimationPlanOutput,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            timeout=timeout,
        )
    else:
        prompt = PLAN_PROMPT.format(steps_json=steps_json, animation_style_instruction=style_instruction)
        return invoke_structured(prompt, AnimationPlanOutput, timeout=timeout)


def _generate_step_code(
    step: StepItem,
    plan: AnimationPlanOutput,
    step_plan_desc: str,
    prev_steps_info: str,
    *,
    animation_style: str | None = None,
) -> str:
    """阶段 B：生成单步的 animate 函数体。"""
    css_summary = f'已定义样式: {plan.shared_css[:200]}...' if len(plan.shared_css) > 200 else (plan.shared_css or "无")
    svg_summary = "有 SVG 底图" if plan.shared_svg else "无 SVG 底图"
    style_instruction = _style_instruction(animation_style)

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
        animation_style_instruction=style_instruction,
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
    def _escape_script_close(raw: str) -> str:
        """防止步骤代码中的 </script> 在 HTML 中提前结束脚本块，导致 stepAnimations 未定义、页面显示 0 步。"""
        return raw.replace("</script>", "<\\/script>").replace("</SCRIPT>", "<\\/SCRIPT>")

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
        clean_code = _escape_script_close(clean_code)

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
    animation_style: str | None = None,
) -> ScriptGenerationOutput:
    """
    两阶段生成网页动画代码：
    1. 阶段 A：生成动画方案（含图片时走多模态，单次轻量请求）
    2. 阶段 B：逐步生成每步 JS 代码（每步一次小请求，纯文本）
    3. 拼装为完整 HTML 片段

    animation_style: 可选。若提供，会注入到方案与代码生成的 prompt 中，要求大模型按该风格生成；为 None 时使用 config.animation_style。
    """
    if not steps:
        raise ValueError("steps 不能为空")
    for i, s in enumerate(steps):
        if not isinstance(s, StepItem):
            raise ValueError(f"steps[{i}] 需为 StepItem")
        if not (s.description and s.voiceover_text):
            raise ValueError(f"steps[{i}] 缺少 description 或 voiceover_text")

    n = len(steps)
    style = (animation_style if animation_style is not None else get_settings().animation_style) or ""

    # ---------- 阶段 A：动画方案 ----------
    logger.info("[script_gen] 阶段A: 生成动画方案，步骤数=%d，有图片=%s，风格=%s", n, bool(image_base64), bool(style))
    plan = _generate_plan(steps, image_base64=image_base64, image_mime_type=image_mime_type, animation_style=style or None)

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
            animation_style=style or None,
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
