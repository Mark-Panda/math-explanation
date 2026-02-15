"""FastAPI 路由：POST /generate_video，GET /tasks/{task_id}，结果 HTML 动画静态或下载。"""
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from api.models import (
    GenerateVideoResponse,
    HistoryItem,
    RegenerateRequest,
    RegenerateResponse,
    TaskStatusResponse,
)
from api.pipeline import run_pipeline
from api.task_store import (
    create_task,
    delete_task,
    get_task,
    set_failed,
    set_progress,
    set_running,
    set_success,
    update_task_problem,
)
from api.history_store import delete_record as history_delete, get_record as history_get, list_history
from problem_analysis.formula_verifier import verify_and_fix_formulas
from problem_analysis.image_to_text import extract_problem_text_from_image, image_to_base64

logger = logging.getLogger(__name__)
router = APIRouter()

# 允许的题目图片类型
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# 生成结果存放目录（与 main 中挂载的 results 目录一致）
RESULTS_DIR = Path(__file__).resolve().parent.parent / "output" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _run_pipeline_task_retry(task_id: str) -> None:
    """断点重试：仅用历史中的题目文本重新跑流水线，从检查点继续（不传图、不重新 OCR）。"""
    rec = history_get(task_id)
    if not rec:
        set_failed(task_id, "任务记录不存在")
        return
    problem_text = (rec.problem_text or "").strip()
    if not problem_text:
        set_failed(task_id, "无题目文本，无法断点重试")
        return
    output_dir = Path(__file__).resolve().parent.parent / "output" / task_id
    logger.info("[retry] 断点重试 task_id=%s", task_id)
    try:
        set_running(task_id)

        def on_step_start(step_index: int, step_name: str) -> None:
            set_progress(task_id, step_name)

        result_path = run_pipeline(
            problem_text,
            output_dir,
            image_base64=None,
            image_mime_type="image/jpeg",
            on_step_start=on_step_start,
            force_restart=False,
        )
        dest = RESULTS_DIR / f"{task_id}.html"
        import shutil
        shutil.copy(str(result_path), str(dest))
        set_success(task_id, f"/results/{task_id}.html")
        logger.info("[retry] task_id=%s 重试成功 path=%s", task_id, dest)
    except Exception as e:
        logger.exception("[retry] task_id=%s 重试失败: %s", task_id, e)
        set_failed(task_id, str(e))


def _run_pipeline_task(
    task_id: str,
    problem_text: str | None,
    image_bytes: bytes | None = None,
    image_mime_type: str = "image/jpeg",
    animation_style: str | None = None,
) -> None:
    """后台执行：若有图片则先识别题目 → 公式验证 → 带原图跑流水线。"""
    output_dir = Path(__file__).resolve().parent.parent / "output" / task_id
    logger.info("[generate] 后台任务开始 task_id=%s 有图片=%s", task_id, bool(image_bytes))

    # 原图 base64（贯穿流水线，让后续 LLM 调用都能看到原图）
    img_b64: str | None = None

    try:
        set_running(task_id)

        # ---------- 有图片：OCR → 公式验证 → 保留 base64 ----------
        if image_bytes:
            img_b64 = image_to_base64(image_bytes)

            set_progress(task_id, "识别题目图片")
            logger.info("[generate] task_id=%s 正在识别题目图片…", task_id)
            try:
                problem_text = extract_problem_text_from_image(image_bytes, mime_type=image_mime_type)
                logger.info("[generate] task_id=%s 图片识别完成 题目长度=%d", task_id, len(problem_text or ""))
            except Exception as e:
                logger.exception("[generate] task_id=%s 图片识别失败: %s", task_id, e)
                set_failed(task_id, f"图片识别失败: {e}")
                return

            if not (problem_text or "").strip():
                logger.warning("[generate] task_id=%s 图片未识别出文字", task_id)
                set_failed(task_id, "未能从图片中识别出题目文字")
                return

            # ---------- 公式交叉验证（P2）：用原图校正 OCR 文本 ----------
            set_progress(task_id, "公式交叉验证")
            logger.info("[generate] task_id=%s 开始公式交叉验证", task_id)
            try:
                problem_text = verify_and_fix_formulas(
                    problem_text,
                    image_base64=img_b64,
                    image_mime_type=image_mime_type,
                )
                logger.info("[generate] task_id=%s 公式验证完成 验证后长度=%d", task_id, len(problem_text or ""))
            except Exception as e:
                logger.warning("[generate] task_id=%s 公式验证失败（不阻塞）: %s", task_id, e)
                # 验证失败不阻塞流水线，继续使用 OCR 原始文本

        if not (problem_text or "").strip():
            set_failed(task_id, "题目为空")
            return
        # 持久化题目文本，便于历史列表展示与重新生成
        update_task_problem(task_id, problem_text.strip())
        logger.info("[generate] task_id=%s 开始执行流水线 题目前50字=%s", task_id, (problem_text or "")[:50])

        def on_step_start(step_index: int, step_name: str) -> None:
            set_progress(task_id, step_name)

        # ---------- 执行流水线（传入原图 base64、可选动画风格） ----------
        result_path = run_pipeline(
            problem_text.strip(),
            output_dir,
            image_base64=img_b64,
            image_mime_type=image_mime_type,
            on_step_start=on_step_start,
            animation_style=animation_style,
        )
        dest = RESULTS_DIR / f"{task_id}.html"
        import shutil
        shutil.copy(str(result_path), str(dest))
        set_success(task_id, f"/results/{task_id}.html")
        logger.info("[generate] task_id=%s 生成成功 path=%s", task_id, dest)
    except Exception as e:
        logger.exception("[generate] task_id=%s 生成失败: %s", task_id, e)
        set_failed(task_id, str(e))


def _normalize_problem(problem: str | None) -> str | None:
    return (problem or "").strip() or None


@router.post("/generate_video", response_model=GenerateVideoResponse)
async def generate_video(
    background_tasks: BackgroundTasks,
    problem: str | None = Form(None, description="题目文本，与图片二选一或同时提供（有图片时以识别结果为准）"),
    image: UploadFile | None = File(None, description="题目图片，将使用视觉模型识别题目文字"),
    animation_style: str | None = Form(None, description="可选，动画风格描述，会注入到生成 prompt 中；不填则使用环境变量 ANIMATION_STYLE"),
):
    """支持 multipart：仅文本、仅图片、或文本+图片。图片识别在后台执行，请求立即返回 task_id，避免 nginx 等代理超时。"""
    problem_text: str | None = _normalize_problem(problem)
    image_bytes: bytes | None = None
    image_mime_type: str = "image/jpeg"

    if image and image.filename:
        content_type = image.content_type or "image/jpeg"
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的图片类型，仅支持: {', '.join(ALLOWED_IMAGE_TYPES)}",
            )
        image_bytes = await image.read()
        image_mime_type = content_type
        if not image_bytes:
            raise HTTPException(status_code=400, detail="上传的图片为空")

    if not problem_text and not image_bytes:
        raise HTTPException(status_code=400, detail="请提供题目文本或上传题目图片")

    problem_preview = (problem_text or "").strip()[:120] if problem_text else "图片上传"
    task_id = create_task(problem_preview=problem_preview, problem_text=problem_text)
    logger.info("[generate] 收到请求 task_id=%s 有文字=%s 有图片=%s", task_id, bool(problem_text), bool(image_bytes))
    style = (animation_style or "").strip() or None
    background_tasks.add_task(_run_pipeline_task, task_id, problem_text, image_bytes, image_mime_type, style)
    return GenerateVideoResponse(task_id=task_id, status="pending")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        result_url=task.result_path if task.status == "success" else None,
        error=task.error,
        current_step=task.current_step,
    )


@router.post("/tasks/{task_id}/retry", response_model=GenerateVideoResponse)
async def retry_task(background_tasks: BackgroundTasks, task_id: str):
    """失败任务的断点重试：从上次中断的步骤继续，不重新执行已完成步骤。"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "failed":
        raise HTTPException(
            status_code=400,
            detail="仅支持对失败任务进行重试，当前状态: " + task.status,
        )
    rec = history_get(task_id)
    if not rec or not (rec.problem_text or "").strip():
        raise HTTPException(status_code=400, detail="该记录无题目文本，无法断点重试")
    set_running(task_id)  # 立即置为 running，避免前端首次轮询仍拿到 failed
    background_tasks.add_task(_run_pipeline_task_retry, task_id)
    return GenerateVideoResponse(task_id=task_id, status="running")


@router.get("/history", response_model=list[HistoryItem])
async def get_history(limit: int = 50, offset: int = 0):
    """分页获取历史记录，按创建时间倒序。"""
    records = list_history(limit=min(limit, 100), offset=max(0, offset))
    return [
        HistoryItem(
            task_id=r.task_id,
            problem_preview=r.problem_preview,
            status=r.status,
            result_path=r.video_path,
            error=r.error,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.delete("/history/{task_id}")
async def delete_history(task_id: str):
    """删除一条历史记录；若存在结果文件则一并删除。"""
    if not history_delete(task_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    delete_task(task_id)
    # 清理可能存在的旧格式 mp4 和新格式 html 文件
    for ext in (".html", ".mp4"):
        result_file = RESULTS_DIR / f"{task_id}{ext}"
        if result_file.exists():
            try:
                result_file.unlink()
            except OSError:
                pass
    return {"ok": True}


@router.post("/regenerate", response_model=RegenerateResponse)
async def regenerate(background_tasks: BackgroundTasks, body: RegenerateRequest):
    """根据历史任务 ID 使用其题目文本重新生成（仅文本，无原图）。"""
    rec = history_get(body.task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在")
    problem_text = (rec.problem_text or "").strip()
    if not problem_text:
        raise HTTPException(
            status_code=400,
            detail="该记录无题目文本（如仅图片上传且未保存），无法重新生成",
        )
    problem_preview = (problem_text or "")[:120]
    new_task_id = create_task(problem_preview=problem_preview, problem_text=problem_text)
    background_tasks.add_task(_run_pipeline_task, new_task_id, problem_text, None, "image/jpeg", None)
    return RegenerateResponse(task_id=new_task_id, status="pending")
