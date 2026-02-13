# Capability: problem-analysis

## Purpose

将数学题目文本解析为结构化解题步骤（含步骤 ID、描述、公式、视觉焦点、旁白文案），供下游脚本生成与素材生成使用。

## Requirements

### Requirement: 题目解析为结构化解题步骤

系统 SHALL 接受一道数学题目的文本输入，并返回结构化的解题步骤数据。输出 MUST 为 JSON，且包含字段 `steps`；每个步骤 MUST 包含：`step_id`（整数）、`description`（字符串）、`math_formula`（LaTeX 格式字符串）、`visual_focus`（字符串）、`voiceover_text`（该步旁白文案字符串）。

#### Scenario: 成功解析题目

- **WHEN** 调用方传入非空题目文本且 LLM 服务可用
- **THEN** 系统返回合法 JSON，包含至少一个步骤，且每个步骤均包含上述五类字段

#### Scenario: 题目文本为空

- **WHEN** 调用方传入空字符串或仅空白字符
- **THEN** 系统 SHALL 在调用 LLM 前进行校验并返回明确错误（如参数错误），不发起 LLM 请求

#### Scenario: 外部服务不可用

- **WHEN** LLM 请求超时或返回不可用
- **THEN** 系统 SHALL 向上层返回可区分的错误（如超时、服务错误），便于编排层重试或提示用户
