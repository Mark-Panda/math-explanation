该方案旨在结合大语言模型的逻辑推理能力、Manim的精确数学渲染能力、以及Diffusion模型的视觉生成能力，打造一个既严谨又生动的数学讲解系统。

---

### 🏗️ 1. 系统架构设计

我们将系统分为四个主要流水线阶段：

```mermaid
graph TD
    Input[用户输入: 数学题目] --> Core[LLM 核心控制器]
  
    Core --> Step1[阶段一: 逻辑推理与结构化]
    Core --> Step2[阶段二: 多模态脚本生成]
    Core --> Step3[阶段三: 素材生成代码]
  
    Step3 --> A[Manim 代码生成器]
    Step3 --> B[Stable Diffusion 提示词生成器]
    Step3 --> C[TTS 语音生成器]
  
    A --> D[渲染引擎: Manim (精确数学动画)]
    B --> E[绘图引擎: SD (背景/插图)]
    C --> F[语音引擎: Azure/OpenAI TTS]
  
    D --> G[合成引擎: FFmpeg]
    E --> G
    F --> G
  
    G --> Output[最终讲解视频]
```

---

### 🛠️ 2. 技术栈选型

| 模块               | 推荐技术                                 | 理由                                                            |
| :----------------- | :--------------------------------------- | :-------------------------------------------------------------- |
| **核心大脑 (LLM)** | **GPT-4o** 或 **Claude 3.5 Sonnet**      | 具备极强的代码生成能力和逻辑推理能力，能写出可运行的Manim代码。 |
| **数学解析**       | **Python SymPy**                         | 用于辅助验证数学推导的准确性（可选）。                          |
| **精确动画**       | **Manim** (Python库)                     | 目前最专业的数学动画引擎，由3Blue1Brown开发。                   |
| **视觉生成**       | **Stable Diffusion XL** + **ControlNet** | 生成高质量的背景、插图或概念图。                                |
| **语音合成**       | **Azure TTS** 或 **OpenAI TTS**          | 自然度极高，支持多种情感和语速。                                |
| **视频合成**       | **FFmpeg**                               | 行业标准，用于将视频、音频、图片合成。                          |
| **开发语言**       | **Python 3.10+**                         | Manim和AI生态的通用语言。                                       |

---

### 📝 3. 详细实现步骤与代码逻辑

#### **阶段一：题目理解与逻辑拆解**
LLM 首先需要将题目转化为结构化的解题步骤，不仅仅是给出答案，而是分步推导。

*   **Prompt 策略**：要求输出 JSON 格式，包含步骤描述、对应的数学公式、以及该步骤的视觉重点。

```python
import json
from openai import OpenAI

client = OpenAI()

def analyze_problem(problem_text):
    prompt = f"""
    你是一个数学专家和动画脚本设计师。请分析以下数学题目，并生成解题步骤。
  
    题目: {problem_text}
  
    请按照以下JSON格式输出：
    {{
        "steps": [
            {{
                "step_id": 1,
                "description": "第一步的文字描述",
                "math_formula": "LaTeX格式的公式，如 $x^2 + y^2 = r^2$",
                "visual_focus": "需要突出的视觉元素，如'高亮圆的方程'",
                "voiceover_text": "这一步的旁白文案"
            }}
        ]
    }}
    """
  
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
  
    return json.loads(response.choices[0].message.content)
```

#### **阶段二：多模态脚本生成**
将逻辑步骤转化为具体的指令。

*   **Prompt 策略**：LLM 不仅生成 Manim 代码，还生成用于 Stable Diffusion 的图像提示词。关键是**时间同步**。

```python
def generate_manim_code_and_prompts(steps_data):
    prompt = f"""
    基于以下解题步骤，生成两部分内容：
    1. Manim Python 代码：用于绘制数学图形和动画。
    2. 图像提示词：用于为该步骤生成概念性背景图（风格：数学教科书风格，极简，白色背景）。
  
    解题步骤数据: {json.dumps(steps_data)}
  
    要求：
    - Manim代码必须包含一个 `SolutionScene` 类。
    - 每个步骤对应一个 construct 方法中的子动画。
    - 使用 `self.wait()` 控制时间，默认每个步骤等待2秒，我们后续会根据语音调整。
    - 输出JSON格式，包含 'manim_code' 和 'image_prompts' 列表。
    """
  
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
  
    return json.loads(response.choices[0].message.content)
```

#### **阶段三：素材生成与渲染 (Worker层)**

这一步是系统最耗时的地方，需要并发处理。

##### A. 语音生成与时长计算
为了保证“口型”和动画对得上，必须先获取语音的精确时长。

```python
import edge_tts # 或使用 openai, azure
import asyncio

async def generate_audio_with_duration(text, filename):
    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
    await communicate.save(filename)
  
    # 获取音频时长 (需要使用 pydub 或类似库)
    from pydub import AudioSegment
    audio = AudioSegment.from_file(filename)
    return len(audio) / 1000.0  # 返回秒数
```

##### B. 动态调整 Manim 代码
将 TTS 返回的时长注入到 Manim 代码中，替换掉原来的 `self.wait()`。

```python
def inject_timing_into_code(original_code, durations):
    # 简单的字符串替换逻辑，实际生产中需要 AST 解析
    lines = original_code.split('\n')
    new_lines = []
    step_idx = 0
  
    for line in lines:
        if "self.wait()" in line and step_idx < len(durations):
            # 替换 wait 时间
            new_lines.append(f"        self.wait({durations[step_idx]})")
            step_idx += 1
        else:
            new_lines.append(line)
    return "\n".join(new_lines)
```

##### C. 渲染 Manim
```python
from manim import *

# 这里需要在一个独立的进程或沙箱中运行，以防代码崩溃阻塞主程序
def render_manim_video(code_string, output_file):
    # 将代码写入临时文件
    with open("temp_scene.py", "w", encoding='utf-8') as f:
        f.write(code_string)
  
    # 调用命令行渲染
    import os
    os.system(f"manim temp_scene.py SolutionScene -pql -o {output_file}")
```

##### D. 生成辅助图像 (可选 - 用于背景)
```python
def generate_concept_image(prompt, filename):
    # 调用 Stable Diffusion API
    # 这里省略 API 调用细节，假设使用 requests.post 调用 Automatic1111
    pass 
```

#### **阶段四：最终合成**
使用 FFmpeg 将语音、背景图、Manim动画合成。

```python
import subprocess

def compose_video(manim_video, audio_file, output_path):
    command = [
        'ffmpeg',
        '-y', # 覆盖输出文件
        '-i', manim_video,
        '-i', audio_file,
        '-c:v', 'copy', # 直接复制视频流，不重新编码
        '-c:a', 'aac',
        '-shortest', # 以最短的流为准
        output_path
    ]
    subprocess.run(command, check=True)
```

---

### 🧠 4. 核心难点：LLM 生成代码的“自愈”机制

LLM 第一次生成的 Manim 代码大概率会有语法错误或逻辑错误。你需要建立一个**反馈循环**：

1.  **执行**：运行生成的 Manim 代码。
2.  **捕获**：捕获 Python Traceback 报错信息。
3.  **反思**：将报错信息发回给 LLM。
    *   *Prompt*: "你生成的代码运行出错了：[Error Info]。请修复这段代码。"
4.  **重试**：重新生成代码并执行。

**伪代码实现：**

```python
max_attempts = 3
current_code = initial_manim_code

for attempt in range(max_attempts):
    try:
        render_manim_video(current_code, "test.mp4")
        print("渲染成功！")
        break
    except Exception as e:
        print(f"尝试 {attempt + 1} 失败: {e}")
        if attempt == max_attempts - 1:
            raise Exception("AI无法生成正确的代码")
      
        # 发送给LLM修复
        current_code = fix_code_with_llm(current_code, str(e))

def fix_code_with_llm(bad_code, error_msg):
    prompt = f"""
    这段Manim代码运行报错：
    代码: {bad_code}
    错误: {error_msg}
  
    请提供修复后的完整代码。不要解释，直接给代码。
    """
    # ... call LLM ...
    return fixed_code
```

---

### 🚀 5. 部署与运行流程图

你可以构建一个简单的 FastAPI 后端来串联这些步骤。

```python
from fastapi import FastAPI, BackgroundTasks

app = FastAPI()

@app.post("/generate_video")
async def create_video(problem: str):
    # 1. 逻辑分析
    steps = analyze_problem(problem)
  
    # 2. 生成初始脚本和代码
    script_data = generate_manim_code_and_prompts(steps)
  
    # 3. 并发生成音频和准备代码
    durations = []
    for step in steps:
        dur = await generate_audio_with_duration(step['voiceover_text'], f"audio_{step['step_id']}.mp3")
        durations.append(dur)
      
    # 4. 注入时间并修复代码
    final_code = inject_timing_into_code(script_data['manim_code'], durations)
    # (此处调用上面的自愈逻辑函数 ensure_code_works(final_code))
  
    # 5. 渲染
    render_manim_video(final_code, "math_anim.mp4")
  
    # 6. 合成
    # (合并所有音频片段 -> 合并所有视频片段 -> 简单起见，这里假设生成了一段长视频和一段长音频)
    compose_video("math_anim.mp4", "full_audio.mp3", "final_result.mp4")
  
    return {"status": "success", "url": "/downloads/final_result.mp4"}
```

---

### 💡 总结与优化建议

1.  **模板库**：不要让 LLM 每次都从零写 `Scene` 的结构。预设几种 Manim 模板（如几何证明模板、函数图像模板），让 LLM 只填充关键坐标和公式，成功率会提高 80%。
2.  **分步渲染**：对于复杂的题目，将每个步骤单独渲染成短视频，最后用 FFmpeg 拼接，这样容错率更高（某个步骤崩了不用重算全部）。
3.  **成本控制**：Manim 渲染非常耗 CPU，建议使用 GPU 加速（虽然 Manim 主要是 CPU 渲染，但有些后端支持）或者集群渲染。语音合成尽量用速度快且免费的模型（如 Edge-TTS）。
4.  **视觉一致性**：如果在 Manim 中使用 AI 生成的图片作为背景，确保 SD 的 Prompt 中包含 "white background, minimal style" 以免喧宾夺主。

这套方案是目前实现高质量、可定制化数学讲解视频的最佳实践路径。