"""TTS 生成语音并返回时长（秒）。同一批步骤固定使用同一音色，避免出现两种人声。"""
import asyncio
import logging
import re
from pathlib import Path

from config import get_settings

logger = logging.getLogger(__name__)


def _latex_to_speech(text: str) -> str:
    """
    将旁白中的 LaTeX 公式（如 $y=kx$、$M(-2,-1)$）转为 TTS 可读的中文语音文本，
    避免读成「美元符号」「反斜杠」等。
    """
    if not text or "$" not in text:
        return text

    # 先替换常见 LaTeX 命令为中文读法（在整段上做，便于 \frac{a}{b} 等）
    repl = text

    # \frac{num}{den} → den分之num（简单实现：找 \frac{...}{...}）
    def _frac_repl(m: re.Match) -> str:
        inner = m.group(0)
        i = 5  # len(r'\frac')
        if i < len(inner) and inner[i] == "{":
            depth, start = 1, i + 1
            j = start
            while j < len(inner) and depth:
                if inner[j] == "{":
                    depth += 1
                elif inner[j] == "}":
                    depth -= 1
                j += 1
            num = inner[start : j - 1].strip()
            if j < len(inner) and inner[j] == "{":
                depth, start2 = 1, j + 1
                k = start2
                while k < len(inner) and depth:
                    if inner[k] == "{":
                        depth += 1
                    elif inner[k] == "}":
                        depth -= 1
                    k += 1
                den = inner[start2 : k - 1].strip()
                num_s = _latex_formula_to_speech(num)
                den_s = _latex_formula_to_speech(den)
                if den_s == "2" and num_s == "1":
                    return "二分之一"
                if den_s == "4" and num_s == "1":
                    return "四分之一"
                return f"{den_s}分之{num_s}"
        return _latex_formula_to_speech(inner)

    repl = re.sub(r"\\frac\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", _frac_repl, repl)

    # 再处理 $...$ 和 $$...$$ 整段
    def _replace_formula(m: re.Match) -> str:
        content = m.group(1)
        return _latex_formula_to_speech(content)

    repl = re.sub(r"\$\$([^$]+)\$\$", _replace_formula, repl)
    repl = re.sub(r"\$([^$]+)\$", _replace_formula, repl)

    return repl


def _latex_formula_to_speech(latex: str) -> str:
    """单段公式 LaTeX 转中文读法，供 TTS 朗读。"""
    s = latex.strip()
    if not s:
        return ""

    # 先处理 \frac{num}{den}（必须在「去掉反斜杠」之前，且 num/den 可含简单内容）
    def _frac_inline(m: re.Match) -> str:
        return _frac_to_speech(m.group(1).strip(), m.group(2).strip())
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", _frac_inline, s)

    # 符号 → 中文
    s = re.sub(r"\\cdot\s*", "乘", s)
    s = re.sub(r"\\times\s*", "乘", s)
    s = re.sub(r"\\pm\s*", "正负", s)
    s = re.sub(r"\\triangle\s*", "三角形", s)
    s = re.sub(r"\\perp\s*", "垂直", s)
    s = re.sub(r"\\geq\s*", "大于等于", s)
    s = re.sub(r"\\leq\s*", "小于等于", s)
    s = re.sub(r"\\neq\s*", "不等于", s)
    s = re.sub(r"\\approx\s*", "约等于", s)
    s = re.sub(r"\\text\{\s*min\s*\}\s*", "最小值", s, flags=re.I)

    # \sqrt{...} → 根号...
    def _sqrt_repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        return "根号" + _latex_formula_to_speech(inner)
    s = re.sub(r"\\sqrt\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", _sqrt_repl, s)

    # 数字坐标 (-2,-1) (2,1) → 负二 负一 / 二 一
    s = re.sub(
        r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        lambda m: _num_pair_to_speech(m.group(1), m.group(2)),
        s,
    )
    # 字母+坐标 M(-2,-1) → M 点 负二 负一（上一步已把 (-2,-1) 换成 负二 负一，这里处理 M负二 负一 → M 点 负二 负一）
    s = re.sub(r"([A-Za-z])\s*(负?[一二三四五六七八九十零\d]+\s+负?[一二三四五六七八九十零\d]+)", r"\1 点 \2", s)
    # 更一般的 (x,y) 非纯数字
    def _coord_repl(m: re.Match) -> str:
        left, right = m.group(1).strip(), m.group(2).strip()
        return _latex_formula_to_speech(left) + " " + _latex_formula_to_speech(right)
    s = re.sub(r"\(\s*([^(),]+)\s*,\s*([^()]+)\s*\)", _coord_repl, s)

    # 幂 x^2 → x的平方, (-1)^2 → 负一的平方
    s = re.sub(r"\^2\b", "的平方", s)
    s = re.sub(r"\^3\b", "的立方", s)
    s = re.sub(r"\^\{2\}\s*", "的平方", s)
    s = re.sub(r"\^\{3\}\s*", "的立方", s)
    s = re.sub(r"\^\{(-?\d+)\}\s*", lambda m: "的" + _digit_to_speech(m.group(1)) + "次方", s)

    # 负数 -1 -2 → 负一 负二（仅对单独数字）
    s = re.sub(r"(?<![.\w])(-\d+)(?![.\w])", _negative_num_to_speech, s)

    # 去掉剩余反斜杠（未识别的命令）
    s = re.sub(r"\\[a-zA-Z]+\s*", " ", s)
    s = re.sub(r"\\", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _frac_to_speech(num: str, den: str) -> str:
    num_s = _latex_formula_to_speech(num.strip())
    den_s = _latex_formula_to_speech(den.strip())
    if den_s == "2" and num_s == "1":
        return "二分之一"
    if den_s == "4" and num_s == "1":
        return "四分之一"
    return f"{den_s}分之{num_s}"


def _negative_num_to_speech(m: re.Match) -> str:
    num = m.group(1)
    n = num.lstrip("-")
    if n == "1":
        return "负一"
    if n == "2":
        return "负二"
    if n == "5":
        return "负五"
    if n.isdigit():
        return "负" + _digit_to_speech(n)
    return num


_DIGIT_CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]


def _digit_to_speech(d: str) -> str:
    """整数中文读法（用于坐标、指数等）。"""
    try:
        n = int(d)
        if n < 0:
            return "负" + _digit_to_speech(str(-n))
        if n < 10:
            return _DIGIT_CN[n]
        if n < 20:
            return "十" + (_DIGIT_CN[n - 10] if n != 10 else "")
        if n < 100:
            a, b = divmod(n, 10)
            return _DIGIT_CN[a] + "十" + (_DIGIT_CN[b] if b else "")
        return str(n)
    except ValueError:
        return d


def _num_pair_to_speech(x: str, y: str) -> str:
    """坐标 (x,y) 数字转读法。"""
    try:
        xn, yn = int(float(x)), int(float(y))
        x_s = "负" + _digit_to_speech(str(-xn)) if xn < 0 else _digit_to_speech(str(xn))
        y_s = "负" + _digit_to_speech(str(-yn)) if yn < 0 else _digit_to_speech(str(yn))
        return x_s + " " + y_s
    except ValueError:
        return x + " " + y


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
    speech_text = _latex_to_speech(text.strip())
    communicate = edge_tts.Communicate(speech_text, voice)
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
