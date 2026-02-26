"""Manim 渲染与自愈：写临时文件、subprocess 调用、失败时 LLM 修复并重试。"""
import sys
import tempfile
from pathlib import Path

from config import get_settings
from llm_runner import invoke_plain


def _project_venv_manim_candidates() -> list[Path]:
    """项目 .venv 下可能的 manim 可执行路径（Unix bin / Windows Scripts）。"""
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        project_root / ".venv" / "bin" / "manim",
        project_root / ".venv" / "Scripts" / "manim.exe",
        project_root / ".venv" / "Scripts" / "manim",
    ]
    return [p for p in candidates if p.exists()]


def _get_manim_args() -> list[str]:
    """
    返回用于 subprocess 的 manim 命令列表。
    优先用 MANIM_COMMAND 绝对路径、当前解释器同目录 manim、当前解释器 python -m manim、
    项目 .venv 内 manim（含 Windows Scripts）、最后 which(configured)。
    """
    import shutil
    configured = (get_settings().manim_command or "").strip()
    # 配置为绝对路径且存在时，直接使用
    if configured and Path(configured).is_absolute() and Path(configured).exists():
        return [configured]
    # 当前解释器同目录的 manim
    venv_bin = Path(sys.executable).resolve().parent
    manim_in_venv = venv_bin / "manim"
    if manim_in_venv.exists():
        return [str(manim_in_venv)]
    try:
        import manim  # noqa: F401
        return [sys.executable, "-m", "manim"]
    except ImportError:
        pass
    # 项目 .venv（支持 Windows Scripts）
    for manim_path in _project_venv_manim_candidates():
        return [str(manim_path)]
    # 项目 .venv 的 python -m manim（有时只有模块无脚本）
    project_root = Path(__file__).resolve().parent.parent
    for py_name in ("bin/python", "Scripts/python.exe", "Scripts/python"):
        uv_venv_python = project_root / ".venv" / py_name
        if uv_venv_python.exists():
            try:
                import subprocess
                subprocess.run(
                    [str(uv_venv_python), "-c", "import manim"],
                    capture_output=True,
                    timeout=5,
                    check=True,
                )
                return [str(uv_venv_python), "-m", "manim"]
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
                continue
    if configured:
        found = shutil.which(configured)
        if found:
            return [found]
    return []


def _strip_markdown_code_block(code: str) -> str:
    """
    若代码被 markdown 代码块包裹（如 ```python ... ```），去掉首尾的围栏行，
    保证写入 scene.py 的是纯 Python，避免 SyntaxError。
    """
    s = code.strip()
    lines = s.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def render_manim_video(code_string: str, output_file: str | Path) -> None:
    """
    将代码写入临时目录的 .py 文件，subprocess 调用 manim CLI 渲染 SolutionScene。
    渲染成功后从 manim 输出目录找到生成的 .mp4 并复制到 output_file。
    若退出码非 0，抛出 RuntimeError 并附带 stderr（供自愈使用）。
    """
    import shutil
    import subprocess
    manim_args = _get_manim_args()
    if not manim_args:
        configured = get_settings().manim_command
        raise FileNotFoundError(
            f"未找到 manim。请在本项目中执行: uv sync（并先装 Manim 系统依赖，见 README），并使用 uv run 启动服务（如 uv run uvicorn main:app ...）。"
            f"或设置 MANIM_COMMAND 为 manim 可执行文件的绝对路径。"
        )
    out_path = Path(output_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    code_clean = _strip_markdown_code_block(code_string)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        scene_py = tmpdir / "scene.py"
        scene_py.write_text(code_clean, encoding="utf-8")
        proc = subprocess.run(
            [*manim_args, str(scene_py), "SolutionScene", "-ql"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(tmpdir),
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Manim 渲染失败 (exit {proc.returncode}): {proc.stderr or proc.stdout}")
        # manim 输出到 <cwd>/media/videos/scene/720p30/SolutionScene.mp4 等
        media = tmpdir / "media" / "videos"
        mp4s = list(media.rglob("*.mp4"))
        if not mp4s:
            raise RuntimeError("Manim 未生成 mp4 文件")
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = out_path.parent / (out_path.name + ".tmp")
        shutil.copy(str(mp4s[0]), str(tmp_dest))
        if not tmp_dest.exists():
            raise RuntimeError(f"复制视频失败，临时文件不存在: {tmp_dest}")
        tmp_dest.replace(out_path)
        if not out_path.exists():
            raise RuntimeError(f"复制视频失败，目标不存在: {out_path}")


def fix_code_with_llm(bad_code: str, error_msg: str) -> str:
    """通过 LangChain 将错误信息与代码发 LLM 请求修复，返回新代码。"""
    prompt = f"""这段 Manim 代码运行报错，请修复后只返回完整可运行的 Python 代码，不要解释。

错误信息:
{error_msg}

代码:
```python
{bad_code}
```

请直接输出修复后的完整代码（保留 SolutionScene 类和 self.wait() 占位）。"""
    return invoke_plain(prompt)


def _extract_syntax_error_highlight(error_msg: str) -> str:
    """若错误信息中含 SyntaxError，提取首段「行号 + 问题行」并置顶，便于 LLM 优先看到。"""
    import re
    m = re.search(
        r"File [^\n]+script\.py\", line (\d+)\s*\n\s*(.+?)(?:\n\s*\^)?",
        error_msg,
        re.DOTALL,
    )
    syn = re.search(r"SyntaxError:\s*([^\n]+)", error_msg)
    if m and syn:
        line_no, line_content = m.group(1), (m.group(2) or "").strip()[:120]
        return f"【关键】SyntaxError: {syn.group(1).strip()}\n  出错行号: {line_no}\n  该行内容: {line_content}\n\n完整错误:\n"
    return ""


def fix_tutor_script_with_llm(bad_code: str, error_msg: str) -> str:
    """Tutor 脚本渲染失败时，用 LLM 修复后返回新代码。要求保留 MathScene、Manim CE 兼容。"""
    highlight = _extract_syntax_error_highlight(error_msg)
    if highlight:
        error_msg = highlight + error_msg
    # 错误过长时保留开头（含可能的【关键】）与末尾，避免挤占 token
    err_max = 40000
    if len(error_msg) > err_max:
        head = error_msg[:600] if highlight else ""
        tail = error_msg[-err_max:]
        error_msg = (head + "\n...(中段堆栈省略)...\n" + tail) if head else "(前段省略)\n...\n" + tail
    prompt = f"""这段 Manim 脚本运行报错，请修复后只返回完整可运行的 Python 代码，不要解释。

错误信息:
{error_msg}

代码:
```python
{bad_code}
```

要求：保留 MathScene 类与 construct/play_scene 结构；使用 Manim Community Edition 兼容写法（虚线用 DashedLine 或 DashedVMobject，不要给 Line 传 dash_length）。辅助线必须用 calculate_geometry() 中已计算好的点作为 DashedLine 的端点，不可随意设坐标。**题目与解析分区域**：题目在上半部分（y≈2.5~3.5 或 .to_edge(UP)），解析/字幕在下半部分（y≈-2.8~-3.5 或 .to_edge(DOWN)），图形在中间，互不覆盖；同一时间只保留当前句字幕，新句前先 FadeOut 上一句；图形标签用 .next_to 放在元素外侧，避免重叠。若涉及图形被裁切或未完全显示，将主图形放入 VGroup 后按外接范围 scale 与 move_to(ORIGIN)，确保整图在画面 x∈[-7,7]、y∈[-4,4] 内且居中。只输出修复后的完整代码。"""
    return invoke_plain(prompt)


def render_manim_video_with_self_heal(code_string: str, output_file: str | Path) -> None:
    """
    自愈循环：执行渲染，失败则用 LLM 修复代码后重试，最多 N 次（配置项）。
    """
    settings = get_settings()
    max_attempts = getattr(settings, "manim_self_heal_max_attempts", 3)
    current_code = code_string
    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            render_manim_video(current_code, output_file)
            return
        except FileNotFoundError as e:
            # 未安装 manim 等环境问题，不重试
            raise RuntimeError(
                f"Manim 渲染失败（环境问题）: {e}. "
                "请安装 Manim: uv sync（见 README 系统依赖）或 pip install manim，并用 uv run 启动服务。"
            ) from e
        except Exception as e:
            last_error = str(e)
            if attempt == max_attempts - 1:
                raise RuntimeError(f"Manim 自愈已达最大重试次数 {max_attempts}，最后错误: {last_error}") from e
            current_code = fix_code_with_llm(current_code, last_error)
    raise RuntimeError(f"Manim 自愈失败: {last_error}")


def render_manim_script(
    script_code: str,
    output_file: str | Path,
    *,
    scene_class: str | None = None,
    quality: str | None = None,
    audio_dir: str | Path | None = None,
    audio_info_dict: dict | None = None,
) -> Path:
    """
    Tutor 流水线用：渲染给定脚本代码，使用指定场景类名与质量。
    script_code 写入临时目录的 script.py；若提供 audio_dir，会复制到临时目录 audio/，
    并写入 audio_info.json，以便脚本内 Path(__file__).parent / "audio" 与 audio_info.json 可用。
    返回实际写入的 mp4 文件路径（与 output_file 解析后的路径一致）。
    """
    import shutil
    import subprocess

    scene_class = scene_class or getattr(get_settings(), "manim_scene_class", "MathScene")
    quality = quality or getattr(get_settings(), "manim_quality", "qh")
    quality_flag = "-" + quality if (quality and quality.startswith("q")) else "-q" + (quality or "h")
    manim_args = _get_manim_args()
    if not manim_args:
        project_root = Path(__file__).resolve().parent.parent
        expected = project_root / ".venv" / "bin" / "manim"
        if not expected.exists():
            expected = project_root / ".venv" / "Scripts" / "manim.exe"
        expected_str = str(expected.resolve()) if expected.exists() else str((project_root / ".venv" / "bin" / "manim").resolve())
        raise FileNotFoundError(
            "未找到 manim。请在本项目目录执行 uv sync 安装 Manim 后，用该环境启动服务（如 uv run uvicorn main:app ...）；"
            "或若 manim 已在别处安装，在 .env 中设置 MANIM_COMMAND 为可执行文件绝对路径，例如：MANIM_COMMAND=" + expected_str
        )
    out_path = Path(output_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    code_clean = _strip_markdown_code_block(script_code)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        script_py = tmpdir / "script.py"
        script_py.write_text(code_clean, encoding="utf-8")
        if audio_dir is not None:
            src = Path(audio_dir)
            if src.exists():
                dest_audio = tmpdir / "audio"
                shutil.copytree(src, dest_audio)
            if audio_info_dict is not None:
                import json
                (tmpdir / "audio_info.json").write_text(
                    json.dumps(audio_info_dict, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        proc = subprocess.run(
            [*manim_args, str(script_py), scene_class, quality_flag],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(tmpdir),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Manim 渲染失败 (exit {proc.returncode}): {proc.stderr or proc.stdout}"
            )
        media = tmpdir / "media" / "videos"
        mp4s = list(media.rglob("*.mp4"))
        if not mp4s:
            raise RuntimeError("Manim 未生成 mp4 文件")
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = out_path.parent / (out_path.name + ".tmp")
        shutil.copy(str(mp4s[0]), str(tmp_dest))
        if not tmp_dest.exists():
            raise RuntimeError(f"复制视频失败，临时文件不存在: {tmp_dest}")
        tmp_dest.replace(out_path)
        if not out_path.exists():
            raise RuntimeError(f"复制视频失败，目标不存在: {out_path}")
        return out_path
