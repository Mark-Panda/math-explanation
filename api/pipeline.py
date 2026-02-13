"""流水线编排：题目分析 → 脚本生成 → TTS+时长 → 时长注入 → Manim 自愈渲染 → 音频拼接 → 合成。"""
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
) -> Path:
    """
    依次执行：题目分析 → 脚本生成 → TTS 与时长收集 → 时长注入 → Manim 自愈渲染 → 音频拼接 → 合成。

    :param problem_text: 题目文本（已经过 OCR 和公式验证）
    :param output_dir: 输出目录
    :param image_base64: 可选，原始题目图片的 base64 编码（用于让 LLM 看到原图提升图形/公式准确度）
    :param image_mime_type: 图片 MIME 类型
    :param on_step_start: 进度回调 on_step_start(step_index, step_name)
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

    # ---------- 阶段 1：题目分析（多模态：文本 + 原图） ----------
    _step(0, PIPELINE_STEPS[0])
    steps = analyze_problem(
        problem_text,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
    )
    logger.info("[pipeline] 题目分析完成 步骤数=%d", len(steps))

    # ---------- 阶段 2：脚本生成（多模态：步骤 + 原图） ----------
    _step(1, PIPELINE_STEPS[1])
    script_out = generate_manim_code_and_prompts(
        steps,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
    )
    manim_code = script_out.manim_code
    logger.info("[pipeline] 脚本生成完成 manim_code 长度=%d", len(manim_code))

    # ---------- 阶段 3：TTS 与时长收集 ----------
    _step(2, PIPELINE_STEPS[2])
    audio_dir = work / "audio"
    durations = generate_audios_for_steps(steps, output_dir=audio_dir, prefix="step")
    logger.info("[pipeline] TTS 完成 时长列表=%s", durations)

    # ---------- 阶段 4：时长注入与 Manim 渲染 ----------
    _step(3, PIPELINE_STEPS[3])
    final_code = inject_timing_into_code(manim_code, durations)
    manim_video = work / "manim.mp4"
    render_manim_video_with_self_heal(final_code, manim_video)
    logger.info("[pipeline] Manim 渲染完成 %s", manim_video)

    # ---------- 阶段 5：音频拼接 ----------
    _step(4, PIPELINE_STEPS[4])
    audio_files = sorted(audio_dir.glob("step_*.mp3"), key=lambda p: int(p.stem.split("_")[1]))
    full_audio = work / "full_audio.mp3"
    concat_audio_files(audio_files, full_audio)
    logger.info("[pipeline] 音频拼接完成 %s", full_audio)

    # ---------- 阶段 6：视频合成 ----------
    _step(5, PIPELINE_STEPS[5])
    final_video = output_dir / "final.mp4"
    compose_video(manim_video, full_audio, final_video)
    logger.info("[pipeline] 流水线全部完成 %s", final_video)
    return final_video
