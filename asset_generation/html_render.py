"""网页动画渲染：将 LLM 生成的动画 HTML 片段 + TTS 音频组装为自包含的 HTML 文件。支持自愈（LLM 修复语法错误）。"""
import base64
import logging
import re
from pathlib import Path

from config import get_settings
from llm_runner import invoke_plain

logger = logging.getLogger(__name__)

# 外层 HTML 模板：包裹 LLM 生成的动画片段，内嵌音频，提供播放控制器
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>数学讲解动画</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #1a1a2e;
      color: #e6e6e6;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      padding: 2rem 1rem;
    }}
    h1 {{
      font-size: 1.5rem;
      font-weight: 600;
      margin-bottom: 1.5rem;
      color: #e6e6e6;
    }}
    #animation-wrapper {{
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
      overflow: hidden;
      margin-bottom: 1.5rem;
    }}
    #controls {{
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.75rem 1.5rem;
      background: #16213e;
      border-radius: 8px;
      margin-bottom: 1rem;
    }}
    #controls button {{
      padding: 0.5rem 1.25rem;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 500;
      transition: all 0.2s;
    }}
    #btn-play {{
      background: #58a6ff;
      color: #fff;
    }}
    #btn-play:hover {{ background: #79b8ff; }}
    #btn-play:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    #btn-reset {{
      background: transparent;
      color: #8b949e;
      border: 1px solid #30363d;
    }}
    #btn-reset:hover {{ color: #e6e6e6; border-color: #8b949e; }}
    #step-info {{
      color: #8b949e;
      font-size: 0.85rem;
    }}
    #progress-bar {{
      width: 100%;
      height: 4px;
      background: #30363d;
      border-radius: 2px;
      overflow: hidden;
      margin-bottom: 1rem;
    }}
    #progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, #58a6ff, #79b8ff);
      border-radius: 2px;
      transition: width 0.3s ease-out;
      width: 0%;
    }}
  </style>
</head>
<body>
  <h1>数学讲解动画</h1>
  <div id="progress-bar"><div id="progress-fill"></div></div>
  <div id="controls">
    <button id="btn-play">▶ 播放</button>
    <button id="btn-reset">重置</button>
    <span id="step-info">共 <span id="total-steps">0</span> 步</span>
  </div>
  <div id="animation-wrapper">
    {animation_html}
  </div>

  <!-- 内嵌音频 -->
  {audio_elements}

  <script>
  (function() {{
    var steps = window.stepAnimations || [];
    var totalSteps = steps.length;
    var currentStep = 0;
    var playing = false;
    var playBtn = document.getElementById('btn-play');
    var resetBtn = document.getElementById('btn-reset');
    var stepInfo = document.getElementById('step-info');
    var totalStepsEl = document.getElementById('total-steps');
    var progressFill = document.getElementById('progress-fill');
    var container = document.getElementById('animation-container');

    totalStepsEl.textContent = totalSteps;

    function updateUI() {{
      if (currentStep >= totalSteps) {{
        stepInfo.innerHTML = '已完成 ' + totalSteps + ' 步';
        playBtn.textContent = '▶ 播放';
        playBtn.disabled = false;
        playing = false;
        progressFill.style.width = '100%';
      }} else {{
        stepInfo.innerHTML = '第 ' + (currentStep + 1) + ' / ' + totalSteps + ' 步';
        progressFill.style.width = ((currentStep / totalSteps) * 100) + '%';
      }}
    }}

    function playStep(index) {{
      if (index >= totalSteps) {{
        currentStep = totalSteps;
        updateUI();
        return;
      }}
      currentStep = index;
      playing = true;
      playBtn.textContent = '⏸ 播放中…';
      playBtn.disabled = true;
      updateUI();

      var step = steps[index];
      var dur = (typeof step.duration === 'number' && step.duration > 0) ? step.duration : 3;

      // 播放该步骤的音频
      var audio = document.getElementById('audio-step-' + index);
      if (audio) {{
        audio.currentTime = 0;
        audio.play().catch(function() {{}});
      }}

      // 执行动画
      try {{
        step.animate(container);
      }} catch(e) {{
        console.error('步骤 ' + (index + 1) + ' 动画执行出错:', e);
      }}

      // 等待 duration 后播放下一步
      setTimeout(function() {{
        if (playing) {{
          playStep(index + 1);
        }}
      }}, dur * 1000);
    }}

    playBtn.addEventListener('click', function() {{
      if (currentStep >= totalSteps) {{
        // 重头播放
        currentStep = 0;
        if (container) container.innerHTML = '';
      }}
      playStep(currentStep);
    }});

    resetBtn.addEventListener('click', function() {{
      playing = false;
      currentStep = 0;
      if (container) container.innerHTML = '';
      // 暂停所有音频
      for (var i = 0; i < totalSteps; i++) {{
        var audio = document.getElementById('audio-step-' + i);
        if (audio) {{
          audio.pause();
          audio.currentTime = 0;
        }}
      }}
      playBtn.textContent = '▶ 播放';
      playBtn.disabled = false;
      updateUI();
    }});

    updateUI();
  }})();
  </script>
</body>
</html>"""


def _strip_markdown_code_block(code: str) -> str:
    """若代码被 markdown 代码块包裹，去掉首尾的围栏行。"""
    s = code.strip()
    lines = s.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _audio_files_to_elements(audio_dir: Path, prefix: str = "step") -> str:
    """将音频文件转为 base64 内嵌的 <audio> 元素。"""
    elements = []
    audio_files = sorted(audio_dir.glob(f"{prefix}_*.mp3"), key=lambda p: int(p.stem.split("_")[1]))
    for i, audio_file in enumerate(audio_files):
        audio_bytes = audio_file.read_bytes()
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        elements.append(
            f'  <audio id="audio-step-{i}" preload="auto" src="data:audio/mpeg;base64,{b64}"></audio>'
        )
    return "\n".join(elements)


def render_html_animation(
    animation_html: str,
    audio_dir: Path,
    output_file: str | Path,
    *,
    audio_prefix: str = "step",
) -> None:
    """
    将 LLM 生成的动画 HTML 片段与 TTS 音频文件组装为自包含的 HTML 文件。
    音频以 base64 内嵌，无需外部文件依赖。
    """
    out_path = Path(output_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    clean_html = _strip_markdown_code_block(animation_html)
    audio_elements = _audio_files_to_elements(audio_dir, prefix=audio_prefix)

    final_html = HTML_TEMPLATE.format(
        animation_html=clean_html,
        audio_elements=audio_elements,
    )
    out_path.write_text(final_html, encoding="utf-8")
    logger.info("[html_render] HTML 动画文件已生成: %s", out_path)


def validate_html_animation(html_code: str) -> list[str]:
    """
    基础校验 HTML 动画代码，返回错误列表。
    空列表表示通过校验。
    """
    errors = []
    if "stepAnimations" not in html_code:
        errors.append("缺少 stepAnimations 数组定义")
    if "animation-container" not in html_code:
        errors.append("缺少 id='animation-container' 的容器元素")
    # 检查是否有明显的语法问题
    if html_code.count("<script") != html_code.count("</script"):
        errors.append("<script> 标签未正确闭合")
    if html_code.count("<style") != html_code.count("</style"):
        errors.append("<style> 标签未正确闭合")
    return errors


def fix_html_with_llm(bad_html: str, error_msg: str) -> str:
    """通过 LLM 修复 HTML 动画代码中的错误。"""
    prompt = f"""这段网页动画 HTML 代码有问题，请修复后只返回完整可运行的 HTML 片段代码，不要解释。

错误信息:
{error_msg}

代码:
```html
{bad_html}
```

请直接输出修复后的完整代码（保留 animation-container、stepAnimations 和 STEP_PLACEHOLDER 占位）。
注意：
- 输出的是 HTML 片段，不要包含 <!DOCTYPE>、<html>、<head>、<body> 标签
- 必须包含 window.stepAnimations 数组定义
- duration 使用 STEP_PLACEHOLDER 占位
- 不要使用任何外部库（MathJax、KaTeX、GSAP 等）"""
    return invoke_plain(prompt)


def render_html_with_self_heal(
    animation_html: str,
    audio_dir: Path,
    output_file: str | Path,
    *,
    audio_prefix: str = "step",
) -> None:
    """
    自愈循环：校验动画代码，失败则用 LLM 修复后重试，最多 N 次。
    """
    settings = get_settings()
    max_attempts = settings.html_self_heal_max_attempts
    current_html = animation_html
    last_error: str | None = None

    for attempt in range(max_attempts):
        errors = validate_html_animation(current_html)
        if not errors:
            render_html_animation(current_html, audio_dir, output_file, audio_prefix=audio_prefix)
            return
        last_error = "; ".join(errors)
        logger.warning("[html_render] 动画代码校验失败 (attempt %d/%d): %s", attempt + 1, max_attempts, last_error)
        if attempt == max_attempts - 1:
            # 最后一次尝试仍失败，但仍尝试渲染（可能只是校验过严）
            logger.warning("[html_render] 达到最大重试次数，尝试直接渲染")
            render_html_animation(current_html, audio_dir, output_file, audio_prefix=audio_prefix)
            return
        current_html = fix_html_with_llm(current_html, last_error)
        current_html = _strip_markdown_code_block(current_html)
