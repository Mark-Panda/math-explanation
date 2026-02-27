"""流水线编排：题目分析 → 脚本生成 → TTS+时长 → 时长注入+HTML渲染 → 完成。支持断点检查点，失败重试时从当前步骤继续。"""
import logging
from pathlib import Path
from typing import Callable

from config import get_settings
from asset_generation.html_render import render_html_with_self_heal
from asset_generation.remotion_render import render_remotion_video
from asset_generation.timing import inject_timing_into_html
from asset_generation.tts import generate_audios_for_steps
from problem_analysis.analyzer import analyze_problem
from script_generation.generator import generate_animation_html_and_prompts
from script_generation.remotion_generator import generate_remotion_code

from api.pipeline_checkpoint import (
    clear_checkpoint,
    load_checkpoint,
    save_step_checkpoint,
)

logger = logging.getLogger(__name__)

# 流水线步骤名称，供进度回调与前端展示
PIPELINE_STEPS = [
    "题目分析",
    "网页动画脚本生成",
    "TTS 与时长收集",
    "时长注入与 HTML 渲染",
]


def run_pipeline(
    problem_text: str,
    output_dir: str | Path,
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    on_step_start: Callable[[int, str], None] | None = None,
    force_restart: bool = False,
    animation_style: str | None = None,
) -> Path:
    """
    依次执行：题目分析 → 脚本生成 → TTS 与时长收集 → 时长注入+HTML 渲染。
    每步成功后写入检查点；若某步失败，重试时从该步直接开始，不重头执行。

    :param problem_text: 题目文本（已经过 OCR 和公式验证）
    :param output_dir: 输出目录
    :param image_base64: 可选，原始题目图片的 base64 编码（用于让 LLM 看到原图提升图形/公式准确度）
    :param image_mime_type: 图片 MIME 类型
    :param on_step_start: 进度回调 on_step_start(step_index, step_name)
    :param force_restart: 为 True 时忽略已有检查点，从头执行
    :param animation_style: 可选，动画风格描述，注入脚本生成 prompt；为 None 时使用 config
    :return: (最终 HTML 动画文件路径, steps, durations)，供调用方写 Remotion 网页 props 等。任一步失败则向上抛出异常。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    def _step(i: int, name: str) -> None:
        if on_step_start:
            on_step_start(i, name)
        logger.info("[pipeline] 阶段%d/%d %s…", i + 1, len(PIPELINE_STEPS), name)

    # ---------- 断点恢复：加载检查点，决定起始步骤 ----------
    start_step = 0
    steps = None
    script_out = None
    animation_html = ""
    durations: list[float] = []

    if not force_restart:
        last_done, steps_ck, script_ck, durations_ck = load_checkpoint(work)
        if last_done >= 0 and steps_ck is not None:
            start_step = last_done + 1
            steps = steps_ck
            if script_ck is not None:
                script_out = script_ck
                animation_html = script_ck.animation_html
            if durations_ck is not None:
                durations = durations_ck
            logger.info("[pipeline] 从检查点恢复，从步骤 %d/%s 继续", start_step, PIPELINE_STEPS[start_step - 1] if start_step else "无")

    audio_dir = work / "audio"

    # ---------- 阶段 0：题目分析 ----------
    if start_step <= 0:
        _step(0, PIPELINE_STEPS[0])
        steps = analyze_problem(
            problem_text,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
        logger.info("[pipeline] 题目分析完成 步骤数=%d", len(steps))
        save_step_checkpoint(work, 0, steps)

    if steps is None or not steps:
        raise ValueError("题目分析结果不可用，无法继续流水线")

    # ---------- 阶段 1：脚本生成 ----------
    if start_step <= 1:
        _step(1, PIPELINE_STEPS[1])
        script_out = generate_animation_html_and_prompts(
            steps,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            animation_style=animation_style,
        )
        animation_html = script_out.animation_html
        logger.info("[pipeline] 脚本生成完成 animation_html 长度=%d", len(animation_html))
        save_step_checkpoint(work, 1, script_out)

        # ---------- 可选：用大模型 + Remotion skill 生成 Remotion 代码 ----------
        if get_settings().remotion_generate_code and steps is not None:
            try:
                logger.info("[pipeline] Remotion 代码生成（大模型 + skill）…")
                remotion_tsx = generate_remotion_code(
                    steps,
                    animation_style=animation_style or get_settings().animation_style or None,
                )
                generated_path = work / "MathExplanation.generated.tsx"
                generated_path.write_text(remotion_tsx, encoding="utf-8")
                logger.info("[pipeline] Remotion 代码已写入 %s", generated_path)
            except Exception as e:
                logger.warning("[pipeline] Remotion 代码生成跳过或失败（不影响 HTML）: %s", e)

    # ---------- 阶段 2：TTS 与时长收集 ----------
    if start_step <= 2:
        _step(2, PIPELINE_STEPS[2])
        audio_dir.mkdir(parents=True, exist_ok=True)
        durations = generate_audios_for_steps(steps, output_dir=audio_dir, prefix="step")
        logger.info("[pipeline] TTS 完成 时长列表=%s", durations)
        save_step_checkpoint(work, 2, durations)

    # ---------- 阶段 3：时长注入与 HTML 渲染 ----------
    if start_step <= 3:
        _step(3, PIPELINE_STEPS[3])
        final_html_code = inject_timing_into_html(animation_html, durations)
        final_html_file = output_dir / "animation.html"
        render_html_with_self_heal(final_html_code, audio_dir, final_html_file, audio_prefix="step")
        logger.info("[pipeline] HTML 渲染完成 %s", final_html_file)
        save_step_checkpoint(work, 3, None)
        # clear_checkpoint(work)

        # ---------- 可选：Remotion 渲染 MP4 ----------
        if get_settings().remotion_enabled and steps is not None:
            try:
                mp4_file = output_dir / "animation.mp4"
                generated_tsx = work / "MathExplanation.generated.tsx"
                render_remotion_video(
                    steps,
                    durations,
                    audio_dir,
                    mp4_file,
                    audio_prefix="step",
                    node_command=get_settings().remotion_node_command,
                    generated_tsx_path=generated_tsx if generated_tsx.is_file() else None,
                )
                logger.info("[pipeline] Remotion MP4 已生成 %s", mp4_file)
            except Exception as e:
                logger.warning("[pipeline] Remotion 渲染跳过或失败（不影响 HTML 结果）: %s", e)

        return (final_html_file, steps, durations)

    final_html_file = output_dir / "animation.html"
    if final_html_file.exists():
        # clear_checkpoint(work)
        return (final_html_file, steps, durations)
    raise RuntimeError("流水线未执行到 HTML 渲染步骤且无成品文件")
