# 数学讲解流水线

从数学题目自动生成带旁白的讲解视频（Manim MP4）。

> **说明文档**：想了解「项目做什么、为什么这样设计、这样设计的好处」可看 [docs/项目说明文档.md](docs/项目说明文档.md)（通俗版）。

**流水线**：按 [Tutor 技能](.cursor/skills/tutor/SKILL.md) 逻辑：数学分析(tutor) → HTML 可视化 → 分镜脚本 → TTS → 验证 → 脚手架 → Manim 实现 → 检查与渲染，得到 MP4 视频。

提供 Web 界面与 API：输入题目或上传题目图片、触发生成、轮询状态、页面内播放或下载。

---

## 依赖安装

- Python 3.10+
- 安装 [uv](https://docs.astral.sh/uv/)（`curl -LsSf https://astral.sh/uv/install.sh | sh` 或 `pip install uv`）
- **系统安装 [FFmpeg](https://ffmpeg.org/)**（需包含 `ffprobe`，用于 TTS 音频时长探测）。未安装时 TTS 会使用默认时长。
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: 从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并将 `bin` 加入 PATH

```bash
uv sync
```

---

## 环境变量说明

复制 `.env copy.example` 为 `.env` 后按需修改（勿将 `.env` 提交到版本库），或直接设置环境变量。

**大模型（LLM）：**

| 变量                  | 说明                                               | 默认/示例        |
| --------------------- | -------------------------------------------------- | ---------------- |
| `OPENAI_API_KEY`      | **必填**，OpenAI 或兼容接口的 API Key              | `sk-...`         |
| `OPENAI_BASE_URL`     | 可选，自定义 API 基础 URL（代理、Azure、国内中转） |                  |
| `LLM_MODEL`           | 模型名称（纯文本任务：题目分析、脚本生成、自愈）   | `gpt-4o`         |
| `LLM_TEMPERATURE`     | 生成温度（0~2，建议 0.1~0.3）                      | `0.2`            |
| `LLM_MAX_TOKENS`      | 单次请求最大 token 数                              | 不设则用模型默认 |
| `LLM_REQUEST_TIMEOUT` | 单次请求超时（秒）                                 | `120`            |
| `LLM_SCRIPT_TIMEOUT`  | 脚本生成阶段超时（秒，建议 ≥300）                  | `300`            |

**视觉模型（多模态，用于图片识别、带图分析）：** 未配置时自动回退到上方 LLM 配置。

| 变量                    | 说明                     | 默认     |
| ----------------------- | ------------------------ | -------- |
| `VISION_API_KEY`        | 视觉模型 API Key         | 用 LLM   |
| `VISION_BASE_URL`       | 视觉模型 API 基础 URL    | 用 LLM   |
| `VISION_MODEL`          | 视觉模型名称             | 用 LLM   |
| `VISION_TEMPERATURE`    | 视觉模型温度             | 用 LLM   |
| `VISION_REQUEST_TIMEOUT`| 视觉模型超时（秒）       | 用 LLM   |

**其他（通用）：**

| 变量                         | 说明                               | 默认                   |
| ---------------------------- | ---------------------------------- | ---------------------- |
| `TTS_VOICE`                  | Edge-TTS 音色                      | `zh-CN-XiaoxiaoNeural` |
| `DEFAULT_WAIT_SECONDS`       | 时长不足时默认 step 时长（秒）     | `2.0`                  |

**Manim 视频流水线：**

| 变量                         | 说明                               | 默认        |
| ---------------------------- | ---------------------------------- | ----------- |
| `MANIM_COMMAND`              | Manim 可执行命令或绝对路径         | `manim`     |
| `MANIM_SCENE_CLASS`          | 要渲染的场景类名                   | `MathScene` |
| `MANIM_QUALITY`              | 渲染质量：`ql`/`qm`/`qh`/`qk`      | `qh`        |
| `MANIM_SELF_HEAL_MAX_ATTEMPTS` | 渲染失败时 LLM 自愈最大重试次数   | `3`         |

---

## 各阶段 AI Prompt 说明

以下为流水线中所有调用 LLM 的步骤、各自用途及在代码中的位置。

| 阶段 | 用途 | Prompt 名称 / 说明 | 位置（文件: 行/函数） |
|------|------|--------------------|------------------------|
| **图片识别**（仅上传图片时） | 从题目图片中识别文字、公式与图形描述 | `VISION_PROMPT` | `problem_analysis/image_to_text.py`：第 6 行常量，在 `extract_problem_text_from_image()` 中作为多模态请求的文本部分 |
| **公式交叉验证**（仅上传图片时） | 对比原图与识别文本，修正 LaTeX/数字/图形描述错误 | `FORMULA_VERIFY_PROMPT` | `problem_analysis/formula_verifier.py`：第 8 行常量，在 `verify_and_fix_formulas()` 中 `format(extracted_text=...)` 后与原图一起发给多模态 LLM |
| **题目分析** | 分析题目并生成解题步骤（steps：step_id、description、math_formula、visual_focus、voiceover_text） | `PROBLEM_ANALYSIS_PROMPT`（仅文本）/ `PROBLEM_ANALYSIS_PROMPT_WITH_IMAGE`（文本+原图） | `problem_analysis/analyzer.py`：第 7、13 行常量，在 `analyze_problem()` 中按是否带图选择其一 |
**Manim 视频流水线中的 LLM 阶段：**

| 阶段 | 用途 | 说明 | 位置 |
|------|------|------|------|
| **数学分析(tutor)** | 输出数学事实分析（已知条件、推导事实、图形构建方法、结论） | 仅文本 / 文本+原图 | `tutor_pipeline/stages.py`：`MATH_ANALYSIS_PROMPT*`，`analyze_math_tutor()` |
| **HTML 可视化** | 根据数学分析生成 HTML+SVG 画图过程 | 纯文本 | `tutor_pipeline/stages.py`：`HTML_VISUALIZATION_PROMPT`，`generate_html_visualization()` |
| **分镜脚本** | 生成分镜设计 + 音频生成清单表 | 纯文本 | `tutor_pipeline/stages.py`：`STORYBOARD_PROMPT`，`generate_storyboard()` |
| **Manim 实现** | 根据分镜与脚手架补全完整 script.py | 纯文本，长超时 | `tutor_pipeline/stages.py`：`IMPLEMENT_SCRIPT_PROMPT`，`implement_script()` |

**Prompt 内容摘要：**

- **VISION_PROMPT**：要求按「题目文字」「图形描述」「公式列表」三部分输出，公式用 LaTeX，图形描述包含类型、标注、边长角度等。
- **FORMULA_VERIFY_PROMPT**：要求对比原图与识别文本，检查公式正确性、完整性、数字符号、图形描述等，修正后输出完整文本，不添加解释。
- **PROBLEM_ANALYSIS_PROMPT / WITH_IMAGE**：数学专家+动画脚本设计师角色，输出 steps 列表（step_id、description、math_formula、visual_focus、voiceover_text）；带图版强调以图片为准的几何与公式细节。
- **Tutor 数学分析**：数学专家角色，输出「已知条件 / 推导事实 / 图形构建方法 / 需要证明的结论」；禁止用坐标系求解，用几何推理。
- **Tutor 分镜**：视频分镜设计师角色，输出分镜设计（画面、字幕、读白、动画、退场）与音频生成清单表（幕号、文件名、读白文本、时长留空）。
- **Tutor Manim 实现**：Manim 动画工程师角色，补全 `calculate_geometry`、`assert_geometry`、每幕 `add_sound` 与动画，全部用 `Text` 不用 `MathTex`。

---

## 本地运行方式

1. 配置好 `OPENAI_API_KEY` 等（见上）；上传题目图片时需**支持视觉的模型**（如 `gpt-4o` 或配置 `VISION_MODEL`）。
2. 安装依赖并启动（任选其一）：
   - **推荐**：使用启动脚本（会自动执行 `uv sync`）
     ```bash
     ./run.sh          # macOS/Linux
     # 或 run.bat     # Windows
     ```
   - 或手动执行：
     ```bash
     uv sync
     uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
     ```
   可通过环境变量 `HOST`、`PORT` 修改地址与端口，例如：`PORT=9000 ./run.sh`。

3. 打开浏览器访问 **Web 界面**：  
   **http://localhost:8000/**  
   输入题目或上传题目图片，点击「生成视频」，等待完成后在页内播放或下载。

4. **输出**：按 Tutor 技能 8 步生成 Manim MP4，需安装 Manim（见下方「Manim 视频流水线」）。

5. API 说明：
   - `POST /api/generate_video`：提交题目。**multipart/form-data** 字段：`problem`（题目文本，可选）、`image`（题目图片，可选）。后台走 Tutor 流水线，返回 MP4 的 `result_url`。
   - **前置 Nginx**：接口已改为立即返回 task_id，后台执行识别与生成。若仍 504，可调大 `proxy_read_timeout`（如 `120s`）。**脚本生成阶段** 504 多为转发到 LLM 的网关读超时过短，建议该网关 `proxy_read_timeout` **180s 或 300s**，并设置 `LLM_SCRIPT_TIMEOUT=300`。
   - `GET /api/tasks/{task_id}`：查询任务状态与结果；成功时 `result_url` 为可播放/下载的地址（`/results/{task_id}.mp4`）。响应含 `step_durations`（各步骤执行时长，秒），用于界面进度条与历史回显。
   - `POST /api/tasks/{task_id}/retry`：对失败任务断点重试。
   - `GET /api/history`、`DELETE /api/history/{task_id}`、`POST /api/regenerate`：历史与重新生成。历史项含 `problem_preview`（标题）、`step_durations`（步骤耗时）；上传图片时标题为图片文件名，重新生成时沿用原记录标题。

---

## 可配置项（自愈、时长）

- **默认 step 时长**：`DEFAULT_WAIT_SECONDS`，默认 2.0 秒。当 TTS 返回的时长数量少于步骤数时，不足的步骤使用该默认时长。
- **Manim 视频流水线**：
  - 需安装 Manim：`pip install manim` 或取消注释 `requirements.txt` 中的 `manim`；系统需 FFmpeg（TTS 已用）。
  - 环境变量见上表（`MANIM_COMMAND`、`MANIM_SCENE_CLASS`、`MANIM_QUALITY`、`MANIM_SELF_HEAL_MAX_ATTEMPTS`）。
  - 流水线 8 步：数学分析(tutor) → HTML 可视化 → 分镜脚本 → TTS 与时长 → 验证音频 → 脚手架 → Manim 实现 → 检查与渲染；支持断点检查点，失败后可重试从断点继续。

---

## 项目结构

- `problem_analysis/`：题目理解；图片识别、公式验证、题目分析（含各 prompt 常量）
- `asset_generation/`：TTS、Manim 渲染（含自愈）等
- `api/`：流水线编排（Manim 视频）、任务存储、FastAPI 路由
- `tutor_pipeline/`：Tutor 技能服务端实现（数学分析、HTML 可视化、分镜、TTS、脚手架、Manim 实现、渲染）
- `config.py`：pydantic-settings 配置
- `llm_runner.py`：LangChain 可复用 LLM 调用（结构化/纯文本/多模态）
- `main.py`：FastAPI 应用入口
- `static/`：Web 前端（index.html）

---

## 测试

```bash
uv run pytest
```
