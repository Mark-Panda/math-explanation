# 数学讲解流水线

从数学题目自动生成带旁白与网页动画的讲解。流水线：**题目分析（LLM）→ 网页动画脚本生成（HTML + 旁白）→ TTS 与时长收集 → 时长注入与 HTML 渲染（含自愈）**。提供 Web 界面：输入题目或上传题目图片、触发生成、轮询状态、页面内播放与下载。

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

**其他：**

| 变量                         | 说明                               | 默认                   |
| ---------------------------- | ---------------------------------- | ---------------------- |
| `TTS_VOICE`                  | Edge-TTS 音色                      | `zh-CN-XiaoxiaoNeural` |
| `HTML_SELF_HEAL_MAX_ATTEMPTS`| HTML 动画代码自愈最大重试次数      | `3`                    |
| `DEFAULT_WAIT_SECONDS`       | 时长不足时默认 step 时长（秒）    | `2.0`                  |
| `ANIMATION_STYLE`            | 可选。动画风格描述，注入脚本生成 prompt；为空则不追加 | 空                     |

---

## 各阶段 AI Prompt 说明

以下为流水线中所有调用 LLM 的步骤、各自用途及在代码中的位置。

| 阶段 | 用途 | Prompt 名称 / 说明 | 位置（文件: 行/函数） |
|------|------|--------------------|------------------------|
| **图片识别**（仅上传图片时） | 从题目图片中识别文字、公式与图形描述 | `VISION_PROMPT` | `problem_analysis/image_to_text.py`：第 6 行常量，在 `extract_problem_text_from_image()` 中作为多模态请求的文本部分 |
| **公式交叉验证**（仅上传图片时） | 对比原图与识别文本，修正 LaTeX/数字/图形描述错误 | `FORMULA_VERIFY_PROMPT` | `problem_analysis/formula_verifier.py`：第 8 行常量，在 `verify_and_fix_formulas()` 中 `format(extracted_text=...)` 后与原图一起发给多模态 LLM |
| **题目分析** | 分析题目并生成解题步骤（steps：step_id、description、math_formula、visual_focus、voiceover_text） | `PROBLEM_ANALYSIS_PROMPT`（仅文本）/ `PROBLEM_ANALYSIS_PROMPT_WITH_IMAGE`（文本+原图） | `problem_analysis/analyzer.py`：第 7、13 行常量，在 `analyze_problem()` 中按是否带图选择其一 |
| **脚本生成 - 阶段 A** | 基于 steps 设计每步的网页动画方案（shared_css、shared_svg、step_plans 含 animation_description、image_prompt） | `PLAN_PROMPT`（仅文本）/ `PLAN_PROMPT_WITH_IMAGE`（文本+原图） | `script_generation/generator.py`：第 21、41 行常量，在 `_generate_plan()` 中按是否带图选择其一 |
| **脚本生成 - 阶段 B** | 为每一步生成 `animate(container)` 的 JavaScript 函数体 | `STEP_CODE_PROMPT` | `script_generation/generator.py`：第 62 行常量，在 `_generate_step_code()` 中 `format(shared_css_summary=..., step_id=..., description=..., ...)` 后调用结构化 LLM |
| **HTML 自愈** | 校验/渲染失败时，根据错误信息修复 HTML 动画代码 | 内联 prompt（错误信息 + 代码片段） | `asset_generation/html_render.py`：`fix_html_with_llm()` 内，约第 310 行 |

**Prompt 内容摘要：**

- **VISION_PROMPT**：要求按「题目文字」「图形描述」「公式列表」三部分输出，公式用 LaTeX，图形描述包含类型、标注、边长角度等。
- **FORMULA_VERIFY_PROMPT**：要求对比原图与识别文本，检查公式正确性、完整性、数字符号、图形描述等，修正后输出完整文本，不添加解释。
- **PROBLEM_ANALYSIS_PROMPT / WITH_IMAGE**：数学专家+动画脚本设计师角色，输出 steps 列表（step_id、description、math_formula、visual_focus、voiceover_text）；带图版强调以图片为准的几何与公式细节。
- **PLAN_PROMPT / PLAN_PROMPT_WITH_IMAGE**：数学动画设计师角色，输出 shared_css、shared_svg、step_plans（step_id、animation_description、image_prompt）；约束 800×600、Unicode 公式、纯 CSS 动画、SVG 几何。若配置了 **动画风格**（`ANIMATION_STYLE` 或接口参数 `animation_style`），会在此处及阶段 B 追加「动画风格要求」。
- **STEP_CODE_PROMPT**：前端动画工程师角色，给定当前步骤描述、公式、视觉重点、旁白、动画方案，输出 `animate_body`（仅函数体），通过 `container` 操作 DOM，仅用 CSS 动画与已有 SVG，不用外部库。同样会注入动画风格要求（若有）。
- **HTML 自愈**：给定错误信息与问题代码，要求只返回完整可运行 HTML 片段，保留 `animation-container`、`stepAnimations`、`STEP_PLACEHOLDER`，不用外部库。

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

4. API 说明：
   - `POST /api/generate_video`：提交题目。支持 **multipart/form-data**：`problem`（题目文本，可选）、`image`（题目图片，可选）、`animation_style`（可选，动画风格描述，会注入到脚本生成 prompt；不填则使用环境变量 `ANIMATION_STYLE`）。仅文本、仅图片或两者均可；有图片时先识别文字并可选公式验证，再带原图跑流水线。返回 `{"task_id": "uuid", "status": "pending"}`。
   - **前置 Nginx**：接口已改为立即返回 task_id，后台执行识别与生成。若仍 504，可调大 `proxy_read_timeout`（如 `120s`）。**脚本生成阶段** 504 多为转发到 LLM 的网关读超时过短，建议该网关 `proxy_read_timeout` **180s 或 300s**，并设置 `LLM_SCRIPT_TIMEOUT=300`。
   - `GET /api/tasks/{task_id}`：查询任务状态与结果；成功时结果中包含可播放/下载的地址。

---

## 可配置项（自愈、时长与动画风格）

- **HTML 自愈重试次数**：`HTML_SELF_HEAL_MAX_ATTEMPTS`，默认 3。HTML 动画校验或渲染失败时由 LLM 修复后重试，超过此次数则任务失败。
- **默认 step 时长**：`DEFAULT_WAIT_SECONDS`，默认 2.0 秒。当 TTS 返回的时长数量少于步骤数时，不足的步骤使用该默认时长。
- **动画风格**：`ANIMATION_STYLE` 或接口参数 `animation_style`。非空时会以「**动画风格要求**：xxx」的形式追加到脚本生成两阶段的 prompt 中，让大模型按该风格生成（如「教科书风格、极简、白底；动画以淡入和滑入为主，避免花哨效果」）。为空则不追加，沿用 prompt 内默认约束。

---

## 项目结构

- `problem_analysis/`：题目理解与 steps schema；图片识别、公式验证、题目分析（含各 prompt 常量）
- `script_generation/`：两阶段脚本生成（动画方案 + 每步 JS 代码），产出 HTML 片段与 image_prompts
- `asset_generation/`：TTS、时长注入、HTML 动画校验与渲染（含自愈）、SD 占位
- `composition/`：FFmpeg 音频拼接/视频合成（当前主流程为 HTML 动画，此模块为 Manim 视频流程预留）
- `api/`：流水线编排、任务存储、FastAPI 路由
- `config.py`：pydantic-settings 配置
- `llm_runner.py`：LangChain 可复用 LLM 调用（结构化/纯文本/多模态）
- `main.py`：FastAPI 应用入口
- `static/`：Web 前端（index.html）

---

## 测试

```bash
uv run pytest
```
