"""
从项目内 Remotion skill（.cursor/skills/remotion）加载规则文本，作为 LLM 生成 Remotion 代码时的上下文。
"""
from pathlib import Path

# 项目根目录（script_generation 的上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_RULES_DIR = PROJECT_ROOT / ".cursor" / "skills" / "remotion" / "rules"

# 生成 Remotion 数学讲解 Composition 时需要的规则（按顺序拼接）
RELEVANT_RULES = [
    "compositions.md",
    "sequencing.md",
    "audio.md",
    "animations.md",
    "timing.md",
]


def load_remotion_skill_context() -> str:
    """
    加载 Remotion skill 中与 composition/sequencing/audio/animations 相关的规则，
    拼成一段可放入 LLM prompt 的「Remotion 最佳实践」上下文。
    若某文件不存在则跳过，不抛错。
    """
    parts = []
    for name in RELEVANT_RULES:
        path = SKILL_RULES_DIR / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
                # 去掉 YAML frontmatter（--- ... ---）
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end != -1:
                        text = text[end + 3 :].lstrip()
                parts.append(f"## {name}\n\n{text.strip()}")
            except Exception:
                continue
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)
