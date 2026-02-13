"""Manim 渲染与自愈：写临时文件、subprocess 调用、失败时 LLM 修复并重试。"""
import sys
import tempfile
from pathlib import Path

from config import get_settings
from llm_runner import invoke_plain


def _get_manim_args() -> list[str]:
    """
    返回用于 subprocess 的 manim 命令列表。
    优先用「当前 Python -m manim」或项目 .venv 内的 manim，不依赖 PATH。
    """
    import shutil
    configured = get_settings().manim_command.strip()
    # 配置为绝对路径且存在时，直接作为可执行文件用
    if Path(configured).is_absolute() and Path(configured).exists():
        return [configured]
    # 当前解释器同目录的 manim 或 python -m manim
    venv_bin = Path(sys.executable).resolve().parent
    manim_in_venv = venv_bin / "manim"
    if manim_in_venv.exists():
        return [str(manim_in_venv)]
    try:
        import manim  # noqa: F401
        return [sys.executable, "-m", "manim"]
    except ImportError:
        pass
    # 若当前解释器无 manim，尝试项目 .venv（例如未用 uv run 启动服务时）
    project_root = Path(__file__).resolve().parent.parent
    uv_venv_python = project_root / ".venv" / "bin" / "python"
    uv_venv_manim = project_root / ".venv" / "bin" / "manim"
    if uv_venv_manim.exists():
        return [str(uv_venv_manim)]
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
            pass
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
        shutil.copy(str(mp4s[0]), str(out_path))


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


def render_manim_video_with_self_heal(code_string: str, output_file: str | Path) -> None:
    """
    自愈循环：执行渲染，失败则用 LLM 修复代码后重试，最多 N 次（配置项）。
    """
    settings = get_settings()
    max_attempts = settings.manim_self_heal_max_attempts
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
