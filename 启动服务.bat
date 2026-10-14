@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ==========================================================
echo   基于 Python Web 的课堂专注度分析系统
echo ==========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo 使用解释器：%PY%
echo 服务地址：http://127.0.0.1:8000
echo 默认账号：admin / admin123
echo 按 Ctrl+C 可停止服务
echo.

%PY% main.py

echo.
echo 服务已停止。
pause
