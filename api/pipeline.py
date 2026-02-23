"""流水线编排：题目分析 → 脚本生成 → TTS+时长 → 时长注入+HTML渲染 → 完成。支持断点检查点，失败重试时从当前步骤继续。
另提供 run_tutor_pipeline：按 /tutor 技能的 8 步逻辑生成 Manim 视频。"""
import logging
from pathlib import Path
from typing import Callable

from asset_generation.html_render import render_html_with_self_heal
from asset_generation.timing import inject_timing_into_html
from asset_generation.tts import generate_audios_for_steps
from problem_analysis.analyzer import analyze_problem
from script_generation.generator import generate_animation_html_and_prompts

from api.pipeline_checkpoint import (
    clear_checkpoint,
    load_checkpoint,
    save_step_checkpoint,
)
from api.tutor_checkpoint import (
    clear_tutor_checkpoint,
    load_tutor_checkpoint,
    save_tutor_step,
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
    :return: 最终 HTML 动画文件路径。任一步失败则向上抛出异常。
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
        import json
        step_list = [
            {
                "step_id": getattr(s, "step_id", i + 1),
                "description": (getattr(s, "description", None) or "").strip(),
                "voiceover_text": (getattr(s, "voiceover_text", None) or "").strip(),
            }
            for i, s in enumerate(steps)
        ]
        script_content = "window.stepDescriptions = " + json.dumps(step_list, ensure_ascii=False)
        script_content = script_content.replace("</script>", "<\\/script>")
        animation_html = animation_html + "\n<script>" + script_content + "</script>"
        final_html_code = inject_timing_into_html(animation_html, durations)
        final_html_file = output_dir / "animation.html"
        render_html_with_self_heal(final_html_code, audio_dir, final_html_file, audio_prefix="step")
        logger.info("[pipeline] HTML 渲染完成 %s", final_html_file)
        save_step_checkpoint(work, 3, None)
        clear_checkpoint(work)
        return final_html_file

    final_html_file = output_dir / "animation.html"
    if final_html_file.exists():
        clear_checkpoint(work)
        return final_html_file
    raise RuntimeError("流水线未执行到 HTML 渲染步骤且无成品文件")


# ---------- Tutor 流水线（/tutor 技能逻辑）----------

PIPELINE_STEPS_TUTOR = [
    "数学分析(tutor)",
    "HTML 可视化",
    "分镜脚本",
    "TTS 与时长",
    "验证音频",
    "脚手架",
    "Manim 实现",
    "检查与渲染",
]


def run_tutor_pipeline(
    problem_text: str,
    output_dir: str | Path,
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    on_step_start: Callable[[int, str], None] | None = None,
    force_restart: bool = False,
) -> Path:
    """
    按 /tutor 技能逻辑执行：数学分析 → HTML 可视化 → 分镜 → TTS → 验证 → 脚手架 → Manim 实现 → 检查与渲染。
    返回最终视频文件路径（output_dir / "animation.mp4"）。
    """
    from tutor_pipeline.stages import (
        analyze_math_tutor,
        check_script_has_required,
        generate_html_visualization,
        generate_scaffold,
        generate_storyboard,
        generate_tts_from_storyboard,
        implement_script,
        render_tutor_video,
        validate_audio,
        _inject_add_sound_if_missing,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    audio_dir = work / "audio"

    def _step(i: int, name: str) -> None:
        if on_step_start:
            on_step_start(i, name)
        logger.info("[tutor_pipeline] 阶段 %d/%d %s…", i + 1, len(PIPELINE_STEPS_TUTOR), name)

    last_done, math_analysis, html_content, storyboard_md, audio_info, scaffold_code, full_script = load_tutor_checkpoint(work)
    start_step = 0
    if not force_restart and last_done >= 0:
        start_step = last_done + 1
        logger.info("[tutor_pipeline] 从检查点恢复，从步骤 %s 继续", PIPELINE_STEPS_TUTOR[start_step - 1] if start_step else "无")

    # 0: 数学分析
    if start_step <= 0:
        _step(0, PIPELINE_STEPS_TUTOR[0])
        math_analysis = analyze_math_tutor(
            problem_text,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
        save_tutor_step(work, 0, math_analysis=math_analysis)

    if not math_analysis or not math_analysis.strip():
        raise ValueError("数学分析结果不可用")

    # 1: HTML 可视化
    if start_step <= 1:
        _step(1, PIPELINE_STEPS_TUTOR[1])
        html_content = generate_html_visualization(math_analysis)
        save_tutor_step(work, 1, html_content=html_content)

    if not html_content or not html_content.strip():
        raise ValueError("HTML 可视化结果不可用")

    # 2: 分镜脚本
    if start_step <= 2:
        _step(2, PIPELINE_STEPS_TUTOR[2])
        storyboard_md = generate_storyboard(math_analysis, html_content)
        save_tutor_step(work, 2, storyboard_md=storyboard_md)

    if not storyboard_md or not storyboard_md.strip():
        raise ValueError("分镜脚本结果不可用")

    # 3: TTS 与时长
    if start_step <= 3:
        _step(3, PIPELINE_STEPS_TUTOR[3])
        audio_dir.mkdir(parents=True, exist_ok=True)
        _, audio_info = generate_tts_from_storyboard(storyboard_md, audio_dir)
        save_tutor_step(work, 3, audio_info=audio_info)

    if not audio_info or not audio_info.files:
        raise ValueError("TTS 结果不可用（无音频清单）")

    # 4: 验证音频
    if start_step <= 4:
        _step(4, PIPELINE_STEPS_TUTOR[4])
        validate_audio(audio_dir, audio_info)

    # 5: 脚手架
    if start_step <= 5 and (not scaffold_code or not scaffold_code.strip()):
        _step(5, PIPELINE_STEPS_TUTOR[5])
        scaffold_code = generate_scaffold(audio_info, audio_dir)
        save_tutor_step(work, 4, scaffold_code=scaffold_code)

    if not scaffold_code or not scaffold_code.strip():
        raise ValueError("脚手架结果不可用")

    # 6: Manim 实现
    if start_step <= 6 and (not full_script or not full_script.strip()):
        _step(6, PIPELINE_STEPS_TUTOR[6])
        full_script = implement_script(scaffold_code, storyboard_md, audio_info, math_analysis=math_analysis)
        save_tutor_step(work, 5, full_script=full_script)

    if not full_script or not full_script.strip():
        raise ValueError("Manim 脚本结果不可用")

    # 7: 检查与渲染
    _step(7, PIPELINE_STEPS_TUTOR[7])
    full_script = _inject_add_sound_if_missing(full_script)
    errs = check_script_has_required(full_script)
    if errs:
        raise ValueError("脚本检查未通过: " + ", ".join(errs))
    output_mp4 = (output_dir / "animation.mp4").resolve()
    result_mp4 = render_tutor_video(full_script, audio_dir, audio_info, output_mp4)
    if result_mp4 is None:
        clear_tutor_checkpoint(work)
        raise RuntimeError("视频渲染未返回路径（内部错误，请检查 MANIM_SELF_HEAL_MAX_ATTEMPTS）")
    result_mp4 = result_mp4.resolve()
    if not result_mp4.exists():
        clear_tutor_checkpoint(work)
        try:
            listing = ", ".join(p.name for p in output_dir.iterdir()) or "(空)"
        except OSError:
            listing = "(无法列出)"
        raise RuntimeError(
            f"视频已渲染但文件不存在: {result_mp4}；output_dir 内容: {listing}"
        )
    clear_tutor_checkpoint(work)
    logger.info("[tutor_pipeline] 视频已生成 %s", result_mp4)
    return result_mp4
