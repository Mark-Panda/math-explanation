# Capability: multimodal-script

## ADDED Requirements

### Requirement: 基于步骤数据生成 Manim 代码与多模态素材描述

系统 SHALL 接受题目分析阶段产出的 steps 数据（与 problem-analysis 输出格式一致），并生成：1）可被 Manim 执行的 Python 代码（包含 `SolutionScene` 类）；2）与步骤对应的图像提示词列表（用于可选 SD）；3）与步骤对应的旁白文案或时间同步所需字段。输出 MUST 为结构化格式（如 JSON），包含 `manim_code`（字符串）及 `image_prompts`（列表）；Manim 代码中每个步骤对应 construct 内的子动画，并使用 `self.wait()` 占位以便后续注入时长。

#### Scenario: 成功生成脚本

- **WHEN** 调用方传入合法的 steps 数据且 LLM 服务可用
- **THEN** 系统返回包含 `manim_code` 与 `image_prompts` 的完整输出；`manim_code` 中 MUST 包含类名 `SolutionScene` 且包含 `self.wait()` 占位

#### Scenario: steps 数据不合法

- **WHEN** 传入的 steps 缺少必需字段或格式错误
- **THEN** 系统 SHALL 在调用 LLM 前校验并返回明确错误，不发起请求

#### Scenario: 与步骤数一致

- **WHEN** 传入 N 个步骤
- **THEN** `image_prompts` 的条目数 SHALL 与 N 一致（或明确约定为一一对应），便于下游按步使用
