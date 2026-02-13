"""将多段音频拼接为单文件（供合成阶段使用）。"""
import subprocess
from pathlib import Path

from config import get_settings


def concat_audio_files(input_paths: list[str | Path], output_path: str | Path) -> None:
    """使用 FFmpeg 将多段音频按顺序拼接为单个文件。"""
    if not input_paths:
        raise ValueError("至少需要一段音频")
    paths = [Path(p) for p in input_paths]
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f"音频文件不存在: {p}")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(paths) == 1:
        import shutil
        shutil.copy(str(paths[0]), str(out))
        return
    # 使用 concat demuxer：写临时文件列表
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in paths:
            f.write(f"file '{p.resolve()}'\n")
        list_path = f.name
    try:
        cmd = get_settings().ffmpeg_command
        subprocess.run(
            [cmd, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", str(out)],
            check=True,
            capture_output=True,
            timeout=300,
        )
    finally:
        Path(list_path).unlink(missing_ok=True)
