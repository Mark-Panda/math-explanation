"""从环境变量或 .env 加载配置（LLM、TTS、Manim/FFmpeg、自愈重试等）。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 文本模型（LLM）配置 ----------
    openai_api_key: str = ""
    """OpenAI API Key（或兼容接口的 Key），必填。"""
    openai_base_url: str | None = None
    """API 基础 URL，可选。用于代理或自定义端点（如 Azure、国内中转）。"""
    llm_model: str = "gpt-4o"
    """文本模型名称，用于脚本生成、代码自愈等纯文本任务。"""
    llm_temperature: float = 0.2
    """生成温度，0~2，越低越稳定，越高越随机。题目分析与代码生成建议 0.1~0.3。"""
    llm_max_tokens: int | None = None
    """单次请求最大 token 数，不设则用模型默认。"""
    llm_request_timeout: float = 120.0
    """单次请求超时秒数（题目分析、代码自愈等）。"""
    llm_script_timeout: float = 300.0
    """脚本生成请求超时秒数（阶段2 返回整段 Manim 代码，耗时长；若前置网关 504 需调大网关超时）。"""

    # ---------- 视觉模型（Vision LLM）配置 ----------
    # 未配置时自动回退到上方文本模型的对应配置
    vision_api_key: str | None = None
    """视觉模型 API Key，不设则使用 openai_api_key。"""
    vision_base_url: str | None = None
    """视觉模型 API 基础 URL，不设则使用 openai_base_url。"""
    vision_model: str | None = None
    """视觉模型名称（如 gpt-4o、claude-sonnet-4-5），用于图片识别、带图分析等多模态任务。不设则使用 llm_model。"""
    vision_temperature: float | None = None
    """视觉模型生成温度，不设则使用 llm_temperature。"""
    vision_max_tokens: int | None = None
    """视觉模型单次请求最大 token 数，不设则使用 llm_max_tokens。"""
    vision_request_timeout: float | None = None
    """视觉模型单次请求超时秒数，不设则使用 llm_request_timeout。"""

    # TTS（edge-tts 用 voice 名）
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # Manim / FFmpeg 路径（空则用系统 PATH）
    manim_command: str = "manim"
    ffmpeg_command: str = "ffmpeg"

    # 自愈：Manim 代码失败时 LLM 修复的最大重试次数
    manim_self_heal_max_attempts: int = 5

    # 默认 wait 时长（秒），用于时长不足时的兜底
    default_wait_seconds: float = 2.0


def get_settings() -> Settings:
    return Settings()
