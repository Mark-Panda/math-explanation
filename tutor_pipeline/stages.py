"""Tutor 流水线各阶段：数学分析 → HTML 可视化 → 分镜 → TTS → 验证 → 脚手架 → 实现 → 检查渲染。"""
import ast
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
- **辅助线**：若有垂线、角平分线、中线等，必须写明每条辅助线的端点/垂足/交点如何由已知点与几何关系确定（例如：过 D 作 BC 的垂线垂足为 E，则 E 在 BC 上且 DE ⟂ BC，可用向量投影求 E 的坐标；角平分线与对边的交点可按边长比例计算）。便于后续动画中辅助线位置正确。

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
- **辅助线**：若有垂线、角平分线、中线等，必须写明每条辅助线的端点/垂足/交点如何由已知点与几何关系确定（例如：垂足在直线上且满足垂直；角平分线与对边交点按比例）。以图片中辅助线的实际位置为准。

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
2. **画面布局**：题目（题干）在上半部分展示，解析/步骤字幕在下半部分展示，图形在中间，这样题目与解析不会重叠；在画面描述中可注明「题目区在上」「字幕区在下」。
3. 在动画部分用「→」或「退场」标明字幕退场时机。
4. 最后必须有「## 音频生成清单」的 Markdown 表格，列：幕号 | 文件名 | 读白文本 | 时长 | 说话人 | 情感。
5. 文件名格式：audio_001_幕名.wav（三位幕号），时长列留空。
6. 幕号从 1 开始连续编号，幕数按内容需要决定，不限制。
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
    支持 ## / ### 标题；若无表格则从「### 第N幕」与「**读白**」回退提取。
    """
    lines = storyboard_md.splitlines()
    # 1) 定位表格：## 或 ### 且含「音频」或「清单」的标题后的 |...| 块
    in_table = False
    rows: list[tuple[int, str, str]] = []
    for line in lines:
        line_stripped = line.strip()
        is_audio_heading = (
            (line_stripped.startswith("## ") or line_stripped.startswith("### "))
            and ("音频" in line_stripped or "清单" in line_stripped)
        )
        if is_audio_heading:
            in_table = True
            continue
        if not in_table:
            continue
        if not line_stripped.startswith("|") or line_stripped == "|" or "---" in line_stripped:
            if rows:
                break
            continue
        parts = [p.strip() for p in line_stripped.split("|") if p.strip() != ""]
        if len(parts) >= 3:
            try:
                scene_num = int(parts[0])
                file_name = parts[1].strip()
                voiceover = parts[2].strip().strip('"\'')
                rows.append((scene_num, file_name, voiceover))
            except (ValueError, IndexError):
                continue
    if rows:
        return rows

    # 2) 回退：从「### 第N幕：xxx」与「**读白**：yyy」提取
    fallback: list[tuple[int, str, str]] = []
    current_num: int | None = None
    current_title = ""
    voiceover = ""
    for line in lines:
        line_stripped = line.strip()
        m = re.match(r"^#+\s*第\s*(\d+)\s*幕\s*[：:]?\s*(.*)", line_stripped)
        if m:
            if current_num is not None and voiceover:
                name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (current_title or str(current_num))[:30]).strip("_") or str(current_num)
                fallback.append(
                    (current_num, f"audio_{current_num:03d}_{name}.wav", voiceover.strip())
                )
            current_num = int(m.group(1))
            current_title = (m.group(2) or "").strip().strip("：:")
            voiceover = ""
            continue
        if current_num is not None and ("读白" in line_stripped or "**读白**" in line_stripped):
            after_colon = re.sub(r"^\*?\*?读白\*?\*?\s*[：:]\s*", "", line_stripped).strip()
            if after_colon:
                voiceover = after_colon
    if current_num is not None and voiceover:
        name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (current_title or str(current_num))[:30]).strip("_") or str(current_num)
        fallback.append((current_num, f"audio_{current_num:03d}_{name}.wav", voiceover.strip()))
    return fallback


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
        raise ValueError(
            "分镜中未解析到音频生成清单。请确保：(1) 包含「## 音频生成清单」或「### 音频清单」及下方 Markdown 表格（幕号|文件名|读白文本|...），"
            "或 (2) 每幕为「### 第N幕：标题」且含「**读白**：文本」以便回退解析。"
        )

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
        try:
            dur = await generate_audio_with_duration_async(text, out_path, voice=voice)
        except Exception as e:
            logger.exception("[TTS] 生成失败 幕=%s 文件=%s", scene_num, file_name)
            raise RuntimeError(
                f"TTS 生成失败（幕 {scene_num}，文件 {file_name}）：{e}"
            ) from e
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
1. calculate_geometry() 必须根据数学分析和分镜完整实现（点、线、圆等，z 坐标均为 0）。**辅助线（垂线、角平分线、中线等）的端点、垂足、与边的交点必须按几何关系在代码中计算得出**（例如：垂足 E = 点 D 在直线 BC 上的投影，可用向量点积求投影点；角平分线与对边交点可按边长比例或定比分点公式计算），不得随意写死坐标，否则辅助线位置会错。
2. assert_geometry() 验证题目条件（边长、中点、直角等）、**辅助线的几何关系**（如垂足在直线上、垂线垂直、角平分线过顶点等）及画布范围，用中文报错。
3. 每幕 play_scene 第一行必须 self.add_sound(str(self._audio_dir / audio_file))，动画时长 >= 音频时长。
4. 读白提到什么就高亮什么；字幕需有退场（分镜中 → 或 退场）。
5. 全部用 Text，不用 MathTex（避免 LaTeX 依赖）。
6. 只输出完整 Python 代码，不要解释。类名保持 MathScene；脚本同目录下会有 audio 文件夹和 audio_info.json，__init__ 中已加载。
7. **Manim Community Edition 兼容**：虚线必须用 DashedLine(start, end) 或 DashedVMobject(line)，不要给 Line() 传 dash_length、dash_ratio 等参数（Line 不接受这些，会报 TypeError）。**辅助线（如垂线 DE）必须用 geometry 中已计算好的点**（如 geometry["points"]["E"]、geometry["points"]["D"]）作为 DashedLine 的端点，不可在 play_scene 里重新设点，否则位置会错。**点的坐标运算**：geometry["points"] 的值是 (x,y,z) 元组。对点做位移时必须写 np.array(point) + (dx,dy,dz)，不能写 point + (dx,dy,dz)（Python 元组相加是拼接，会得到 (x,y,z,dx,dy,dz) 长度为 6，导致 ValueError: could not broadcast (1,6) into (1,3)）。DashedLine/Line 的 start、end 须为长度 3 的坐标，脚本中需 `import numpy as np`。
8. **题目与解析分区域**：题目（题干）与解析（步骤字幕、推导文字）必须在不同区域，不得重叠。建议：**题目区**固定在上半部分（如 y≈2.5~3.5 或 .to_edge(UP, buff=0.5)），仅在第一幕或引入时展示，后续可 FadeOut 或保留在上方不占解析区；**解析/字幕区**固定在下半部分（如 y≈-2.8~-3.5 或 .to_edge(DOWN, buff=0.5)），所有步骤说明、字幕、推导文字都放在该区域，同一时间只保留当前句，新句出现前先 FadeOut 上一句；**图形区**在中间（y≈-1.5~1.5）。这样题目在上、解析在下、图形居中，互不覆盖。
9. **避免其他重叠**：图形上的标签用 .next_to(点/线, direction) 或 .shift() 放在对应元素外侧，避免标签之间、标签与字幕重叠。
10. **图形完整显示**：Manim 默认画面范围约 x∈[-7.1, 7.1]、y∈[-4, 4]。**必须在 calculate_geometry() 内使所有点的坐标落在 [-6, 6]×[-3.5, 3.5] 内（留边距）**，避免 assert_geometry 时因边界等于 ±7/±4 或浮点误差导致 AssertionError（如「y坐标超出范围[0, 4.8]」）。做法：在 calculate_geometry 末尾根据所有点的 min_x,max_x,min_y,max_y 计算缩放系数 scale 与平移量，对 geometry["points"] 中每个点统一缩放并平移至中心后再返回；或一开始就用保守的缩放（如 0.8）与原点居中。assert_geometry() 中做画布范围检查时用中文报错并给出建议缩放/平移量。
11. **括号与语法**：所有 self.play(...)、Write(...)、FadeOut(...) 等调用必须括号成对，勿漏写闭合的 )，例如 self.play(Write(obj), run_time=1) 不能写成 run_time=0 后缺 )；每行括号、方括号、花括号都要成对闭合。
12. **self.wait 必须为正数**：Manim 要求 self.wait(duration) 的 duration 严格大于 0。不可写 self.wait(max(0, ...))，否则会报 "duration of 0 <= 0 seconds"。应写 self.wait(max(0.5, duration)) 或 self.wait(max(0.5, duration - 已用时长))，保证传入的始终是正数（如至少 0.5 秒）。

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
    """步骤7：LLM 根据分镜与 audio_info 生成完整 script.py。走多模型重试与 script 超时。"""
    from llm_runner import _with_model_fallback_and_retry
    from config import get_llm_model_list, get_settings

    prompt = IMPLEMENT_SCRIPT_PROMPT.format(
        math_analysis=(math_analysis or "")[:4000],
        storyboard=storyboard_md[:8000],
        audio_info_json=audio_info.model_dump_json(indent=2),
        scaffold=scaffold[:6000],
    )
    s = get_settings()
    models = get_llm_model_list()

    def do(m: str) -> str:
        llm = get_chat_model(model=m, timeout=s.llm_script_timeout)
        msg = llm.invoke([HumanMessage(content=prompt)])
        raw = msg.content if hasattr(msg, "content") else str(msg)
        # 去掉可能的 markdown 代码块
        if "```python" in raw:
            raw = re.sub(r"^```python\s*\n?", "", raw)
        if "```" in raw:
            raw = re.sub(r"\n?```\s*$", "", raw)
        out = raw.strip()
        if not out:
            raise ValueError("脚本生成模型返回内容为空")
        return out

    return _with_model_fallback_and_retry(models, s.llm_retry_per_model, do)


# -------- 步骤 8：检查与渲染 --------


def _inject_add_sound_if_missing(script_code: str) -> str:
    """若脚本缺少 add_sound，在 play_scene 方法体首行注入；无 play_scene 则在 construct 首行注入。"""
    if "add_sound" in script_code:
        return script_code
    add_sound_line = "self.add_sound(str(self._audio_dir / audio_file))\n"

    # 1) 有 play_scene：在方法体首行前注入
    if "def play_scene" in script_code:
        # 匹配 def play_scene(...): 后至下一行缩进（允许 ): 后带注释、空行）
        match = re.search(
            r"def play_scene\s*\([^)]*\)\s*:\s*(?:#.*?)?\s*\n\s*\n?(\s+)",
            script_code,
            re.DOTALL,
        )
        if not match:
            # 回退：找 "def play_scene" 再找 "):" 再找换行与缩进
            idx = script_code.find("def play_scene")
            if idx != -1:
                rest = script_code[idx:]
                paren = rest.find("):")
                if paren != -1:
                    after_paren = rest[paren + 2 :]
                    m = re.match(r"\s*\n+(\s*)", after_paren)
                    if m:
                        indent = m.group(1)
                        insert_at = idx + paren + 2 + m.end()
                        return (
                            script_code[:insert_at]
                            + indent
                            + add_sound_line.strip()
                            + "\n"
                            + script_code[insert_at:]
                        )
        else:
            indent = match.group(1)
            pos = match.end()
            return script_code[:pos] + indent + add_sound_line.strip() + "\n" + script_code[pos:]

    # 2) 无 play_scene 但有 construct：在 construct 方法体首行前注入（满足检查项）
    if "def construct" in script_code and "Scene" in script_code:
        match = re.search(
            r"def construct\s*\([^)]*\)\s*:\s*(?:#.*?)?\s*\n\s*\n?(\s+)",
            script_code,
            re.DOTALL,
        )
        if match:
            indent = match.group(1)
            pos = match.end()
            return script_code[:pos] + indent + add_sound_line.strip() + "\n" + script_code[pos:]

    return script_code


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
) -> Path:
    """
    调用 Manim 渲染；失败时用 LLM 修复脚本后重试（最多 MANIM_SELF_HEAL_MAX_ATTEMPTS 次）。
    返回实际写入的 mp4 文件路径。
    """
    from asset_generation import manim_render

    settings = get_settings()
    max_attempts = max(1, int(getattr(settings, "manim_self_heal_max_attempts", 3)))
    current_code = script_code
    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            # 渲染前先做语法检查，SyntaxError 时用简洁错误信息让 LLM 修复，避免长堆栈干扰
            try:
                ast.parse(current_code)
            except SyntaxError as syn_err:
                err_text = f"SyntaxError: {syn_err.msg}\n  行 {syn_err.lineno}: {syn_err.text or ''}"
                if syn_err.offset is not None and syn_err.text:
                    err_text += f"\n  该行第 {syn_err.offset} 个字符附近有误，请补全括号或修正语法。"
                last_error = err_text
                # 先尝试自动补全 ", run" 后缺失的 "time=1)"
                fixed = current_code
                if "was never closed" in (syn_err.msg or "") and syn_err.lineno and 1 <= syn_err.lineno <= current_code.count("\n") + 1:
                    lines = current_code.splitlines()
                    idx = syn_err.lineno - 1
                    if 0 <= idx < len(lines):
                        line = lines[idx]
                        if re.search(r",\s*run\s*$", line):
                            lines[idx] = line.rstrip() + "_time=1)"
                        elif re.search(r",\s*run_\s*$", line):
                            lines[idx] = line.rstrip() + "time=1)"
                        else:
                            lines = None
                        if lines is not None:
                            fixed = "\n".join(lines)
                            try:
                                ast.parse(fixed)
                                current_code = fixed
                                logger.info("[tutor] 已自动补全第 %d 行 run_time=1)", syn_err.lineno)
                                continue
                            except SyntaxError:
                                pass
                logger.info("[tutor] 脚本语法错误，尝试 LLM 修复 (第 %d 次)… %s", attempt + 1, err_text[:200])
                current_code = manim_render.fix_tutor_script_with_llm(current_code, err_text)
                if not (current_code and current_code.strip()):
                    raise RuntimeError("LLM 未返回有效脚本代码")
                if "```python" in current_code:
                    current_code = re.sub(r"^```python\s*\n?", "", current_code)
                if "```" in current_code:
                    current_code = re.sub(r"\n?```\s*$", "", current_code)
                current_code = current_code.strip()
                continue
            written = manim_render.render_manim_script(
                current_code,
                output_mp4,
                scene_class=scene_class or settings.manim_scene_class,
                quality=settings.manim_quality,
                audio_dir=Path(audio_dir),
                audio_info_dict=audio_info.model_dump(),
            )
            return written
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
    raise RuntimeError(
        f"Manim 渲染未产生输出，最后错误: {last_error or '未知'}"
    )
