"""从题目图片中识别并提取文字（调用视觉大模型）。"""
import base64

from llm_runner import invoke_vision_plain

VISION_PROMPT = """请识别图片中的数学题目内容，只输出题目文字本身（可包含公式、数字、符号），不要解答、不要推理过程。若有多道题，逐题输出；若为手写或印刷不清晰，尽量准确辨认后输出。"""


def extract_problem_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    使用视觉大模型从图片中提取题目文字。
    :param image_bytes: 图片二进制内容
    :param mime_type: 如 image/jpeg, image/png
    :return: 识别出的题目文本，若失败或为空则抛出或返回空串
    """
    if not image_bytes or len(image_bytes) == 0:
        raise ValueError("图片内容为空")
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    text = invoke_vision_plain(VISION_PROMPT, b64, mime_type=mime_type)
    return (text or "").strip()