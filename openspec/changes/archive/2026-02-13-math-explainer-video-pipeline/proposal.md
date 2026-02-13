# 数学讲解视频生成流水线 - 提案

## Why

需要一套系统，能够从用户输入的数学题目自动生成「带旁白、动画与口型/节奏对齐」的讲解视频，用于教学与自学场景。结合 LLM 的逻辑推理、Manim 的精确数学渲染与 TTS 的语音合成，在不大规模人工介入的前提下产出既严谨又易理解的讲解内容。当前没有统一流水线将题目解析、脚本生成、素材渲染与合成串联为可交付产品，本变更填补该能力。

## What Changes

- **新增**：题目理解与逻辑拆解服务——输入题目文本，输出结构化解题步骤（JSON，含步骤描述、公式、视觉重点、旁白文案）。
- **新增**：多模态脚本生成服务——基于步骤数据生成 Manim 代码、Stable Diffusion 图像提示词、以及各步旁白文案；输出约定为 JSON（manim_code、image_prompts、voiceover 等）。
- **新增**：素材生成与渲染能力——TTS 生成语音并返回时长；将时长注入 Manim 代码中的 `self.wait()`；在子进程/沙箱中执行 Manim 渲染；对 Manim 代码实现「执行 → 捕获错误 → LLM 修复 → 重试」的自愈循环；可选集成 Stable Diffusion 生成概念图。
- **新增**：视频合成能力——使用 FFmpeg 将 Manim 视频与 TTS 音频合成最终 MP4（以最短流为准等约定）。
- **新增**：流水线编排与 API——FastAPI 提供入口（如 `POST /generate_video`），串起上述阶段（可先同步或 BackgroundTasks），返回任务标识或结果路径。
- **新增**：Web 界面——用户可上传或输入题目、触发生成、查看生成状态，并在生成完成后在页面内播放讲解动画视频（支持下载）。

## Capabilities

### New Capabilities

- `problem-analysis`: 题目理解与逻辑拆解。输入题目文本，输出 steps JSON（step_id、description、math_formula、visual_focus、voiceover_text）。
- `multimodal-script`: 多模态脚本生成。输入 steps 数据，输出 manim_code、image_prompts 及与步骤对应的旁白/时间同步所需字段。
- `asset-generation`: 素材生成与渲染。包含 TTS（含时长）、Manim 代码时长注入、Manim 渲染与自愈、可选 SD 图像生成。
- `video-composition`: 视频合成。输入 Manim 视频与音频路径，输出最终 MP4。
- `explainer-api`: 讲解视频流水线 API。编排上述能力，暴露 HTTP 接口与任务/结果约定。
- `explainer-web-ui`: Web 可视化界面。支持题目上传/输入、触发生成、状态展示与生成完成后页面内播放（及下载）视频。

### Modified Capabilities

- （无；本项目为从零构建，无既有 spec 需修改。）

## Impact

- **代码与模块**：新增 Python 3.10+ 后端（建议包/模块划分：problem_analysis、script_generation、asset_generation、composition、api）及前端静态资源或轻量前端（用于 Web 界面）。
- **依赖**：**LangChain** 作为大模型调用与编排框架；LLM 后端（如 OpenAI GPT-4o / Claude）通过 LangChain 接入；TTS（如 Edge-TTS / Azure / OpenAI）、Manim、FFmpeg；可选 SymPy、Stable Diffusion API。
- **配置与密钥**：LLM/TTS/SD 的 API 密钥与端点、Manim/FFmpeg 路径等通过环境变量或配置文件管理，不写死。
- **部署**：可先单机运行（FastAPI 托管 API + 静态 Web 资源，本地 Manim/FFmpeg），后续可考虑异步队列与独立 Worker 以应对渲染耗时与成本。
