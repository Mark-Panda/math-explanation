"""Tutor 流水线检查点：步骤 0..6 持久化，支持断点重试。"""
import json
import logging
from pathlib import Path

from api.history_store import update_checkpoint
from tutor_pipeline.schemas import AudioInfo

logger = logging.getLogger(__name__)

TUTOR_CP_DIR = ".tutor_checkpoint"
MANIFEST = "manifest.json"
STEP_0_MATH = "step_0_math_analysis.txt"
STEP_1_HTML = "step_1_html.txt"
STEP_2_STORYBOARD = "step_2_storyboard.txt"
STEP_3_AUDIO_INFO = "step_3_audio_info.json"
STEP_4_SCAFFOLD = "step_4_scaffold.txt"
STEP_5_SCRIPT = "step_5_script.txt"


def _cp_dir(work_dir: Path) -> Path:
    return Path(work_dir) / TUTOR_CP_DIR


def get_last_completed_tutor_step(work_dir: Path) -> int:
    """返回已完成的最后一步索引 (0..5)，无检查点或损坏时返回 -1。"""
    cp = _cp_dir(work_dir)
    m = cp / MANIFEST
    if not m.is_file():
        return -1
    try:
        d = json.loads(m.read_text(encoding="utf-8"))
        s = int(d.get("last_completed_step", -1))
        return s if -1 <= s <= 5 else -1
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("[tutor_checkpoint] 读取 manifest 失败: %s", e)
        return -1


def load_tutor_checkpoint(work_dir: Path) -> tuple[int, str | None, str | None, str | None, AudioInfo | None, str | None, str | None]:
    """
    加载 Tutor 检查点。
    :return: (last_completed_step, math_analysis, html_content, storyboard_md, audio_info, scaffold_code, full_script)
    """
    work_dir = Path(work_dir)
    last = get_last_completed_tutor_step(work_dir)
    if last < 0:
        return -1, None, None, None, None, None, None

    cp = _cp_dir(work_dir)
    math_analysis, html_content, storyboard_md = None, None, None
    audio_info: AudioInfo | None = None
    scaffold_code, full_script = None, None

    if last >= 0 and (cp / STEP_0_MATH).is_file():
        math_analysis = (cp / STEP_0_MATH).read_text(encoding="utf-8")
    if last >= 1 and (cp / STEP_1_HTML).is_file():
        html_content = (cp / STEP_1_HTML).read_text(encoding="utf-8")
    if last >= 2 and (cp / STEP_2_STORYBOARD).is_file():
        storyboard_md = (cp / STEP_2_STORYBOARD).read_text(encoding="utf-8")
    if last >= 3 and (cp / STEP_3_AUDIO_INFO).is_file():
        try:
            audio_info = AudioInfo.model_validate_json((cp / STEP_3_AUDIO_INFO).read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[tutor_checkpoint] 加载 step_3 失败: %s", e)
            return -1, None, None, None, None, None, None
    if last >= 4 and (cp / STEP_4_SCAFFOLD).is_file():
        scaffold_code = (cp / STEP_4_SCAFFOLD).read_text(encoding="utf-8")
    if last >= 5 and (cp / STEP_5_SCRIPT).is_file():
        full_script = (cp / STEP_5_SCRIPT).read_text(encoding="utf-8")

    return last, math_analysis, html_content, storyboard_md, audio_info, scaffold_code, full_script


def save_tutor_step(
    work_dir: Path,
    step_index: int,
    *,
    math_analysis: str | None = None,
    html_content: str | None = None,
    storyboard_md: str | None = None,
    audio_info: AudioInfo | None = None,
    scaffold_code: str | None = None,
    full_script: str | None = None,
) -> None:
    """保存指定步骤的检查点并更新 manifest。"""
    work_dir = Path(work_dir)
    cp = _cp_dir(work_dir)
    cp.mkdir(parents=True, exist_ok=True)

    if step_index == 0 and math_analysis is not None:
        (cp / STEP_0_MATH).write_text(math_analysis, encoding="utf-8")
    elif step_index == 1 and html_content is not None:
        (cp / STEP_1_HTML).write_text(html_content, encoding="utf-8")
    elif step_index == 2 and storyboard_md is not None:
        (cp / STEP_2_STORYBOARD).write_text(storyboard_md, encoding="utf-8")
    elif step_index == 3 and audio_info is not None:
        (cp / STEP_3_AUDIO_INFO).write_text(audio_info.model_dump_json(indent=2), encoding="utf-8")
    elif step_index == 4 and scaffold_code is not None:
        (cp / STEP_4_SCAFFOLD).write_text(scaffold_code, encoding="utf-8")
    elif step_index == 5 and full_script is not None:
        (cp / STEP_5_SCRIPT).write_text(full_script, encoding="utf-8")

    (cp / MANIFEST).write_text(json.dumps({"last_completed_step": step_index}, ensure_ascii=False), encoding="utf-8")
    logger.info("[tutor_checkpoint] 已保存 Tutor 步骤 %d", step_index)

    task_id = work_dir.parent.name
    update_checkpoint(task_id, tutor_step=step_index)


def clear_tutor_checkpoint(work_dir: Path) -> None:
    """删除 Tutor 检查点目录。"""
    cp = _cp_dir(Path(work_dir))
    if cp.exists():
        import shutil
        shutil.rmtree(cp, ignore_errors=True)
        logger.info("[tutor_checkpoint] 已清除检查点目录")
    task_id = Path(work_dir).parent.name
    update_checkpoint(task_id, tutor_step=-1)
