#!/usr/bin/env bash
# 数学讲解视频流水线 - 启动脚本
# 使用前请先执行: uv sync

set -e
cd "$(dirname "$0")"

if ! command -v uv &>/dev/null; then
  echo "未检测到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# 若无虚拟环境或依赖缺失则同步
uv sync

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "启动服务: http://${HOST}:${PORT}"
echo "按 Ctrl+C 停止"
exec uv run uvicorn main:app --reload --host "$HOST" --port "$PORT"
