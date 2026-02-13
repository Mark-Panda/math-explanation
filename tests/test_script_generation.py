"""脚本生成单测：steps 校验；成功生成需 mock 或真实 LLM。"""
import pytest

from problem_analysis.schemas import StepItem
from script_generation.generator import generate_animation_html_and_prompts


def test_generate_animation_html_and_prompts_empty_steps_raises():
    with pytest.raises(ValueError, match="不能为空"):
        generate_animation_html_and_prompts([])


def test_generate_animation_html_and_prompts_invalid_step_raises():
    bad = [StepItem(step_id=1, description="", math_formula="", visual_focus="", voiceover_text="")]
    with pytest.raises(ValueError, match="description 或 voiceover_text"):
        generate_animation_html_and_prompts(bad)


def test_generate_animation_html_and_prompts_valid():
    """完整流程测试（需要 LLM API Key）。"""
    pytest.importorskip("langchain_openai")
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    steps = [
        StepItem(
            step_id=1,
            description="设 x^2=1",
            math_formula="$x^2=1$",
            visual_focus="方程",
            voiceover_text="我们设 x 平方等于 1。",
        ),
    ]
    out = generate_animation_html_and_prompts(steps)
    assert "stepAnimations" in out.animation_html
    assert "STEP_PLACEHOLDER" in out.animation_html
    assert len(out.image_prompts) >= 1
    assert isinstance(out.animation_html, str) and len(out.animation_html) > 0
