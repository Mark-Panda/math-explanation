"""Tutor 流水线：audio_info.json 及分镜解析用到的数据结构。"""
from pydantic import BaseModel, Field


class AudioInfoEntry(BaseModel):
    """单条音频信息，与 audio_info.json 中 files[] 元素一致。"""
    scene: int = Field(..., description="幕号，从 1 开始")
    file: str = Field(..., description="文件名，如 audio_001_开场.wav")
    duration: float = Field(..., description="时长（秒）")


class AudioInfo(BaseModel):
    """audio_info.json 根结构。"""
    files: list[AudioInfoEntry] = Field(default_factory=list)
