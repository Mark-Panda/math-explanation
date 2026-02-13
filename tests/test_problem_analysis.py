"""题目分析单测：空输入校验；合法输入需 mock LLM。"""
import pytest

from problem_analysis.analyzer import analyze_problem


def test_analyze_problem_empty_string_raises():
    """题目文本为空时在调用 LLM 前校验并抛出明确错误。"""
    with pytest.raises(ValueError, match="不能为空"):
        analyze_problem("")
    with pytest.raises(ValueError, match="不能为空"):
        analyze_problem("   \n\t  ")


def test_analyze_problem_valid_input_calls_llm():
    """合法输入时调用 LLM 并返回 steps（需有 OPENAI_API_KEY 或 mock）。"""
    # 无 mock 时依赖真实 API；仅做冒烟测试时可跳过
    pytest.importorskip("langchain_openai")
    # 若未配置 key 则跳过
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    steps = analyze_problem("求方程 x^2 = 1 的解。")
    assert len(steps) >= 1
    for s in steps:
        assert hasattr(s, "step_id") and isinstance(s.step_id, int)
        assert hasattr(s, "description") and isinstance(s.description, str)
        assert hasattr(s, "math_formula") and isinstance(s.math_formula, str)
        assert hasattr(s, "visual_focus") and isinstance(s.visual_focus, str)
        assert hasattr(s, "voiceover_text") and isinstance(s.voiceover_text, str)
