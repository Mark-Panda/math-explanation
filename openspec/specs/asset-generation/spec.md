# Capability: asset-generation

## Purpose

为讲解视频流水线提供 TTS 音频生成、时长注入、Manim 渲染与自愈，以及可选的概念图占位，产出视频与音频素材。

## Requirements

### Requirement: TTS 生成语音并返回时长

系统 SHALL 对给定文本调用 TTS 服务生成音频文件，并返回该音频的时长（单位：秒）。调用方 SHALL 可指定输出文件路径或由系统生成临时路径；返回的时长 SHALL 用于后续注入 Manim 的 `self.wait()`。

#### Scenario: 成功生成并返回时长

- **WHEN** 传入非空文本及有效输出路径且 TTS 服务可用
- **THEN** 系统生成音频文件并返回大于 0 的时长（秒），精度至少到小数点后一位

#### Scenario: TTS 失败

- **WHEN** TTS 服务超时或返回错误
- **THEN** 系统 SHALL 抛出或返回可区分的错误，不写入不完整音频

### Requirement: 将各步时长注入 Manim 代码

系统 SHALL 接受原始 Manim 代码字符串与各步时长数组（与步骤顺序一致），并将代码中的 `self.wait()` 按出现顺序替换为 `self.wait(duration)`；若时长数量少于 wait 个数，不足部分 SHALL 使用配置的默认时长（如 2 秒）；若时长数量多于 wait 个数，多余时长 SHALL 被忽略。

#### Scenario: 一一对应替换

- **WHEN** 代码中 self.wait() 个数与 durations 数组长度一致
- **THEN** 每个 self.wait() 被替换为 self.wait(durations[i])，且生成的代码可被 Manim 正确解析

#### Scenario: 时长不足

- **WHEN** durations 长度小于 self.wait() 个数
- **THEN** 未被赋值的 wait 使用默认时长（如 2.0），且行为在 spec 或配置中明确

### Requirement: Manim 代码执行与自愈

系统 SHALL 在独立子进程（或沙箱）中执行 Manim 代码并渲染为视频；若执行失败（非零退出码或异常），系统 SHALL 将错误信息与当前代码发给 LLM 请求修复，并重试执行；重试次数 SHALL 有上限（如 3），超过后 SHALL 向上层返回失败而非无限重试。

#### Scenario: 首次执行成功

- **WHEN** 注入时长后的 Manim 代码无错误
- **THEN** 渲染产出视频文件，子进程退出码为 0，无重试

#### Scenario: 执行失败后修复成功

- **WHEN** 首次执行失败，LLM 返回修复后的代码且第二次执行成功
- **THEN** 系统产出视频文件并返回成功，调用方无需感知重试

#### Scenario: 达到最大重试仍失败

- **WHEN** 已重试至配置的最大次数仍无法成功渲染
- **THEN** 系统 SHALL 向上层返回明确失败结果（含最后错误信息），不继续重试

### Requirement: 可选概念图生成（占位）

系统 MAY 支持根据提示词生成概念图并写入指定路径；若本迭代不实现，SHALL 提供占位接口（如接收 prompt 与 path，不调用 SD 或直接跳过），以便流水线统一调用。

#### Scenario: 占位实现

- **WHEN** 调用方传入 prompt 与 filename
- **THEN** 若未启用 SD，系统 SHALL 不报错并可在文档中说明行为（跳过或返回占位路径）
