"""流水线检查点：按步骤持久化中间结果，支持失败后从断点重试。"""
import json
import logging
from pathlib import Path
from typing import Any

from problem_analysis.schemas import StepItem
from script_generation.schemas import ScriptGenerationOutput

logger = logging.getLogger(__name__)

CHECKPOINT_DIR_NAME = ".checkpoint"
MANIFEST_FILE = "manifest.json"
STEP_0_FILE = "step_0_steps.json"
STEP_1_FILE = "step_1_script.json"
STEP_2_FILE = "step_2_durations.json"


def _checkpoint_dir(work_dir: Path) -> Path:
    return work_dir / CHECKPOINT_DIR_NAME


def get_last_completed_step(work_dir: Path) -> int:
    """返回已完成的最后一步索引 (0..3)，无检查点或损坏时返回 -1。"""
    cp_dir = _checkpoint_dir(work_dir)
    manifest_path = cp_dir / MANIFEST_FILE
    if not manifest_path.is_file():
        return -1
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        step = int(data.get("last_completed_step", -1))
        return step if -1 <= step <= 3 else -1
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("[checkpoint] 读取 manifest 失败: %s", e)
        return -1


def load_checkpoint(
    work_dir: Path,
) -> tuple[int, list[StepItem] | None, ScriptGenerationOutput | None, list[float] | None]:
    """
    加载检查点数据。
    :return: (last_completed_step, steps, script_out, durations)
     若某步未持久化则对应为 None；last_completed_step 为 -1 表示无有效检查点。
    """
    work_dir = Path(work_dir)
    last = get_last_completed_step(work_dir)
    if last < 0:
        return -1, None, None, None

    cp_dir = _checkpoint_dir(work_dir)
    steps: list[StepItem] | None = None
    script_out: ScriptGenerationOutput | None = None
    durations: list[float] | None = None

    if last >= 0:
        p0 = cp_dir / STEP_0_FILE
        if p0.is_file():
            try:
                raw = json.loads(p0.read_text(encoding="utf-8"))
                steps = [StepItem.model_validate(x) for x in raw]
            except (json.JSONDecodeError, OSError, ValueError) as e:
                logger.warning("[checkpoint] 加载 step_0 失败: %s", e)
                return -1, None, None, None

    if last >= 1:
        p1 = cp_dir / STEP_1_FILE
        if p1.is_file():
            try:
                raw = json.loads(p1.read_text(encoding="utf-8"))
                script_out = ScriptGenerationOutput.model_validate(raw)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                logger.warning("[checkpoint] 加载 step_1 失败: %s", e)
                return -1, None, None, None

    if last >= 2:
        p2 = cp_dir / STEP_2_FILE
        if p2.is_file():
            try:
                raw = json.loads(p2.read_text(encoding="utf-8"))
                durations = [float(x) for x in raw]
            except (json.JSONDecodeError, OSError, ValueError, TypeError) as e:
                logger.warning("[checkpoint] 加载 step_2 失败: %s", e)
                return -1, None, None, None

    return last, steps, script_out, durations


def save_step_checkpoint(
    work_dir: Path,
    step_index: int,
    payload: Any,
) -> None:
    """
    保存指定步骤的检查点并更新 manifest。
    step_index: 0=steps, 1=script, 2=durations；3 仅更新 manifest（无额外 JSON）。
    """
    work_dir = Path(work_dir)
    cp_dir = _checkpoint_dir(work_dir)
    cp_dir.mkdir(parents=True, exist_ok=True)

    if step_index == 0 and payload is not None:
        steps: list[StepItem] = payload
        raw = [s.model_dump() for s in steps]
        (cp_dir / STEP_0_FILE).write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    elif step_index == 1 and payload is not None:
        script: ScriptGenerationOutput = payload
        (cp_dir / STEP_1_FILE).write_text(
            script.model_dump_json(indent=2),
            encoding="utf-8",
        )
    elif step_index == 2 and payload is not None:
        durations: list[float] = payload
        (cp_dir / STEP_2_FILE).write_text(json.dumps(durations), encoding="utf-8")

    manifest = {"last_completed_step": step_index}
    (cp_dir / MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    logger.info("[checkpoint] 已保存步骤 %d 检查点", step_index)


def clear_checkpoint(work_dir: Path) -> None:
    """删除检查点目录（成功跑完全流程后可调用，或由调用方在「强制从头运行」时调用）。"""
    cp_dir = _checkpoint_dir(Path(work_dir))
    if cp_dir.exists():
        import shutil
        shutil.rmtree(cp_dir, ignore_errors=True)
        logger.info("[checkpoint] 已清除检查点目录")
