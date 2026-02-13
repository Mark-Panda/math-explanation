"""使用 FFmpeg 将 Manim 视频与音频合成为最终 MP4。"""
import subprocess
from pathlib import Path

from config import get_settings


class CompositionError(RuntimeError):
    """合成失败时抛出，携带可区分错误信息。"""
    pass


def compose_video(
    manim_video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
) -> None:
    """
    校验两个输入文件存在后，调用 FFmpeg 合成：-c:v copy、-c:a aac、-shortest。
    若输入不存在或 FFmpeg 非零退出码，抛出 CompositionError。
    """
    video_path = Path(manim_video_path)
    audio_path_p = Path(audio_path)
    out_path = Path(output_path)
    if not video_path.is_file():
        raise CompositionError(f"视频文件不存在: {video_path}")
    if not audio_path_p.is_file():
        raise CompositionError(f"音频文件不存在: {audio_path_p}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = get_settings().ffmpeg_command
    args = [
        cmd,
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path_p),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise CompositionError(f"FFmpeg 执行失败 (exit {proc.returncode}): {proc.stderr or proc.stdout}")
