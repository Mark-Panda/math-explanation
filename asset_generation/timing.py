"""将各步时长注入 Manim 代码中的 self.wait()。"""
import re

from config import get_settings


def inject_timing_into_code(
    original_code: str,
    durations: list[float],
    default_wait: float | None = None,
) -> str:
    """
    按出现顺序将 self.wait() 替换为 self.wait(duration)。
    若 durations 不足则用 default_wait（未传则用配置的 default_wait_seconds）。
    """
    if default_wait is None:
        default_wait = get_settings().default_wait_seconds
    lines = original_code.split("\n")
    new_lines: list[str] = []
    step_idx = 0
    for line in lines:
        if "self.wait()" in line and step_idx < len(durations):
            # 只替换第一个 self.wait() 为带参数的
            new_line = line.replace("self.wait()", f"self.wait({durations[step_idx]})", 1)
            new_lines.append(new_line)
            step_idx += 1
        elif "self.wait()" in line:
            new_line = line.replace("self.wait()", f"self.wait({default_wait})", 1)
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines)
