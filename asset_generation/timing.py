"""将各步时长注入网页动画代码中的 STEP_PLACEHOLDER。"""
import re

from config import get_settings


def inject_timing_into_html(
    original_html: str,
    durations: list[float],
    default_wait: float | None = None,
) -> str:
    """
    按出现顺序将 STEP_PLACEHOLDER 替换为实际的时长数值（秒）。
    若 durations 不足则用 default_wait（未传则用配置的 default_wait_seconds）。
    """
    if default_wait is None:
        default_wait = get_settings().default_wait_seconds

    step_idx = 0
    result = original_html

    def _replace_placeholder(match: re.Match) -> str:
        nonlocal step_idx
        if step_idx < len(durations):
            val = durations[step_idx]
        else:
            val = default_wait
        step_idx += 1
        return str(val)

    # 替换所有 STEP_PLACEHOLDER（可能被引号包裹，也可能不被包裹）
    # 匹配模式：可选引号 + STEP_PLACEHOLDER + 可选引号
    result = re.sub(
        r"""(['"]?)STEP_PLACEHOLDER\1""",
        _replace_placeholder,
        result,
    )

    return result
