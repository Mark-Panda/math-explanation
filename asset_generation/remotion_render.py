"""
Remotion 视频渲染：将流水线产出的 steps + 时长 + TTS 音频合成为 MP4。
依赖项目内 remotion/ 子项目与 Node 环境；渲染前会写入 remotion-input.json 并复制音频到 remotion/public/audio/。
"""
import json
import logging
import shutil
import subprocess
from pathlib import Path

from problem_analysis.schemas import StepItem

logger = logging.getLogger(__name__)

# 项目根目录（asset_generation 的上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"
REMOTION_PUBLIC_AUDIO = REMOTION_DIR / "public" / "audio"


def _remotion_input_from_pipeline(
    steps: list[StepItem],
    durations: list[float],
    audio_prefix: str = "step",
) -> dict:
    """构造 Remotion 的 inputProps：steps + audioFileNames。"""
    step_inputs = []
    audio_file_names = []
    for i, step in enumerate(steps):
        duration_sec = durations[i] if i < len(durations) else 2.0
        step_inputs.append({
            "stepId": step.step_id,
            "description": step.description,
            "mathFormula": step.math_formula or "",
            "voiceoverText": step.voiceover_text or "",
            "durationSeconds": duration_sec,
        })
        audio_file_names.append(f"{audio_prefix}_{i + 1}.mp3")
    return {
        "steps": step_inputs,
        "audioFileNames": audio_file_names,
    }


def write_remotion_props_for_player(
    steps: list[StepItem],
    durations: list[float],
    audio_dir: Path,
    output_dir: Path,
    task_id: str,
    *,
    audio_prefix: str = "step",
    audio_base_url: str | None = None,
) -> None:
    """
    为 Remotion 网页播放准备：写入 remotion-props.json（含 audioUrls）并复制音频到 output_dir/audio/。
    供前端 Player 使用，audio_base_url 若为空则使用相对路径 /results/{task_id}/audio/。
    """
    output_dir = Path(output_dir).resolve()
    props = _remotion_input_from_pipeline(steps, durations, audio_prefix)
    base = (audio_base_url or "").rstrip("/")
    if not base:
        base = f"/results/{task_id}/audio"
    props["audioUrls"] = [f"{base}/{audio_prefix}_{i + 1}.mp3" for i in range(len(steps))]
    props_dir = output_dir / task_id
    props_dir.mkdir(parents=True, exist_ok=True)
    (props_dir / "remotion-props.json").write_text(
        json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    audio_dest = props_dir / "audio"
    audio_dest.mkdir(parents=True, exist_ok=True)
    for i in range(len(steps)):
        src = audio_dir / f"{audio_prefix}_{i + 1}.mp3"
        if src.is_file():
            shutil.copy2(src, audio_dest / src.name)
    logger.info("[remotion] 已写入 remotion-props 与音频至 %s", props_dir)


def render_remotion_video(
    steps: list[StepItem],
    durations: list[float],
    audio_dir: Path,
    output_file: Path,
    *,
    audio_prefix: str = "step",
    node_command: str = "node",
    remotion_dir: Path | None = None,
) -> None:
    """
    将 steps、时长与 audio_dir 下的 TTS 音频通过 Remotion 渲染为 MP4。

    :param steps: 题目分析得到的步骤列表
    :param durations: 每步时长（秒），与 steps 顺序一致
    :param audio_dir: 存放 step_1.mp3, step_2.mp3, ... 的目录（与 TTS prefix="step" 一致）
    :param output_file: 输出 MP4 路径
    :param audio_prefix: 音频文件名前缀，默认 "step"
    :param node_command: 用于执行 render.js 的 Node 可执行文件，默认 "node"
    :param remotion_dir: Remotion 项目目录，默认项目内 remotion/
    :raises FileNotFoundError: remotion 目录或 Node 不存在
    :raises RuntimeError: 渲染失败
    """
    remotion_dir = remotion_dir or REMOTION_DIR
    if not remotion_dir.is_dir():
        raise FileNotFoundError(f"Remotion 项目目录不存在: {remotion_dir}")

    output_file = Path(output_file).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    input_json_path = output_file.parent / "remotion-input.json"

    # 写入 Remotion inputProps
    input_props = _remotion_input_from_pipeline(steps, durations, audio_prefix)
    input_json_path.write_text(json.dumps(input_props, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[remotion] 已写入 %s", input_json_path)

    # 复制音频到 remotion/public/audio/
    REMOTION_PUBLIC_AUDIO.mkdir(parents=True, exist_ok=True)
    for i in range(len(steps)):
        src = audio_dir / f"{audio_prefix}_{i + 1}.mp3"
        if src.is_file():
            shutil.copy2(src, REMOTION_PUBLIC_AUDIO / src.name)
        else:
            logger.warning("[remotion] 音频不存在，将静音: %s", src)
    logger.info("[remotion] 已复制音频到 %s", REMOTION_PUBLIC_AUDIO)

    # 调用 Node 渲染脚本
    render_script = remotion_dir / "render.js"
    if not render_script.is_file():
        raise FileNotFoundError(f"渲染脚本不存在: {render_script}")

    cmd = [
        node_command,
        str(render_script),
        "--input", str(input_json_path),
        "--output", str(output_file),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(remotion_dir),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Remotion 渲染失败 (exit {proc.returncode}): {proc.stderr or proc.stdout}"
        )
    logger.info("[remotion] 视频已生成: %s", output_file)
