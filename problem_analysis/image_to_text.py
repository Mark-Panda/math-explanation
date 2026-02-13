"""从题目图片中识别并提取文字、公式与图形描述。统一使用多模态大模型，仅请求时区分 content 为图片。"""
import base64

from llm_runner import invoke_multimodal_plain

VISION_PROMPT = """请仔细分析图片中的数学题目内容，按以下三部分输出：

1. 【题目文字】：完整输出题目的文字部分（包含公式、数字、符号）。公式请使用标准 LaTeX 格式，如 $x^2 + y^2 = r^2$、$\\frac{a}{b}$、$\\int_0^1 f(x)dx$。若题目包含选项，也一并输出。

2. 【图形描述】：如果图片中包含几何图形、函数图像、坐标系、示意图等，请详细描述：
   - 图形类型（三角形、圆、坐标系、函数图像等）
   - 各顶点/关键点的标注字母和位置关系
   - 已知的边长、角度、标注数值
   - 辅助线、虚线、阴影区域等特殊标记
   - 坐标轴的范围、刻度和关键坐标点（如有）
   - 图形之间的相对位置关系
   如果没有图形，输出"无"。

3. 【公式列表】：将识别出的每个独立公式单独列出，确保 LaTeX 语法正确，格式为：
   - 公式1: $...$
   - 公式2: $...$
   如果没有公式，输出"无"。

若有多道题，逐题按上述格式输出。若为手写或印刷不清晰，尽量准确辨认后输出。"""


def image_to_base64(image_bytes: bytes) -> str:
    """将图片二进制内容转为 base64 字符串。"""
    if not image_bytes or len(image_bytes) == 0:
        raise ValueError("图片内容为空")
    return base64.standard_b64encode(image_bytes).decode("ascii")


def extract_problem_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    使用多模态大模型从图片中提取题目文字、公式与图形描述。
    :param image_bytes: 图片二进制内容
    :param mime_type: 如 image/jpeg, image/png
    :return: 识别出的结构化题目文本（含图形描述），若失败或为空则抛出或返回空串
    """
    b64 = image_to_base64(image_bytes)
    text = invoke_multimodal_plain(
        VISION_PROMPT,
        content_type="image",
        image_base64=b64,
        image_mime_type=mime_type,
    )
    return (text or "").strip()