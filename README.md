# 数学讲解视频流水线

从数学题目自动生成带旁白与动画的讲解视频。流水线：题目分析（LLM）→ 多模态脚本生成（Manim 代码 + 旁白）→ TTS 与时长注入 → Manim 渲染（含自愈）→ FFmpeg 合成。提供 Web 界面：输入题目、触发生成、轮询状态、页面内播放与下载。

## 依赖安装

- Python 3.10+
- 安装 [uv](https://docs.astral.sh/uv/)（`curl -LsSf https://astral.sh/uv/install.sh | sh` 或 `pip install uv`）
- **系统安装 [FFmpeg](https://ffmpeg.org/)**（需包含 `ffmpeg` 与 `ffprobe`，用于音频时长探测与最终视频合成）。未安装时 TTS 会使用默认时长，合成阶段会报错。
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: 从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并将 `bin` 加入 PATH
- [Manim](https://www.manim.community/)（数学动画渲染）已为默认依赖，**需先装系统依赖**再 `uv sync`：
  - **macOS**：`brew install pkg-config cairo ffmpeg`
  - **Ubuntu/Debian**：`sudo apt install pkg-config libcairo2-dev ffmpeg`
  - 若出现 `pycairo` / `cairo found: NO`，即未装好 pkg-config 或 cairo。
- 可选：LaTeX（Manim 渲染公式时用，如 `brew install --cask mactex`）

```bash
uv sync
```

若 `uv run manim checkhealth` 报错「Failed to spawn: manim」，可改用：`uv run python -m manim checkhealth`

## 环境变量说明

复制 `.env.example` 为 `.env` 后按需修改（勿将 `.env` 提交到版本库），或直接设置环境变量。

**大模型（LLM）相关：**

| 变量                  | 说明                                               | 默认/示例        |
| --------------------- | -------------------------------------------------- | ---------------- |
| `OPENAI_API_KEY`      | **必填**，OpenAI 或兼容接口的 API Key              | `sk-...`         |
| `OPENAI_BASE_URL`     | 可选，自定义 API 基础 URL（代理、Azure、国内中转） |                  |
| `LLM_MODEL`           | 模型名称                                           | `gpt-4o`         |
| `LLM_TEMPERATURE`     | 生成温度（0~2，建议 0.1~0.3）                      | `0.2`            |
| `LLM_MAX_TOKENS`      | 单次请求最大 token 数                              | 不设则用模型默认 |
| `LLM_REQUEST_TIMEOUT` | 单次请求超时（秒）                                 | `120`            |
| `LLM_SCRIPT_TIMEOUT`  | 脚本生成阶段超时（秒，建议 ≥300）                  | `300`            |

**其他：**

| 变量                           | 说明                       | 默认                   |
| ------------------------------ | -------------------------- | ---------------------- |
| `TTS_VOICE`                    | Edge-TTS 音色              | `zh-CN-XiaoxiaoNeural` |
| `MANIM_COMMAND`                | Manim 命令行               | `manim`                |
| `FFMPEG_COMMAND`               | FFmpeg 命令行              | `ffmpeg`               |
| `MANIM_SELF_HEAL_MAX_ATTEMPTS` | Manim 代码自愈最大重试次数 | `3`                    |
| `DEFAULT_WAIT_SECONDS`         | 时长不足时默认 wait（秒）  | `2.0`                  |

## 本地运行方式

1. 配置好 `OPENAI_API_KEY` 等（见上）。
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
   在页面中输入题目、点击「生成视频」，等待生成完成后可在页内播放或下载。

4. API 说明：
   - `POST /api/generate_video`：提交题目。支持 **multipart/form-data**：`problem`（题目文本，可选）、`image`（题目图片文件，可选）。仅文本、仅图片、或两者同时提供均可；有图片时使用视觉模型识别题目文字。返回 `{"task_id": "uuid", "status": "pending"}`。
   - 使用「上传题目图片」功能时，需使用**支持视觉的模型**（如 `gpt-4o`），并在 `.env` 中设置 `LLM_MODEL=gpt-4o`。
   - **前置 Nginx 时**：`POST /api/generate_video` 已改为立即返回 task_id，图片识别与生成在后台执行，一般不会触发 504。若仍出现 504，可调大 Nginx 的 `proxy_read_timeout`（例如 `proxy_read_timeout 120s;`）。
   - **阶段2 脚本生成时 LLM 返回 504**：说明**转发到 LLM 的网关**（如 ops-ai-gateway 前的 Nginx）读超时过短。脚本生成需返回整段 Manim 代码，常超过 60 秒。请在**该网关**上把 `proxy_read_timeout` 调大（建议 **180s 或 300s**），并确保 `.env` 中 `LLM_SCRIPT_TIMEOUT=300`。
   - `GET /api/tasks/{task_id}`：查询任务状态与结果；成功时 `video_url` 为 `/results/{task_id}.mp4`，可直接播放或下载。

## 可配置项（design / 自愈与时长）

- **自愈重试次数**：`MANIM_SELF_HEAL_MAX_ATTEMPTS`，默认 3。Manim 代码执行失败时由 LLM 修复后重试，超过此次数则任务失败。
- **默认 wait 时长**：`DEFAULT_WAIT_SECONDS`，默认 2.0 秒。当 TTS 返回的时长数量少于 Manim 中 `self.wait()` 个数时，不足的 wait 使用该默认值。

## 项目结构

- `problem_analysis/`：题目理解与 steps schema、analyze_problem
- `script_generation/`：多模态脚本生成（Manim 代码 + image_prompts）
- `asset_generation/`：TTS、时长注入、Manim 渲染与自愈、SD 占位
- `composition/`：音频拼接、FFmpeg 合成
- `api/`：流水线编排、任务存储、FastAPI 路由
- `config.py`：pydantic-settings 配置
- `llm_runner.py`：LangChain 可复用 LLM 调用
- `main.py`：FastAPI 应用入口
- `static/`：Web 前端（index.html）

## 测试

```bash
uv run pytest
```
# math-explanation
