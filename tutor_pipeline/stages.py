"""Tutor 流水线各阶段：数学分析 → HTML 可视化 → 分镜 → TTS → 验证 → 脚手架 → 实现 → 检查渲染。"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import get_settings
from llm_runner import get_chat_model, invoke_multimodal_plain, invoke_plain
from langchain_core.messages import HumanMessage

from asset_generation.manim_render import render_manim_video_with_self_heal
from asset_generation.tts import generate_audio_with_duration_async
from tutor_pipeline.schemas import AudioInfo, AudioInfoEntry

import asyncio
import logging

logger = logging.getLogger(__name__)

# -------- 步骤 1：数学分析（tutor 格式：已知条件、推导事实、图形构建方法）--------

MATH_ANALYSIS_PROMPT = """你是一位数学专家。请分析以下数学题目，输出结构化的数学事实分析（Markdown）。

题目：
{problem_text}

请严格按以下 Markdown 结构输出，不要省略任何小节：

## 数学事实分析

### 已知条件
- 条件1：...
- 条件2：...

### 推导的事实
1. **事实名称**: 描述
   - 计算过程: ...
   - 数学表达: ...

### 图形构建方法
- 点的坐标: ...
- 边的关系: ...
- 圆/弧的定义: ...

### 需要证明的结论
- 结论1: ...

注意：禁止用坐标系设点来求解，应用几何推理（勾股、相似、等积变换等）。证明题的结论在分镜中可作为已确立事实使用。"""

MATH_ANALYSIS_PROMPT_WITH_IMAGE = """你是一位数学专家。请结合题目文字和附带的原始题目图片，分析数学题目，输出结构化的数学事实分析（Markdown）。

题目文字：
{problem_text}

请仔细观察附带的原始题目图片（几何形状、标注、公式），然后严格按以下 Markdown 结构输出：

## 数学事实分析

### 已知条件
- 条件1：...
- 条件2：...

### 推导的事实
1. **事实名称**: 描述
   - 计算过程: ...
   - 数学表达: ...

### 图形构建方法
- 点的坐标: ...
- 边的关系: ...
- 圆/弧的定义: ...

### 需要证明的结论
- 结论1: ...

注意：禁止用坐标系设点来求解，应用几何推理。以图片中的图形与标注为准。"""


def analyze_math_tutor(
    problem_text: str,
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
) -> str:
    """步骤1：输出 math_analysis.md 内容（tutor 格式）。"""
    problem_text = (problem_text or "").strip()
    if not problem_text:
        raise ValueError("题目文本不能为空")
    if image_base64:
        prompt = MATH_ANALYSIS_PROMPT_WITH_IMAGE.format(problem_text=problem_text)
        return invoke_multimodal_plain(
            prompt,
            content_type="image",
            image_base64=image_base64,
            image_mime_type=image_mime_type,
        )
    prompt = MATH_ANALYSIS_PROMPT.format(problem_text=problem_text)
    return invoke_plain(prompt)


# -------- 步骤 2：HTML 可视化 --------

HTML_VISUALIZATION_PROMPT = """你是一位数学动画设计师。根据以下数学事实分析，生成一份 HTML 文件内容，用 SVG 展示图形与画图过程。

数学事实分析：
{math_analysis}

要求：
- 输出完整 HTML 文档（含 <!DOCTYPE html>、<head>、<body>）
- 内含题目陈述、SVG 图形、分步解答、关键要素标注
- SVG 需展示画图过程（如：先画三角形 → 再画圆 → 标注点）
- 公式用 Unicode 符号（如 ²、√、°），不用 LaTeX
- 不依赖外部 CDN，自包含
"""


def generate_html_visualization(math_analysis: str) -> str:
    """步骤2：根据数学分析生成 数学_日期_题目.html 的 HTML 内容。"""
    return invoke_plain(
        HTML_VISUALIZATION_PROMPT.format(math_analysis=math_analysis)
    )


# -------- 步骤 3：分镜脚本 --------

STORYBOARD_PROMPT = """你是一位视频分镜设计师。根据以下数学事实分析和 HTML 可视化内容，生成分镜脚本（Markdown）。

数学事实分析：
{math_analysis}

HTML 可视化摘要（画图过程与要素）：
{html_summary}

要求：
1. 文件结构：先「## 分镜设计」，每个幕用「### 第N幕：幕名」，包含 **画面**、**字幕**（≤20字）、**读白**（口语化）、**动画**、**目的**。
2. 在动画部分用「→」或「退场」标明字幕退场时机。
3. 最后必须有「## 音频生成清单」的 Markdown 表格，列：幕号 | 文件名 | 读白文本 | 时长 | 说话人 | 情感。
4. 文件名格式：audio_001_幕名.wav（三位幕号），时长列留空。
5. 幕号从 1 开始连续编号，幕数按内容需要决定，不限制。
"""


def generate_storyboard(math_analysis: str, html_content: str) -> str:
    """步骤3：生成 分镜.md 内容。"""
    html_summary = html_content[:3000] + "..." if len(html_content) > 3000 else html_content
    return invoke_plain(
        STORYBOARD_PROMPT.format(
            math_analysis=math_analysis[:4000],
            html_summary=html_summary,
        )
    )


# -------- 分镜表格解析与 TTS --------


def _parse_audio_table_from_storyboard(storyboard_md: str) -> list[tuple[int, str, str]]:
    """
    从分镜 Markdown 中解析「## 音频生成清单」表格，返回 [(幕号, 文件名, 读白文本), ...]。
    """
    # 定位表格：## 音频生成清单 之后的第一个 |...| 块
    in_table = False
    rows: list[tuple[int, str, str]] = []
    for line in storyboard_md.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("## ") and "音频" in line_stripped:
            in_table = True
            continue
        if not in_table:
            continue
        if not line_stripped.startswith("|") or line_stripped == "|" or "---" in line_stripped:
            if rows:
                break
            continue
        parts = [p.strip() for p in line_stripped.split("|") if p.strip() != ""]
        # 列顺序：幕号 | 文件名 | 读白文本 | 时长 | 说话人 | 情感
        if len(parts) >= 3:
            try:
                scene_num = int(parts[0])
                file_name = parts[1].strip()
                voiceover = parts[2].strip().strip('"\'')
                rows.append((scene_num, file_name, voiceover))
            except (ValueError, IndexError):
                continue
    return rows


async def generate_tts_from_storyboard_async(
    storyboard_md: str,
    output_dir: str | Path,
    *,
    voice: str | None = None,
) -> tuple[list[float], AudioInfo]:
    """
    步骤4：根据分镜中的音频清单生成 wav 并写 audio_info.json。
    返回 (durations, AudioInfo)。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _parse_audio_table_from_storyboard(storyboard_md)
    if not rows:
        raise ValueError("分镜中未解析到音频生成清单表格，请确保包含「## 音频生成清单」及表头与数据行")

    voice = voice or get_settings().tts_voice
    durations: list[float] = []
    entries: list[AudioInfoEntry] = []
    default_dur = get_settings().default_wait_seconds

    for scene_num, file_name, voiceover in rows:
        if not file_name.lower().endswith(".wav"):
            file_name = file_name.rstrip() + ".wav" if not file_name.endswith(".wav") else file_name
        out_path = output_dir / file_name
        text = (voiceover or "").strip()
        if not text:
            durations.append(default_dur)
            entries.append(AudioInfoEntry(scene=scene_num, file=file_name, duration=default_dur))
            continue
        dur = await generate_audio_with_duration_async(text, out_path, voice=voice)
        durations.append(dur)
        entries.append(AudioInfoEntry(scene=scene_num, file=file_name, duration=dur))

    audio_info = AudioInfo(files=entries)
    info_path = output_dir / "audio_info.json"
    info_path.write_text(audio_info.model_dump_json(indent=2), encoding="utf-8")
    return durations, audio_info


def generate_tts_from_storyboard(
    storyboard_md: str,
    output_dir: str | Path,
    *,
    voice: str | None = None,
) -> tuple[list[float], AudioInfo]:
    """同步封装。"""
    return asyncio.run(
        generate_tts_from_storyboard_async(storyboard_md, output_dir, voice=voice)
    )


def validate_audio(audio_dir: str | Path, audio_info: AudioInfo) -> None:
    """
    步骤5：验证音频文件存在且时长>0；数量与分镜一致。
    异常时抛出 ValueError。
    """
    audio_dir = Path(audio_dir)
    for entry in audio_info.files:
        p = audio_dir / entry.file
        if not p.exists():
            raise ValueError(f"缺少第{entry.scene}幕音频文件: {entry.file}")
        if entry.duration <= 0:
            raise ValueError(f"第{entry.scene}幕音频时长异常: {entry.file}")


# -------- 步骤 6：脚手架 --------

SCRIPT_SCAFFOLD_TEMPLATE = '''from manim import *
import json
import os

class MathScene(Scene):
    """数学教学视频场景 - 根据分镜与音频信息生成动画。"""

    COLORS = {{
        "background": "#1a1a2e",
        "primary": "#4ecca3",
        "secondary": "#e94560",
        "highlight": "#ffc107",
        "text": "#ffffff",
        "grid": "#2a2a4e",
    }}

    SCENES = [
{scenes_py_list}
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audio_timings = self._load_audio_timings()

    def _load_audio_timings(self):
        return {{int(e["scene"]): float(e["duration"]) for e in self._audio_info.get("files", [])}}

    def calculate_geometry(self):
        geometry = {{"points": {{}}, "lines": {{}}, "circles": {{}}, "arcs": {{}}}}
        return geometry

    def assert_geometry(self, geometry):
        pass

    def define_elements(self, geometry):
        return {{"points": {{}}, "lines": {{}}, "circles": {{}}, "labels": {{}}}}

    def construct(self):
        geometry = self.calculate_geometry()
        self.assert_geometry(geometry)
        elements = self.define_elements(geometry)
        self.camera.background_color = self.COLORS["background"]
        for scene_num, scene_name, audio_file, duration in self.SCENES:
            self.play_scene(scene_num, scene_name, audio_file, duration, elements, geometry)

    def play_scene(self, scene_num, scene_name, audio_file, duration, elements, geometry):
        self.add_sound(str(self._audio_dir / audio_file))
        self.wait(duration)
'''


def generate_scaffold(audio_info: AudioInfo, audio_dir: str | Path) -> str:
    """步骤6：生成 script.py 脚手架（含 SCENES 与 _audio_info、_audio_dir）。"""
    # SCENES: (幕号, 幕名, 文件名, 时长)
    scenes_py = []
    for e in audio_info.files:
        name = Path(e.file).stem.replace("audio_" + str(e.scene).zfill(3) + "_", "")
        scenes_py.append(f'        ({e.scene}, "{name}", "{e.file}", {e.duration}),')
    scenes_py_list = "\n".join(scenes_py)
    code = SCRIPT_SCAFFOLD_TEMPLATE.format(scenes_py_list=scenes_py_list)
    # 注入 _audio_info 和 _audio_dir：在 __init__ 里设置
    code = code.replace(
        "self.audio_timings = self._load_audio_timings()",
        "self._audio_info = {}\n        _ap = Path(__file__).resolve().parent / \"audio_info.json\"\n        if _ap.exists():\n            import json\n            with open(_ap, \"r\", encoding=\"utf-8\") as _f:\n                self._audio_info = json.load(_f)\n        self._audio_dir = Path(__file__).resolve().parent / \"audio\"\n        self.audio_timings = self._load_audio_timings()",
    )
    code = code.replace(
        "import os",
        "import os\nfrom pathlib import Path",
    1,
    )
    # _load_audio_timings 需要读 self._audio_info
    code = code.replace(
        'return {int(e["scene"]): float(e["duration"]) for e in self._audio_info.get("files", [])}',
        'return {int(e["scene"]): float(e["duration"]) for e in (self._audio_info or {}).get("files", [])}',
    )
    return code


# -------- 步骤 7：实现完整 script.py --------

IMPLEMENT_SCRIPT_PROMPT = """你是一位 Manim 动画工程师。请根据以下数学分析、分镜脚本和 audio_info，将给定的 script.py 脚手架补全为可运行的完整代码。

要求：
1. calculate_geometry() 必须根据数学分析和分镜完整实现（点、线、圆等，z 坐标均为 0）。
2. assert_geometry() 验证题目条件（边长、中点、直角等）及画布范围，用中文报错。
3. 每幕 play_scene 第一行必须 self.add_sound(str(self._audio_dir / audio_file))，动画时长 >= 音频时长。
4. 读白提到什么就高亮什么；字幕需有退场（分镜中 → 或 退场）。
5. 全部用 Text，不用 MathTex（避免 LaTeX 依赖）。
6. 只输出完整 Python 代码，不要解释。类名保持 MathScene；脚本同目录下会有 audio 文件夹和 audio_info.json，__init__ 中已加载。
7. **Manim Community Edition 兼容**：虚线必须用 DashedLine(start, end) 或 DashedVMobject(line)，不要给 Line() 传 dash_length、dash_ratio 等参数（Line 不接受这些，会报 TypeError）。
8. **避免文字重叠**：所有字幕/标题使用固定区域（如画面下方 1/4 处），同一时间只保留当前句字幕，新字幕出现前先 FadeOut 或 Uncreate 上一句；图形上的标签用 .next_to(点/线, direction) 或 .shift() 放在对应元素外侧，避免标签之间、标签与字幕重叠；多段文字不要同时放在画面中央。

数学事实分析（供几何计算参考）：
{math_analysis}

分镜脚本：
{storyboard}

audio_info.json 内容：
{audio_info_json}

当前脚手架（请在此基础上补全并返回完整 script.py 内容）：
{scaffold}
"""


def implement_script(
    scaffold: str,
    storyboard_md: str,
    audio_info: AudioInfo,
    *,
    math_analysis: str = "",
) -> str:
    """步骤7：LLM 根据分镜与 audio_info 生成完整 script.py。"""
    prompt = IMPLEMENT_SCRIPT_PROMPT.format(
        math_analysis=(math_analysis or "")[:4000],
        storyboard=storyboard_md[:8000],
        audio_info_json=audio_info.model_dump_json(indent=2),
        scaffold=scaffold[:6000],
    )
    llm = get_chat_model(timeout=get_settings().llm_script_timeout)
    msg = llm.invoke([HumanMessage(content=prompt)])
    raw = msg.content if hasattr(msg, "content") else str(msg)
    # 去掉可能的 markdown 代码块
    if "```python" in raw:
        raw = re.sub(r"^```python\s*\n?", "", raw)
    if "```" in raw:
        raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip()


# -------- 步骤 8：检查与渲染 --------


def check_script_has_required(script_code: str) -> list[str]:
    """检查 script.py 是否包含必备项，返回错误列表（空则通过）。"""
    errs: list[str] = []
    if "def calculate_geometry" not in script_code:
        errs.append("缺少 calculate_geometry()")
    if "def assert_geometry" not in script_code:
        errs.append("缺少 assert_geometry()")
    if "add_sound" not in script_code:
        errs.append("缺少 add_sound() 调用（音频集成）")
    if "class " in script_code and "Scene" not in script_code:
        errs.append("未找到继承 Scene 的类")
    return errs


def render_tutor_video(
    script_code: str,
    audio_dir: Path,
    audio_info: AudioInfo,
    output_mp4: Path,
    *,
    scene_class: str | None = None,
) -> None:
    """
    调用 Manim 渲染；失败时用 LLM 修复脚本后重试（最多 MANIM_SELF_HEAL_MAX_ATTEMPTS 次）。
    """
    from asset_generation import manim_render

    settings = get_settings()
    max_attempts = getattr(settings, "manim_self_heal_max_attempts", 3)
    current_code = script_code
    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            manim_render.render_manim_script(
                current_code,
                output_mp4,
                scene_class=scene_class or settings.manim_scene_class,
                quality=settings.manim_quality,
                audio_dir=Path(audio_dir),
                audio_info_dict=audio_info.model_dump(),
            )
            return
        except FileNotFoundError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt >= max_attempts - 1:
                raise RuntimeError(
                    f"Manim 自愈已达最大重试次数 {max_attempts}，最后错误: {last_error}"
                ) from e
            logger.info("[tutor] Manim 渲染失败，尝试 LLM 修复脚本 (第 %d 次)…", attempt + 1)
            current_code = manim_render.fix_tutor_script_with_llm(current_code, last_error)
            if not (current_code and current_code.strip()):
                raise RuntimeError("LLM 未返回有效脚本代码") from e
            # 去掉可能的 markdown 代码块
            if "```python" in current_code:
                current_code = re.sub(r"^```python\s*\n?", "", current_code)
            if "```" in current_code:
                current_code = re.sub(r"\n?```\s*$", "", current_code)
            current_code = current_code.strip()
