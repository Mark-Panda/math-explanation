@echo off
REM 数学讲解视频流水线 - 启动脚本 (Windows)
REM 使用前请先执行: uv sync

cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo 未检测到 uv，请先安装: https://docs.astral.sh/uv/
  exit /b 1
)

uv sync

set HOST=0.0.0.0
if not "%HOST%"=="" set HOST=%HOST%
set PORT=8000
if not "%PORT%"=="" set PORT=%PORT%

echo 启动服务: http://%HOST%:%PORT%
echo 按 Ctrl+C 停止
uv run uvicorn main:app --reload --host %HOST% --port %PORT%
