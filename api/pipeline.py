"""流水线编排：题目分析 → 脚本生成 → TTS+时长 → 时长注入 → Manim 自愈渲染 → 音频拼接 → 合成。支持断点检查点，失败重试时从当前步骤继续。"""
import logging
from pathlib import Path
from typing import Callable

from asset_generation.manim_render import render_manim_video_with_self_heal
from asset_generation.timing import inject_timing_into_code
from asset_generation.tts import generate_audios_for_steps
from composition.audio_concat import concat_audio_files
from composition.ffmpeg_compose import CompositionError, compose_video
from problem_analysis.analyzer import analyze_problem
from script_generation.generator import generate_manim_code_and_prompts

from api.pipeline_checkpoint import (
    clear_checkpoint,
    load_checkpoint,
    save_step_checkpoint,
)

logger = logging.getLogger(__name__)

# 流水线步骤名称，供进度回调与前端展示
PIPELINE_STEPS = [
    "题目分析",
    "多模态脚本生成",
    "TTS 与时长收集",
    "时长注入与 Manim 渲染",
    "音频拼接",
    "视频合成",
]


def run_pipeline(
    problem_text: str,
    output_dir: str | Path,
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    on_step_start: Callable[[int, str], None] | None = None,
    force_restart: bool = False,
) -> Path:
    """
    依次执行：题目分析 → 脚本生成 → TTS 与时长收集 → 时长注入 → Manim 自愈渲染 → 音频拼接 → 合成。
    每步成功后写入检查点；若某步失败，重试时从该步直接开始，不重头执行。

    :param problem_text: 题目文本（已经过 OCR 和公式验证）
    :param output_dir: 输出目录
    :param image_base64: 可选，原始题目图片的 base64 编码（用于让 LLM 看到原图提升图形/公式准确度）
    :param image_mime_type: 图片 MIME 类型
    :param on_step_start: 进度回调 on_step_start(step_index, step_name)
    :param force_restart: 为 True 时忽略已有检查点，从头执行
    :return: 最终视频文件路径。任一步失败则向上抛出异常。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    def _step(i: int, name: str) -> None:
        if on_step_start:
            on_step_start(i, name)
        logger.info("[pipeline] 阶段%d/6 %s…", i + 1, name)

    # ---------- 断点恢复：加载检查点，决定起始步骤 ----------
    start_step = 0
    steps = None
    script_out = None
    manim_code = ""
    durations: list[float] = []

    if not force_restart:
        last_done, steps_ck, script_ck, durations_ck = load_checkpoint(work)
        if last_done >= 0 and steps_ck is not None:
            start_step = last_done + 1
            steps = steps_ck
            if script_ck is not None:
                script_out = script_ck
                manim_code = script_ck.manim_code
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
        script_out = generate_manim_code_and_prompts(
            steps,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
        manim_code = script_out.manim_code
        logger.info("[pipeline] 脚本生成完成 manim_code 长度=%d", len(manim_code))
        save_step_checkpoint(work, 1, script_out)

    # ---------- 阶段 2：TTS 与时长收集 ----------
    if start_step <= 2:
        _step(2, PIPELINE_STEPS[2])
        audio_dir.mkdir(parents=True, exist_ok=True)
        durations = generate_audios_for_steps(steps, output_dir=audio_dir, prefix="step")
        logger.info("[pipeline] TTS 完成 时长列表=%s", durations)
        save_step_checkpoint(work, 2, durations)

    # ---------- 阶段 3：时长注入与 Manim 渲染 ----------
    if start_step <= 3:
        _step(3, PIPELINE_STEPS[3])
        final_code = inject_timing_into_code(manim_code, durations)
        manim_video = work / "manim.mp4"
        render_manim_video_with_self_heal(final_code, manim_video)
        logger.info("[pipeline] Manim 渲染完成 %s", manim_video)
        save_step_checkpoint(work, 3, None)

    manim_video = work / "manim.mp4"

    # ---------- 阶段 4：音频拼接 ----------
    if start_step <= 4:
        _step(4, PIPELINE_STEPS[4])
        audio_files = sorted(audio_dir.glob("step_*.mp3"), key=lambda p: int(p.stem.split("_")[1]))
        full_audio = work / "full_audio.mp3"
        concat_audio_files(audio_files, full_audio)
        logger.info("[pipeline] 音频拼接完成 %s", full_audio)
        save_step_checkpoint(work, 4, None)

    full_audio = work / "full_audio.mp3"

    # ---------- 阶段 5：视频合成 ----------
    if start_step <= 5:
        _step(5, PIPELINE_STEPS[5])
        final_video = output_dir / "final.mp4"
        compose_video(manim_video, full_audio, final_video)
        logger.info("[pipeline] 流水线全部完成 %s", final_video)
        save_step_checkpoint(work, 5, None)
        clear_checkpoint(work)
        return final_video

    final_video = output_dir / "final.mp4"
    if final_video.exists():
        clear_checkpoint(work)
        return final_video
    raise RuntimeError("流水线未执行到视频合成步骤且无成品文件")
