"""基于 LangChain 的可复用 LLM 调用，供题目分析、脚本生成、代码自愈共用。文字与图片题目统一走多模态大模型，仅请求时区分 content 类型。"""
import json
import logging
import re
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


def _extract_json_from_text(text: str) -> str:
    """
    从 LLM 返回的文本中提取 JSON 字符串。

    某些模型（如通过兼容网关调用的 Claude）不支持原生 structured output，
    会返回 Markdown 代码块包裹的 JSON。本函数尝试：
    1. 提取 ```json ... ``` 或 ``` ... ``` 中的内容
    2. 若无代码块，尝试找到第一个 { 和最后一个 } 之间的内容
    3. 都失败则返回原文本（交给调用方报错）
    """
    # 尝试匹配 ```json ... ``` 或 ``` ... ```
    pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 尝试找到最外层 JSON 对象
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        # 简单验证是否为合法 JSON
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return text


def _invoke_and_parse(
    llm: BaseChatModel,
    content: str | list,
    schema: type[T],
) -> T:
    """
    普通调用 LLM 并手动提取 JSON 解析为 Pydantic 模型。

    在 prompt 末尾追加 JSON 格式约束，引导模型直接返回 JSON；
    即便模型返回 Markdown 代码块包裹的 JSON，也能通过 _extract_json_from_text 提取。

    不使用 with_structured_output，因为当前网关不支持 OpenAI 原生 response_format。
    """
    json_hint = (
        "\n\n**重要：请只输出纯 JSON，不要包含 Markdown 代码块（```）、注释或任何其他文字。**"
        f"\nJSON Schema: {json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )
    if isinstance(content, list):
        # 多模态：在 text 部分追加提示
        patched_content = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                patched_content.append({**item, "text": item["text"] + json_hint})
            else:
                patched_content.append(item)
        msg = llm.invoke([HumanMessage(content=patched_content)])
    else:
        msg = llm.invoke([HumanMessage(content=content + json_hint)])

    raw_content = msg.content if hasattr(msg, "content") else str(msg)
    logger.info("[LLM] 调用完成, raw_len=%d", len(raw_content))
    logger.debug("[LLM] raw response: %s", _truncate_for_log(raw_content))

    # 提取 JSON 并解析
    extracted = _extract_json_from_text(raw_content)
    logger.info("[LLM] 提取 JSON, extracted_len=%d", len(extracted))
    return schema.model_validate_json(extracted)


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
    result = _invoke_and_parse(llm, prompt, schema)
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


def invoke_multimodal_structured(
    prompt: str,
    schema: type[T],
    *,
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    model: str | None = None,
    timeout: float | None = None,
) -> T:
    """
    多模态结构化输出：同时传入文本提示与可选图片，返回 Pydantic 模型。
    当 image_base64 不为空时，content 为 [text, image_url]；否则退化为纯文本结构化调用。

    若模型不支持原生 structured output（如通过 OpenAI 兼容网关调用的 Claude），
    会自动降级为普通调用 + 手动 JSON 提取。
    """
    logger.info(
        "[LLM] invoke_multimodal_structured 请求 schema=%s prompt_len=%d has_image=%s",
        schema.__name__, len(prompt), bool(image_base64),
    )
    logger.info("[LLM] prompt: %s", _truncate_for_log(prompt))
    llm = get_chat_model(model=model, timeout=timeout)
    if image_base64:
        url = f"data:{image_mime_type};base64,{image_base64}"
        content: str | list = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]
    else:
        content = prompt
    result = _invoke_and_parse(llm, content, schema)
    out_str = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
    logger.info("[LLM] invoke_multimodal_structured 响应 schema=%s response_len=%d", schema.__name__, len(out_str))
    logger.info("[LLM] response: %s", _truncate_for_log(out_str))
    return result
