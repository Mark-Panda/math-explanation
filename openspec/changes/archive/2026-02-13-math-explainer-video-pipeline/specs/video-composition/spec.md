# Capability: video-composition

## ADDED Requirements

### Requirement: 将视频与音频合成为最终 MP4

系统 SHALL 接受一段视频文件路径（Manim 渲染结果）与一段音频文件路径（如 TTS 拼接后的完整旁白），使用 FFmpeg 将二者合成为单一 MP4 文件。合成时 SHALL 以最短流为准（如 `-shortest`），视频编码 SHALL 支持直接复制（如 `-c:v copy`）以节省时间，音频编码 SHALL 为 AAC 或等价可播放格式；输出路径由调用方指定或由系统生成并返回。

#### Scenario: 成功合成

- **WHEN** 视频与音频路径存在且可读，FFmpeg 可用
- **THEN** 系统在指定输出路径生成 MP4，包含视频流与音频流，播放时音画同步

#### Scenario: 输入文件不存在

- **WHEN** 任一输入路径不存在或不可读
- **THEN** 系统 SHALL 在调用 FFmpeg 前校验并返回明确错误，不产生无效输出

#### Scenario: FFmpeg 执行失败

- **WHEN** FFmpeg 返回非零退出码
- **THEN** 系统 SHALL 捕获错误并向上层返回可区分的失败信息，不将部分生成文件当作成功结果
