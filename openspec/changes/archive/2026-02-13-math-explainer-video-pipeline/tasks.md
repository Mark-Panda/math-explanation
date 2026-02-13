# 数学讲解视频流水线 - 任务列表

## 1. 项目与配置

- [x] 1.1 创建 Python 项目结构（包/模块：problem_analysis、script_generation、asset_generation、composition、api）
- [x] 1.2 添加依赖声明（langchain、langchain-openai 或 langchain-anthropic 等 ChatModel 适配器、edge-tts 或 azure/openai TTS、manim、ffmpeg-python 或 subprocess、pydantic-settings 等）
- [x] 1.3 实现配置加载（环境变量或 .env，含 LLM 端点/Key、TTS 配置、Manim/FFmpeg 路径、自愈最大重试次数）
- [x] 1.4 基于 LangChain 封装可复用的 LLM 调用（ChatModel + 可选 with_structured_output），供题目分析、脚本生成、代码自愈共用

## 2. 题目分析 (problem-analysis)

- [x] 2.1 实现 steps JSON 的 schema 定义（step_id、description、math_formula、visual_focus、voiceover_text）
- [x] 2.2 实现 analyze_problem(problem_text)：校验非空、通过 LangChain 调用 LLM（结构化输出 steps JSON）、返回 steps
- [x] 2.3 为题目分析添加单测或手测（合法输入、空输入、模拟 LLM 失败）

## 3. 多模态脚本生成 (multimodal-script)

- [x] 3.1 定义脚本生成输出 schema（manim_code、image_prompts 等）
- [x] 3.2 实现 generate_manim_code_and_prompts(steps_data)：校验 steps、通过 LangChain 调用 LLM、返回结构化结果（manim_code、image_prompts 等）
- [x] 3.3 在 Prompt 中约定 SolutionScene 类名与 self.wait() 占位，并做返回格式校验
- [x] 3.4 为脚本生成添加单测或手测

## 4. 素材生成 - TTS 与时长

- [x] 4.1 实现 generate_audio_with_duration(text, output_path)：调用 TTS、写入文件、返回时长（秒）
- [x] 4.2 实现按步骤批量生成音频并收集各步时长列表（durations）
- [x] 4.3 实现 inject_timing_into_code(original_code, durations, default_wait)：按顺序替换 self.wait() 为 self.wait(duration)，不足用 default_wait

## 5. 素材生成 - Manim 渲染与自愈

- [x] 5.1 实现 render_manim_video(code_string, output_file)：写临时 .py、subprocess 调用 manim CLI、捕获退出码与 stderr
- [x] 5.2 实现 fix_code_with_llm(bad_code, error_msg)：通过 LangChain 将错误信息与代码发 LLM 请求修复，返回新代码
- [x] 5.3 实现自愈循环：执行 → 失败则修复 → 重试，最多 N 次；成功或达上限后返回结果或抛出
- [x] 5.4 为 Manim 渲染与自愈添加单测或集成测试（含模拟失败与修复成功）

## 6. 素材生成 - 可选 SD（占位）

- [x] 6.1 实现 generate_concept_image(prompt, filename) 占位：若不启用 SD 则跳过或写占位说明，不报错

## 7. 视频合成 (video-composition)

- [x] 7.1 实现 compose_video(manim_video_path, audio_path, output_path)：校验输入文件存在、调用 FFmpeg（-c:v copy、-c:a aac、-shortest）
- [x] 7.2 处理 FFmpeg 非零退出码并向上层返回明确错误
- [x] 7.3 为合成添加单测或手测（含缺失输入文件场景）

## 8. 流水线编排与 API (explainer-api)

- [x] 8.1 实现编排函数：依次调用题目分析 → 脚本生成 → TTS 与时长收集 → 时长注入 → Manim 自愈渲染 → 音频拼接（若多段）→ 合成，并传递各阶段输出
- [x] 8.2 实现 FastAPI POST 接口（如 /generate_video），接收题目、触发生成（异步 BackgroundTasks）、返回任务 ID
- [x] 8.3 实现 GET /tasks/{task_id}：返回任务状态（pending/running/success/failed）及成功时的结果视频 URL（可供静态资源或下载）
- [x] 8.4 定义请求/响应模型（题目字段、错误码、任务状态、结果 path/url）
- [x] 8.5 端到端手测：从题目输入到下载/播放最终 MP4（需本地启动服务并配置 LLM/Manim/TTS/FFmpeg 后手测）

## 9. Web 界面 (explainer-web-ui)

- [x] 9.1 在 FastAPI 中挂载静态资源目录（StaticFiles），提供前端入口页（如 index.html）
- [x] 9.2 实现题目输入区：文本框、提交按钮；提交时校验非空并调用 POST /generate_video，接收任务 ID
- [x] 9.3 实现生成状态展示：轮询 GET /tasks/{task_id}，展示「生成中」/「成功」/「失败」及失败时的错误信息
- [x] 9.4 生成成功后展示内嵌视频播放器（HTML5 video 绑定结果 URL）与下载链接
- [x] 9.5 （可选）支持题目文件上传：上传题目图片，由视觉模型识别后作为题目提交

## 10. 文档与交付

- [x] 10.1 编写 README：依赖安装、环境变量说明、本地运行方式（含启动后访问 Web 界面地址）
- [x] 10.2 在 design 或 README 中记录自愈重试次数、默认 wait 时长等可配置项
