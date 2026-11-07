@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 课堂专注度分析系统

echo ==========================================================
echo    课堂专注度分析系统 启动程序
echo ==========================================================
echo.

if not exist ".venv\Scripts\python.exe" goto NO_VENV
set "PY=.venv\Scripts\python.exe"
echo [信息] 使用虚拟环境：%PY%
goto CHECK_DEPS

:NO_VENV
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON
echo [警告] 未找到 .venv 虚拟环境，改用系统 Python
set "PY=python"

:CHECK_DEPS
"%PY%" -c "import fastapi, ultralytics" >nul 2>nul
if errorlevel 1 goto NO_DEPS
echo [信息] 依赖检查通过

if not exist ".env" (
    echo [警告] 未找到 .env 配置文件
    echo [提示] 请复制 .env.example 为 .env 并填写数据库连接
    echo.
)

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo [信息] 正在启动服务，请稍候...
echo [信息] 服务地址： http://127.0.0.1:8000
echo [信息] 默认账号： admin / admin123
echo.

start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='http://127.0.0.1:8000/health'; for($i=0;$i -lt 60;$i++){ try{ $r=Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ Start-Process 'http://127.0.0.1:8000'; break } }catch{} Start-Sleep -Seconds 1 }"

"%PY%" main.py

echo.
echo [信息] 服务已停止。
echo.
pause
exit /b 0

:NO_PYTHON
echo.
echo [错误] 未检测到 Python，请先安装 Python 3.10 或以上版本
echo [提示] 安装时请勾选 Add Python to PATH
echo.
pause
exit /b 1

:NO_DEPS
echo.
echo [错误] 依赖未安装或不完整
echo [解决] 请执行： %PY% -m pip install -r requirements.txt
echo.
pause
exit /b 1
