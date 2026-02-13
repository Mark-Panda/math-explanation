"""流水线编排：题目分析 → 脚本生成 → TTS+时长 → 时长注入 → Manim 自愈渲染 → 音频拼接 → 合成。"""
import logging
from pathlib import Path

from asset_generation.manim_render import render_manim_video_with_self_heal
from asset_generation.timing import inject_timing_into_code
from asset_generation.tts import generate_audios_for_steps
from composition.audio_concat import concat_audio_files
from composition.ffmpeg_compose import CompositionError, compose_video
from problem_analysis.analyzer import analyze_problem
from script_generation.generator import generate_manim_code_and_prompts

logger = logging.getLogger(__name__)


def run_pipeline(problem_text: str, output_dir: str | Path) -> Path:
    """
    依次执行：题目分析 → 脚本生成 → TTS 与时长收集 → 时长注入 → Manim 自愈渲染 → 音频拼接 → 合成。
    返回最终视频文件路径。任一步失败则向上抛出异常（ValueError、RuntimeError、CompositionError 等）。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    logger.info("[pipeline] 阶段1/6 题目分析…")
    steps = analyze_problem(problem_text)
    logger.info("[pipeline] 题目分析完成 步骤数=%d", len(steps))

    logger.info("[pipeline] 阶段2/6 多模态脚本生成…")
    script_out = generate_manim_code_and_prompts(steps)
    manim_code = script_out.manim_code
    logger.info("[pipeline] 脚本生成完成 manim_code 长度=%d", len(manim_code))

    logger.info("[pipeline] 阶段3/6 TTS 与时长收集…")
    audio_dir = work / "audio"
    durations = generate_audios_for_steps(steps, output_dir=audio_dir, prefix="step")
    logger.info("[pipeline] TTS 完成 时长列表=%s", durations)

    logger.info("[pipeline] 阶段4/6 时长注入与 Manim 渲染…")
    final_code = inject_timing_into_code(manim_code, durations)
    manim_video = work / "manim.mp4"
    render_manim_video_with_self_heal(final_code, manim_video)
    logger.info("[pipeline] Manim 渲染完成 %s", manim_video)

    logger.info("[pipeline] 阶段5/6 音频拼接…")
    audio_files = sorted(audio_dir.glob("step_*.mp3"), key=lambda p: int(p.stem.split("_")[1]))
    full_audio = work / "full_audio.mp3"
    concat_audio_files(audio_files, full_audio)
    logger.info("[pipeline] 音频拼接完成 %s", full_audio)

    logger.info("[pipeline] 阶段6/6 视频合成…")
    final_video = output_dir / "final.mp4"
    compose_video(manim_video, full_audio, final_video)
    logger.info("[pipeline] 流水线全部完成 %s", final_video)
    return final_video
