"""历史记录持久化：SQLite 存储任务与生成记录，支持列表、删除、按 task_id 查询。"""
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# 数据库文件放在项目 data 目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "history.db"

# 预览最大长度
PREVIEW_MAX = 120


@dataclass
class HistoryRecord:
    task_id: str
    problem_text: Optional[str]
    problem_preview: str
    status: str  # pending | running | success | failed
    video_path: Optional[str] = None
    error: Optional[str] = None
    current_step: Optional[str] = None  # 当前执行步骤，供断点重试时前端展示
    output_format: str = "html"  # html | video，供断点重试时选择流水线
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total_duration_ms: Optional[int] = None
    step_durations_json: Optional[str] = None
    checkpoint_html_step: Optional[int] = None
    checkpoint_tutor_step: Optional[int] = None
    checkpoint_updated_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """创建表结构（幂等）。"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                task_id TEXT PRIMARY KEY,
                problem_text TEXT,
                problem_preview TEXT NOT NULL,
                status TEXT NOT NULL,
                video_path TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_history_created_at ON history(created_at DESC)"
        )
        # LLM 响应缓存
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # 兼容旧库：若无 current_step 列则添加
        cur = conn.execute("PRAGMA table_info(history)")
        columns = [row[1] for row in cur.fetchall()]
        if "current_step" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN current_step TEXT")
        if "output_format" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN output_format TEXT DEFAULT 'html'")
        if "started_at" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN started_at TEXT")
        if "finished_at" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN finished_at TEXT")
        if "total_duration_ms" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN total_duration_ms INTEGER")
        if "step_durations_json" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN step_durations_json TEXT")
        if "checkpoint_html_step" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN checkpoint_html_step INTEGER")
        if "checkpoint_tutor_step" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN checkpoint_tutor_step INTEGER")
        if "checkpoint_updated_at" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN checkpoint_updated_at TEXT")
        conn.commit()
    finally:
        conn.close()


def _row_to_record(row: sqlite3.Row) -> HistoryRecord:
    return HistoryRecord(
        task_id=row["task_id"],
        problem_text=row["problem_text"],
        problem_preview=row["problem_preview"] or "",
        status=row["status"],
        video_path=row["video_path"],
        error=row["error"],
        current_step=row["current_step"] if "current_step" in row.keys() else None,
        output_format=row["output_format"] if "output_format" in row.keys() else "html",
        started_at=row["started_at"] if "started_at" in row.keys() else None,
        finished_at=row["finished_at"] if "finished_at" in row.keys() else None,
        total_duration_ms=row["total_duration_ms"] if "total_duration_ms" in row.keys() else None,
        step_durations_json=row["step_durations_json"] if "step_durations_json" in row.keys() else None,
        checkpoint_html_step=row["checkpoint_html_step"] if "checkpoint_html_step" in row.keys() else None,
        checkpoint_tutor_step=row["checkpoint_tutor_step"] if "checkpoint_tutor_step" in row.keys() else None,
        checkpoint_updated_at=row["checkpoint_updated_at"] if "checkpoint_updated_at" in row.keys() else None,
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def create_record(
    task_id: str,
    problem_preview: str = "",
    problem_text: Optional[str] = None,
    output_format: str = "html",
) -> None:
    """创建一条待处理历史记录。"""
    init_db()
    now = _now_iso()
    preview = (problem_preview or "").strip()[:PREVIEW_MAX] or (
        (problem_text or "").strip()[:PREVIEW_MAX] if problem_text else "[图片上传]"
    )
    fmt = "video" if (output_format or "").strip() == "video" else "html"
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO history (task_id, problem_text, problem_preview, status, video_path, error, output_format, created_at, updated_at, started_at, finished_at, total_duration_ms, step_durations_json, checkpoint_html_step, checkpoint_tutor_step, checkpoint_updated_at)
            VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
            """,
            (task_id, problem_text, preview, fmt, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def update_problem(task_id: str, problem_text: str) -> None:
    """更新题目文本（如 OCR 完成后）。"""
    now = _now_iso()
    preview = (problem_text or "")[:PREVIEW_MAX]
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE history SET problem_text = ?, problem_preview = ?, updated_at = ? WHERE task_id = ?",
            (problem_text, preview, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_status(
    task_id: str,
    status: str,
    video_path: Optional[str] = None,
    error: Optional[str] = None,
    *,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    total_duration_ms: Optional[int] = None,
    step_durations_json: Optional[str] = None,
) -> None:
    """更新任务状态与结果；同时清空 current_step，避免展示旧进度。"""
    now = _now_iso()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE history SET status = ?, video_path = ?, error = ?, current_step = NULL, started_at = COALESCE(?, started_at), finished_at = COALESCE(?, finished_at), total_duration_ms = COALESCE(?, total_duration_ms), step_durations_json = COALESCE(?, step_durations_json), updated_at = ? WHERE task_id = ?",
            (status, video_path, error, started_at, finished_at, total_duration_ms, step_durations_json, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_progress(task_id: str, current_step: str, *, started_at: Optional[str] = None) -> None:
    """仅更新当前步骤（用于运行中任务的进度展示，断点重试时前端可正确显示）。"""
    now = _now_iso()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE history SET current_step = ?, started_at = COALESCE(?, started_at), updated_at = ? WHERE task_id = ?",
            (current_step, started_at, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_checkpoint(
    task_id: str,
    *,
    html_step: Optional[int] = None,
    tutor_step: Optional[int] = None,
) -> None:
    """更新断点元数据（HTML 或 Tutor 流水线）。传入 -1 表示清空该类型断点。"""
    now = _now_iso()
    conn = _get_conn()
    html_value = None if html_step == -1 else html_step
    tutor_value = None if tutor_step == -1 else tutor_step
    try:
        conn.execute(
            "UPDATE history SET checkpoint_html_step = COALESCE(?, checkpoint_html_step), checkpoint_tutor_step = COALESCE(?, checkpoint_tutor_step), checkpoint_updated_at = ? WHERE task_id = ?",
            (html_value, tutor_value, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear_checkpoint_meta(task_id: str) -> None:
    """清理断点元数据。"""
    now = _now_iso()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE history SET checkpoint_html_step = NULL, checkpoint_tutor_step = NULL, checkpoint_updated_at = NULL, updated_at = ? WHERE task_id = ?",
            (now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_record(task_id: str) -> Optional[HistoryRecord]:
    """按 task_id 查询一条记录。"""
    conn = _get_conn()
    try:
        init_db()
        row = conn.execute("SELECT * FROM history WHERE task_id = ?", (task_id,)).fetchone()
        return _row_to_record(row) if row else None
    finally:
        conn.close()


def list_history(limit: int = 50, offset: int = 0) -> list[HistoryRecord]:
    """按创建时间倒序分页查询。"""
    conn = _get_conn()
    try:
        init_db()
        rows = conn.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


def get_llm_cache(cache_key: str) -> Optional[str]:
    """读取 LLM 缓存内容，未命中返回 None。"""
    conn = _get_conn()
    try:
        init_db()
        row = conn.execute(
            "SELECT response FROM llm_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_llm_cache(cache_key: str, response: str) -> None:
    """写入 LLM 缓存内容。"""
    conn = _get_conn()
    try:
        init_db()
        now = _now_iso()
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, response, created_at) VALUES (?, ?, ?)",
            (cache_key, response, now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_record(task_id: str) -> bool:
    """删除一条记录，返回是否删除成功。"""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM history WHERE task_id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
