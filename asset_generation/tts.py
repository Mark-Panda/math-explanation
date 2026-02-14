"""TTS 生成语音并返回时长（秒）。同一批步骤固定使用同一音色，避免出现两种人声。"""
import asyncio
import logging
from pathlib import Path

from config import get_settings

logger = logging.getLogger(__name__)


async def generate_audio_with_duration_async(
    text: str,
    output_path: str | Path,
    *,
    voice: str | None = None,
) -> float:
    """异步：生成语音文件并返回时长（秒）。传入 voice 时固定使用该音色，否则从配置读取。"""
    if not text or not text.strip():
        raise ValueError("语音文本不能为空")
    try:
        import edge_tts
    except ImportError as e:
        raise ImportError("请安装 edge-tts: pip install edge-tts") from e
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if voice is None:
        voice = get_settings().tts_voice
    communicate = edge_tts.Communicate(text.strip(), voice)
    await communicate.save(str(out))
    default_sec = get_settings().default_wait_seconds

    def _duration_via_ffprobe() -> float | None:
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except FileNotFoundError:
            import warnings
            warnings.warn(
                "未找到 ffprobe（请安装 FFmpeg: brew install ffmpeg，以获得准确语音时长）。当前使用默认时长。",
                UserWarning,
                stacklevel=2,
            )
        except subprocess.TimeoutExpired:
            import warnings
            warnings.warn(
                "ffprobe 获取时长超时，使用默认时长。",
                UserWarning,
                stacklevel=2,
            )
        return None

    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(out))
        return len(seg) / 1000.0
    except ImportError:
        return _duration_via_ffprobe() or default_sec
    except (FileNotFoundError, OSError):
        # pydub 内部调用 ffprobe，未安装 ffmpeg 时会报错
        return _duration_via_ffprobe() or default_sec


def generate_audio_with_duration(text: str, output_path: str | Path) -> float:
    """同步封装：生成语音并返回时长（秒）。"""
    return asyncio.run(generate_audio_with_duration_async(text, output_path))


async def generate_audios_for_steps_async(
    steps: list,
    *,
    output_dir: str | Path = ".",
    prefix: str = "audio",
) -> list[float]:
    """按步骤批量生成音频并返回各步时长列表。同一批内固定使用同一音色，避免出现两种人声。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    voice = get_settings().tts_voice
    logger.info("[TTS] 本批使用音色: %s（共 %d 步）", voice, len(steps))
    durations: list[float] = []
    for i, step in enumerate(steps):
        text = getattr(step, "voiceover_text", None) or (step.get("voiceover_text") if isinstance(step, dict) else "")
        if not text:
            durations.append(get_settings().default_wait_seconds)
            continue
        path = output_dir / f"{prefix}_{i+1}.mp3"
        dur = await generate_audio_with_duration_async(text, path, voice=voice)
        durations.append(dur)
    return durations


def generate_audios_for_steps(
    steps: list,
    *,
    output_dir: str | Path = ".",
    prefix: str = "audio",
) -> list[float]:
    """同步：按步骤批量生成音频并返回各步时长列表。"""
    return asyncio.run(generate_audios_for_steps_async(steps, output_dir=output_dir, prefix=prefix))
