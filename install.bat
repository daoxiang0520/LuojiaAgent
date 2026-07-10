@echo off
echo ========================================
echo   LuojiaAgent 一键安装
echo ========================================
echo.

echo [1/3] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 安装失败，请检查 Python 和 pip 是否正确安装
    pause
    exit /b 1
)

echo.
echo [2/3] 安装 Playwright 浏览器...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo Playwright 浏览器安装失败
    pause
    exit /b 1
)

echo.
echo [3/3] 配置 API Key...
if not exist api.key (
    echo 请输入 DeepSeek API Key:
    set /p apikey=
    echo !apikey! > api.key
    echo API Key 已保存到 api.key
) else (
    echo api.key 已存在，跳过
)

echo.
echo ========================================
echo   安装完成！
echo   运行: streamlit run app.py
echo ========================================
pause
