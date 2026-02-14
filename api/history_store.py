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
        # 兼容旧库：若无 current_step 列则添加
        cur = conn.execute("PRAGMA table_info(history)")
        columns = [row[1] for row in cur.fetchall()]
        if "current_step" not in columns:
            conn.execute("ALTER TABLE history ADD COLUMN current_step TEXT")
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
) -> None:
    """创建一条待处理历史记录。"""
    init_db()
    now = _now_iso()
    preview = (problem_preview or "").strip()[:PREVIEW_MAX] or (
        (problem_text or "").strip()[:PREVIEW_MAX] if problem_text else "[图片上传]"
    )
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO history (task_id, problem_text, problem_preview, status, video_path, error, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?)
            """,
            (task_id, problem_text, preview, now, now),
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
) -> None:
    """更新任务状态与结果；同时清空 current_step，避免展示旧进度。"""
    now = _now_iso()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE history SET status = ?, video_path = ?, error = ?, current_step = NULL, updated_at = ? WHERE task_id = ?",
            (status, video_path, error, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_progress(task_id: str, current_step: str) -> None:
    """仅更新当前步骤（用于运行中任务的进度展示，断点重试时前端可正确显示）。"""
    now = _now_iso()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE history SET current_step = ?, updated_at = ? WHERE task_id = ?",
            (current_step, now, task_id),
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


def delete_record(task_id: str) -> bool:
    """删除一条记录，返回是否删除成功。"""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM history WHERE task_id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
