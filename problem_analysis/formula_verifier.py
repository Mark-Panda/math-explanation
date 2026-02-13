"""公式交叉验证：对比 OCR 提取文本与原图，修正公式识别错误。"""
import logging

from llm_runner import invoke_multimodal_plain

logger = logging.getLogger(__name__)

FORMULA_VERIFY_PROMPT = """请对比原始题目图片与以下从图片中识别出的文本内容，逐一验证并修正。

识别文本：
{extracted_text}

请重点检查：
1. **LaTeX 公式正确性**：所有公式的括号是否匹配、上下标是否完整、分式/根号/积分等复杂结构是否正确嵌套
2. **公式完整性**：是否有遗漏的公式或公式的一部分（与图片对比）
3. **数字和符号**：数字、运算符、等号、不等号等是否与图片一致
4. **图形描述准确性**：几何图形的标注字母、角度值、边长值是否与图片一致
5. **特殊符号**：希腊字母（α, β, θ 等）、集合符号、逻辑符号是否正确

如果发现错误，请直接修正后输出完整的正确文本（保持原有的三段结构：题目文字、图形描述、公式列表）。
如果全部正确，原样输出文本即可。
不要添加额外解释，只输出修正后的文本。"""


def verify_and_fix_formulas(
    extracted_text: str,
    image_base64: str,
    image_mime_type: str = "image/jpeg",
) -> str:
    """
    将 OCR 提取的文本与原图一起发给多模态 LLM，交叉验证并修正公式错误。
    :param extracted_text: OCR 提取的文本（含公式和图形描述）
    :param image_base64: 原始图片的 base64 编码
    :param image_mime_type: 图片 MIME 类型
    :return: 验证并修正后的文本
    """
    if not extracted_text or not extracted_text.strip():
        return extracted_text
    if not image_base64:
        logger.info("[formula_verifier] 无原图，跳过公式验证")
        return extracted_text

    logger.info("[formula_verifier] 开始公式交叉验证 text_len=%d", len(extracted_text))
    prompt = FORMULA_VERIFY_PROMPT.format(extracted_text=extracted_text)
    verified_text = invoke_multimodal_plain(
        prompt,
        content_type="image",
        image_base64=image_base64,
        image_mime_type=image_mime_type,
    )
    result = (verified_text or "").strip()
    if not result:
        logger.warning("[formula_verifier] 验证返回为空，保留原文本")
        return extracted_text
    logger.info("[formula_verifier] 公式验证完成 verified_len=%d", len(result))
    return result
