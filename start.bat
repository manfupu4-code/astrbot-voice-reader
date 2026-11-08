@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] 首次运行，正在创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo 创建失败：请确认已安装 Python 3.9+ 并加入 PATH
        pause
        exit /b 1
    )
    echo [2/2] 安装依赖（约 1-2 分钟）...
    ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

echo 启动中...
".venv\Scripts\python.exe" -m voice_reader.main %*
pause
