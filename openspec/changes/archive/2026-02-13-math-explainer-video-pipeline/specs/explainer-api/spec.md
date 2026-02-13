# Capability: explainer-api

## ADDED Requirements

### Requirement: 提供触发生成讲解视频的 HTTP 接口

系统 SHALL 提供 HTTP API（如 `POST /generate_video` 或等价路径），接受题目文本（如 JSON body 中的 `problem` 字段），触发生成流程并返回任务标识或结果信息。接口 SHALL 在合理时间内返回（若采用异步任务，则返回任务 ID 及状态；若采用同步，则应在设计文档约定的超时内返回或返回 202 + 任务 ID）。

#### Scenario: 同步执行并返回结果路径

- **WHEN** 请求体包含有效题目且采用同步实现
- **THEN** 在流水线全部成功后，响应 SHALL 包含成功状态及最终视频的路径或可访问 URL（如 `url` 或 `path` 字段）

#### Scenario: 异步执行并返回任务 ID

- **WHEN** 请求体包含有效题目且采用异步实现（如 BackgroundTasks）
- **THEN** 接口 SHALL 立即返回 202 或 200，并在响应体中包含任务 ID（或等价标识），供客户端轮询或回调获取最终结果

#### Scenario: 参数无效

- **WHEN** 请求体缺少题目或题目为空
- **THEN** 接口 SHALL 返回 4xx 及明确错误信息，不触发生成流程

#### Scenario: 流水线某阶段失败

- **WHEN** 题目分析、脚本生成、素材生成或合成任一步失败
- **THEN** 接口或任务结果 SHALL 返回可区分的错误信息（如阶段名 + 原因），便于排查与重试

### Requirement: 提供任务状态与结果查询接口（供 Web 轮询）

当采用异步任务时，系统 SHALL 提供按任务 ID 查询状态的接口（如 `GET /tasks/{task_id}` 或等价路径）。响应 SHALL 包含任务状态（如 pending、running、success、failed）及在成功时提供可访问的结果视频 URL（供前端播放与下载）。

#### Scenario: 轮询未完成任务

- **WHEN** 客户端使用有效任务 ID 请求状态且任务尚未完成
- **THEN** 接口 SHALL 返回当前状态（如 running）及可选进度信息，不返回结果 URL

#### Scenario: 轮询已完成成功任务

- **WHEN** 客户端使用有效任务 ID 请求状态且任务已成功完成
- **THEN** 接口 SHALL 返回 success 状态及结果视频的 URL（可为相对路径或静态资源路径），供前端嵌入播放或下载

#### Scenario: 轮询失败任务

- **WHEN** 任务已失败
- **THEN** 接口 SHALL 返回 failed 状态及错误信息，便于前端展示提示
