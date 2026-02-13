"""从题目图片中识别并提取文字。与文本题目相同，统一使用多模态大模型，仅请求时区分 content 为图片。"""
import base64

from llm_runner import invoke_multimodal_plain

VISION_PROMPT = """请识别图片中的数学题目内容，只输出题目文字本身（可包含公式、数字、符号），不要解答、不要推理过程。若有多道题，逐题输出；若为手写或印刷不清晰，尽量准确辨认后输出。"""


def extract_problem_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    使用多模态大模型从图片中提取题目文字（与文本题目同一模型，请求时 content 类型为 image）。
    :param image_bytes: 图片二进制内容
    :param mime_type: 如 image/jpeg, image/png
    :return: 识别出的题目文本，若失败或为空则抛出或返回空串
    """
    if not image_bytes or len(image_bytes) == 0:
        raise ValueError("图片内容为空")
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    text = invoke_multimodal_plain(
        VISION_PROMPT,
        content_type="image",
        image_base64=b64,
        image_mime_type=mime_type,
    )
    return (text or "").strip()