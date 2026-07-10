@echo off
:: 强制控制台使用 UTF-8 编码，防止中文乱码
chcp 65001 >nul
title LuojiaAgent 智慧校园助手 启动器

echo ============================================================
echo      🏫 LuojiaAgent 智慧校园助手 启动服务
echo ============================================================
echo 正在检测本地运行环境，请稍候...

:: 1. 获取当前批处理文件所在的绝对路径（实现完美的相对路径定位）
set "CURRENT_DIR=%~dp0"
cd /d "%CURRENT_DIR%"

:: 2. 自动检测本地是否存在虚拟环境 (.venv 或 venv)
if exist "%CURRENT_DIR%.venv\Scripts\python.exe" (
    echo [✔] 检测到本地虚拟环境 .venv，正在启动...
    set "PYTHON_EXE=%CURRENT_DIR%.venv\Scripts\python.exe"
) else if exist "%CURRENT_DIR%venv\Scripts\python.exe" (
    echo [✔] 检测到本地虚拟环境 venv，正在启动...
    set "PYTHON_EXE=%CURRENT_DIR%venv\Scripts\python.exe"
) else (
    echo [!] 未检测到本地虚拟环境，将尝试调用系统全局 Python...
    set "PYTHON_EXE=python"
)
echo 正在为您在后台启动 Web 页面，请观察默认浏览器弹窗...
echo ===========================================================
:: 3. 相对路径启动 Streamlit
"%PYTHON_EXE%" -m streamlit run app.py
if %errorlevel% neq 0 (
    echo [❌] 启动失败！请确保您已安装 streamlit 库。
    pause
)