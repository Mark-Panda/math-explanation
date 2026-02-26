"""从环境变量或 .env 加载配置（LLM、TTS、HTML 渲染自愈等）。"""
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
    llm_models: str | None = None
    """多个文本模型，逗号分隔（如 model_a,model_b）。不设则仅使用 llm_model；设置后按顺序尝试，一个失败则换下一个，每个模型重试 llm_retry_per_model 次。"""
    llm_retry_per_model: int = 3
    """每个模型的最大重试次数，失败后切换下一个模型。"""
    llm_temperature: float = 0.2
    """生成温度，0~2，越低越稳定，越高越随机。题目分析与代码生成建议 0.1~0.3。"""
    llm_max_tokens: int | None = None
    """单次请求最大 token 数，不设则用模型默认。"""
    llm_request_timeout: float = 120.0
    """单次请求超时秒数（题目分析、代码自愈等）。"""
    llm_script_timeout: float = 300.0
    """脚本生成请求超时秒数（阶段2 返回整段动画代码，耗时长；若前置网关 504 需调大网关超时）。"""

    # ---------- 视觉模型（Vision LLM）配置 ----------
    # 未配置时自动回退到上方文本模型的对应配置
    vision_api_key: str | None = None
    """视觉模型 API Key，不设则使用 openai_api_key。"""
    vision_base_url: str | None = None
    """视觉模型 API 基础 URL，不设则使用 openai_base_url。"""
    vision_model: str | None = None
    """视觉模型名称（如 gpt-4o、claude-sonnet-4-5），用于图片识别、带图分析等多模态任务。不设则使用 llm_model。"""
    vision_models: str | None = None
    """多个视觉模型，逗号分隔。不设则仅使用 vision_model/llm_model；设置后按顺序尝试，每个模型重试 llm_retry_per_model 次。"""
    vision_retry_per_model: int | None = None
    """视觉模型每个模型的最大重试次数，不设则使用 llm_retry_per_model。"""
    vision_temperature: float | None = None
    """视觉模型生成温度，不设则使用 llm_temperature。"""
    vision_max_tokens: int | None = None
    """视觉模型单次请求最大 token 数，不设则使用 llm_max_tokens。"""
    vision_request_timeout: float | None = None
    """视觉模型单次请求超时秒数，不设则使用 llm_request_timeout。"""

    # TTS（edge-tts 音色名，建议在 .env 中显式设置，整批步骤会固定使用该音色）
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 主音色 NoAudioReceived 时尝试的备用音色，为空则不尝试
    tts_voice_fallback: str = "zh-CN-YunxiNeural"

    # 自愈：HTML 动画代码校验失败时 LLM 修复的最大重试次数
    html_self_heal_max_attempts: int = 3

    # 默认 wait 时长（秒），用于时长不足时的兜底
    default_wait_seconds: float = 2.0

    # 动画风格（可选）：注入到脚本生成阶段的 prompt，要求大模型按此风格生成。为空则不追加要求。
    # 示例："教科书风格、极简、白底；动画以淡入和滑入为主，避免花哨效果"
    animation_style: str = ""

    # ---------- Tutor 视频流水线（Manim）----------
    manim_command: str = "manim"
    """Manim 可执行命令（或绝对路径），用于渲染视频。"""
    manim_self_heal_max_attempts: int = 3
    """Manim 渲染失败时 LLM 自愈最大重试次数。"""
    manim_scene_class: str = "MathScene"
    """要渲染的 Manim 场景类名（tutor 流水线）。"""
    manim_quality: str = "qh"
    """Manim 渲染质量：ql=480p, qm=720p30, qh=1080p60, qk=4K。"""


def get_settings() -> Settings:
    return Settings()


def get_llm_model_list(settings: Settings | None = None) -> list[str]:
    """文本模型列表：若配置了 llm_models（逗号分隔）则解析为列表，否则为 [llm_model]。"""
    s = settings or get_settings()
    if s.llm_models and s.llm_models.strip():
        return [m.strip() for m in s.llm_models.split(",") if m.strip()]
    return [s.llm_model]


def get_vision_model_list(settings: Settings | None = None) -> list[str]:
    """视觉模型列表：若配置了 vision_models 则解析为列表，否则为 [vision_model 或 llm_model]。"""
    s = settings or get_settings()
    if s.vision_models and s.vision_models.strip():
        return [m.strip() for m in s.vision_models.split(",") if m.strip()]
    return [s.vision_model or s.llm_model]
