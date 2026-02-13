"""Manim 渲染与自愈：mock 子进程与 LLM，测试自愈循环。"""
import pytest

from asset_generation.manim_render import fix_code_with_llm, render_manim_video_with_self_heal


def test_fix_code_with_llm_returns_string():
    """fix_code_with_llm 返回字符串（需 LLM，无 key 时跳过）。"""
    pytest.importorskip("langchain_openai")
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    out = fix_code_with_llm("def x(): pass", "NameError: name 'y' is not defined")
    assert isinstance(out, str) and len(out) > 0


def test_render_manim_video_with_self_heal_raises_on_invalid_code():
    """无效代码在达到最大重试后抛出 RuntimeError（需 Manim 与 LLM，否则跳过）。"""
    import shutil
    if not shutil.which("manim"):
        pytest.skip("manim 未安装")
    pytest.importorskip("langchain_openai")
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    invalid_code = "print(1/0)"  # 无 SolutionScene，manim 会报错
    with pytest.raises((RuntimeError, Exception)):
        render_manim_video_with_self_heal(invalid_code, "/tmp/test_manim_out.mp4")
