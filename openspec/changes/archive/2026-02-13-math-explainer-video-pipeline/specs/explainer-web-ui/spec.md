# Capability: explainer-web-ui

## ADDED Requirements

### Requirement: 题目输入与上传

Web 界面 SHALL 提供用户输入数学题目的方式：至少支持**文本框输入**；可选支持**文件上传**（如文本或图片，图片需后端或后续扩展支持解析）。提交前 SHALL 对非空进行校验或提示。

#### Scenario: 文本框提交题目

- **WHEN** 用户在文本框中输入题目并点击提交
- **THEN** 界面将题目内容作为请求体发送至生成接口（如 POST /generate_video），并进入「生成中」或任务跟踪状态

#### Scenario: 题目为空时提交

- **WHEN** 用户未输入题目或仅输入空白即提交
- **THEN** 界面 SHALL 阻止请求并给出提示（如「请输入题目」），不调用后端

### Requirement: 触发生成与状态展示

Web 界面 SHALL 在用户提交题目后触发生成任务（调用后端异步接口），并展示生成状态（如生成中、成功、失败）。在异步模式下 SHALL 通过轮询任务状态接口（如 GET /tasks/{task_id}）更新界面，直至任务完成或失败。

#### Scenario: 提交后展示生成中

- **WHEN** 用户提交题目且后端返回任务 ID
- **THEN** 界面 SHALL 显示「生成中」或等价提示，并开始轮询状态接口

#### Scenario: 轮询到失败

- **WHEN** 轮询返回任务状态为失败
- **THEN** 界面 SHALL 展示错误信息并停止轮询，允许用户重新输入或重试

### Requirement: 生成完成后播放与下载

当任务状态为成功且返回结果视频 URL 时，Web 界面 SHALL 在页面内提供**视频播放**（如使用 HTML5 `<video>` 或兼容控件），并 SHALL 提供**下载**该讲解视频的入口（如下载链接或按钮）。

#### Scenario: 成功后在页内播放

- **WHEN** 轮询返回 success 及视频 URL
- **THEN** 界面 SHALL 展示可播放的视频播放器，用户可在不离开页面的情况下观看讲解动画

#### Scenario: 提供下载入口

- **WHEN** 生成成功且视频 URL 可用
- **THEN** 界面 SHALL 提供下载链接或按钮，用户点击后可下载该 MP4 文件
