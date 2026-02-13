"""视频合成单测：缺失输入时抛出明确错误。"""
from pathlib import Path

import pytest

from composition.ffmpeg_compose import CompositionError, compose_video


def test_compose_video_missing_video_raises():
    with pytest.raises(CompositionError, match="视频文件不存在"):
        compose_video("/nonexistent/video.mp4", __file__, "/tmp/out.mp4")


def test_compose_video_missing_audio_raises():
    with pytest.raises(CompositionError, match="音频文件不存在"):
        compose_video(__file__, "/nonexistent/audio.mp3", "/tmp/out.mp4")
