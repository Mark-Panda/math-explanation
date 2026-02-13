"""FastAPI 应用入口：挂载 API、结果静态目录、Web 前端静态目录。"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.history_store import init_db as init_history_db
from api.routes import router, RESULTS_DIR

# 配置日志：便于查看 /api/generate_video 及流水线执行进度
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# 降低 uvicorn 访问日志噪音，业务日志仍为 INFO
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

app = FastAPI(title="数学讲解动画流水线", version="0.2.0")


@app.on_event("startup")
def startup():
    init_history_db()


app.include_router(router, prefix="/api", tags=["explainer"])

# 结果 HTML 动画通过 /results/{task_id}.html 访问
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")

# Web 界面：静态页面目录
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
