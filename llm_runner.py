"""基于 LangChain 的可复用 LLM 调用，供题目分析、脚本生成、代码自愈共用。文字与图片题目统一走多模态大模型，仅请求时区分 content 类型。"""
import logging
from typing import Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from config import get_settings

logger = logging.getLogger(__name__)

# 日志中 prompt/response 最大展示长度，超出截断
_LOG_CONTENT_MAX = 2000

T = TypeVar("T", bound=BaseModel)


def _truncate_for_log(s: str, max_len: int = _LOG_CONTENT_MAX) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"... [截断，共 {len(s)} 字]"


def get_chat_model(
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> BaseChatModel:
    """返回配置好的 ChatModel（OpenAI），参数未传时使用配置文件。"""
    s = get_settings()
    kwargs = {
        "model": model or s.llm_model,
        "temperature": temperature if temperature is not None else s.llm_temperature,
        "api_key": s.openai_api_key or None,
        "request_timeout": timeout if timeout is not None else s.llm_request_timeout,
    }
    if s.openai_base_url:
        kwargs["base_url"] = s.openai_base_url
    if max_tokens is not None or s.llm_max_tokens is not None:
        kwargs["max_tokens"] = max_tokens if max_tokens is not None else s.llm_max_tokens
    return ChatOpenAI(**kwargs)


def invoke_structured(
    prompt: str,
    schema: type[T],
    *,
    model: str | None = None,
    timeout: float | None = None,
) -> T:
    """调用 LLM 并解析为 Pydantic 模型。供题目分析、脚本生成等复用。"""
    logger.info("[LLM] invoke_structured 请求 schema=%s prompt_len=%d", schema.__name__, len(prompt))
    logger.info("[LLM] prompt: %s", _truncate_for_log(prompt))
    llm = get_chat_model(model=model, timeout=timeout)
    structured_llm = llm.with_structured_output(schema)
    result = structured_llm.invoke([HumanMessage(content=prompt)])
    out_str = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
    logger.info("[LLM] invoke_structured 响应 schema=%s response_len=%d", schema.__name__, len(out_str))
    logger.info("[LLM] response: %s", _truncate_for_log(out_str))
    return result


def invoke_plain(prompt: str, *, model: str | None = None) -> str:
    """调用 LLM 返回纯文本（用于代码自愈等）。"""
    logger.info("[LLM] invoke_plain 请求 prompt_len=%d", len(prompt))
    logger.info("[LLM] prompt: %s", _truncate_for_log(prompt))
    llm = get_chat_model(model=model)
    msg = llm.invoke([HumanMessage(content=prompt)])
    content = msg.content if hasattr(msg, "content") else str(msg)
    logger.info("[LLM] invoke_plain 响应 response_len=%d", len(content))
    logger.info("[LLM] response: %s", _truncate_for_log(content))
    return content


def invoke_multimodal_plain(
    prompt: str,
    *,
    content_type: Literal["text", "image"],
    text: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    model: str | None = None,
) -> str:
    """
    统一使用多模态大模型，返回纯文本。请求时区分是文字还是图片：
    - content_type="text"：content 为文本，需传 text
    - content_type="image"：content 为图片+提示，需传 image_base64（及可选 image_mime_type）
    """
    llm = get_chat_model(model=model)
    if content_type == "text":
        if text is None or text == "":
            raise ValueError("content_type 为 text 时需提供 text")
        content: str | list = f"{prompt}\n\n{text}" if (prompt and prompt.strip()) else text
        logger.info("[LLM] invoke_multimodal_plain 请求 content_type=text prompt_len=%d text_len=%d", len(prompt), len(text or ""))
        logger.info("[LLM] prompt: %s", _truncate_for_log(prompt))
        logger.info("[LLM] text: %s", _truncate_for_log(text or ""))
    else:
        if not image_base64:
            raise ValueError("content_type 为 image 时需提供 image_base64")
        url = f"data:{image_mime_type};base64,{image_base64}"
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        logger.info("[LLM] invoke_multimodal_plain 请求 content_type=image prompt_len=%d image_base64_len=%d", len(prompt), len(image_base64))
        logger.info("[LLM] prompt: %s", _truncate_for_log(prompt))
    msg = llm.invoke([HumanMessage(content=content)])
    out = msg.content if hasattr(msg, "content") else str(msg)
    logger.info("[LLM] invoke_multimodal_plain 响应 response_len=%d", len(out))
    logger.info("[LLM] response: %s", _truncate_for_log(out))
    return out


def invoke_vision_plain(
    prompt: str,
    image_base64: str,
    mime_type: str = "image/jpeg",
    *,
    model: str | None = None,
) -> str:
    """调用多模态大模型识别图片内容，返回纯文本。内部使用 invoke_multimodal_plain(content_type="image")。"""
    return invoke_multimodal_plain(
        prompt,
        content_type="image",
        image_base64=image_base64,
        image_mime_type=mime_type,
        model=model,
    )
