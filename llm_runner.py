"""基于 LangChain 的可复用 LLM 调用，供题目分析、脚本生成、代码自愈共用。"""
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from config import get_settings

T = TypeVar("T", bound=BaseModel)


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
    llm = get_chat_model(model=model, timeout=timeout)
    structured_llm = llm.with_structured_output(schema)
    return structured_llm.invoke([HumanMessage(content=prompt)])


def invoke_plain(prompt: str, *, model: str | None = None) -> str:
    """调用 LLM 返回纯文本（用于代码自愈等）。"""
    llm = get_chat_model(model=model)
    msg = llm.invoke([HumanMessage(content=prompt)])
    return msg.content if hasattr(msg, "content") else str(msg)


def invoke_vision_plain(
    prompt: str,
    image_base64: str,
    mime_type: str = "image/jpeg",
    *,
    model: str | None = None,
) -> str:
    """调用支持视觉的 LLM，传入图片（base64）与提示，返回纯文本。用于从题目图片识别文字。"""
    llm = get_chat_model(model=model)
    url = f"data:{mime_type};base64,{image_base64}"
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": url}},
    ]
    msg = llm.invoke([HumanMessage(content=content)])
    return msg.content if hasattr(msg, "content") else str(msg)
