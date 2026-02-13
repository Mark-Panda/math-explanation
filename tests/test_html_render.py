"""HTML 动画渲染单测：校验函数与自愈循环。"""
import pytest

from asset_generation.html_render import validate_html_animation


def test_validate_html_animation_valid():
    """合法的 HTML 片段应通过校验。"""
    html = """
    <div id="animation-container"></div>
    <style>.box { color: red; }</style>
    <script>
    window.stepAnimations = [
        { duration: STEP_PLACEHOLDER, animate: function(c) { c.innerHTML = 'hello'; } }
    ];
    </script>
    """
    errors = validate_html_animation(html)
    assert errors == []


def test_validate_html_animation_missing_step_animations():
    """缺少 stepAnimations 应报错。"""
    html = '<div id="animation-container"></div><script>var x = 1;</script>'
    errors = validate_html_animation(html)
    assert any("stepAnimations" in e for e in errors)


def test_validate_html_animation_missing_container():
    """缺少 animation-container 应报错。"""
    html = '<div id="canvas"></div><script>window.stepAnimations = [];</script>'
    errors = validate_html_animation(html)
    assert any("animation-container" in e for e in errors)
