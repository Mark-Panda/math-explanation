"""可选 SD 概念图生成：占位实现，未启用时不报错。"""
from pathlib import Path


def generate_concept_image(prompt: str, filename: str | Path) -> None:
    """
    占位：若未启用 Stable Diffusion，则不调用 SD、不写入文件，不报错。
    后续可在此处接入 SD API；启用与否可由配置控制。
    """
    # 当前不实现 SD 调用；可选：写入占位说明文件或直接 return
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 不写入任何内容，避免覆盖；调用方可通过文件是否存在判断是否启用 SD
    return
