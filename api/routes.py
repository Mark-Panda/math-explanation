"""FastAPI 路由：POST /generate_video，GET /tasks/{task_id}，结果视频静态或下载。"""
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from api.models import GenerateVideoRequest, GenerateVideoResponse, TaskStatusResponse
from api.pipeline import run_pipeline
from api.task_store import create_task, get_task, set_failed, set_progress, set_running, set_success
from problem_analysis.formula_verifier import verify_and_fix_formulas
from problem_analysis.image_to_text import extract_problem_text_from_image, image_to_base64

logger = logging.getLogger(__name__)
router = APIRouter()

# 允许的题目图片类型
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# 生成结果存放目录（与 main 中挂载的 results 目录一致）
RESULTS_DIR = Path(__file__).resolve().parent.parent / "output" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _run_pipeline_task(
    task_id: str,
    problem_text: str | None,
    image_bytes: bytes | None = None,
    image_mime_type: str = "image/jpeg",
) -> None:
    """后台执行：若有图片则先识别题目 → 公式验证 → 带原图跑流水线。"""
    output_dir = Path(__file__).resolve().parent.parent / "output" / task_id
    logger.info("[generate_video] 后台任务开始 task_id=%s 有图片=%s", task_id, bool(image_bytes))

    # 原图 base64（贯穿流水线，让后续 LLM 调用都能看到原图）
    img_b64: str | None = None

    try:
        set_running(task_id)

        # ---------- 有图片：OCR → 公式验证 → 保留 base64 ----------
        if image_bytes:
            img_b64 = image_to_base64(image_bytes)

            set_progress(task_id, "识别题目图片")
            logger.info("[generate_video] task_id=%s 正在识别题目图片…", task_id)
            try:
                problem_text = extract_problem_text_from_image(image_bytes, mime_type=image_mime_type)
                logger.info("[generate_video] task_id=%s 图片识别完成 题目长度=%d", task_id, len(problem_text or ""))
            except Exception as e:
                logger.exception("[generate_video] task_id=%s 图片识别失败: %s", task_id, e)
                set_failed(task_id, f"图片识别失败: {e}")
                return

            if not (problem_text or "").strip():
                logger.warning("[generate_video] task_id=%s 图片未识别出文字", task_id)
                set_failed(task_id, "未能从图片中识别出题目文字")
                return

            # ---------- 公式交叉验证（P2）：用原图校正 OCR 文本 ----------
            set_progress(task_id, "公式交叉验证")
            logger.info("[generate_video] task_id=%s 开始公式交叉验证", task_id)
            try:
                problem_text = verify_and_fix_formulas(
                    problem_text,
                    image_base64=img_b64,
                    image_mime_type=image_mime_type,
                )
                logger.info("[generate_video] task_id=%s 公式验证完成 验证后长度=%d", task_id, len(problem_text or ""))
            except Exception as e:
                logger.warning("[generate_video] task_id=%s 公式验证失败（不阻塞）: %s", task_id, e)
                # 验证失败不阻塞流水线，继续使用 OCR 原始文本

        if not (problem_text or "").strip():
            set_failed(task_id, "题目为空")
            return
        logger.info("[generate_video] task_id=%s 开始执行流水线 题目前50字=%s", task_id, (problem_text or "")[:50])

        def on_step_start(step_index: int, step_name: str) -> None:
            set_progress(task_id, step_name)

        # ---------- 执行流水线（传入原图 base64） ----------
        video_path = run_pipeline(
            problem_text.strip(),
            output_dir,
            image_base64=img_b64,
            image_mime_type=image_mime_type,
            on_step_start=on_step_start,
        )
        result_path = RESULTS_DIR / f"{task_id}.mp4"
        import shutil
        shutil.copy(str(video_path), str(result_path))
        set_success(task_id, f"/results/{task_id}.mp4")
        logger.info("[generate_video] task_id=%s 生成成功 path=%s", task_id, result_path)
    except Exception as e:
        logger.exception("[generate_video] task_id=%s 生成失败: %s", task_id, e)
        set_failed(task_id, str(e))


def _normalize_problem(problem: str | None) -> str | None:
    return (problem or "").strip() or None


@router.post("/generate_video", response_model=GenerateVideoResponse)
async def generate_video(
    background_tasks: BackgroundTasks,
    problem: str | None = Form(None, description="题目文本，与图片二选一或同时提供（有图片时以识别结果为准）"),
    image: UploadFile | None = File(None, description="题目图片，将使用视觉模型识别题目文字"),
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

    task_id = create_task()
    logger.info("[generate_video] 收到请求 task_id=%s 有文字=%s 有图片=%s", task_id, bool(problem_text), bool(image_bytes))
    background_tasks.add_task(_run_pipeline_task, task_id, problem_text, image_bytes, image_mime_type)
    return GenerateVideoResponse(task_id=task_id, status="pending")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        video_url=task.video_path if task.status == "success" else None,
        error=task.error,
        current_step=task.current_step,
    )
