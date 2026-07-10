@echo off
title LuojiaAgent - Setup and Run

echo [+] Preparing local virtual environment...
python -m venv .venv

echo [+] Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [+] Installing required Python libraries...
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [+] Installing Playwright browser...
.venv\Scripts\python.exe -m playwright install chromium

echo [+] Launching Streamlit Web UI...
.venv\Scripts\python.exe -m streamlit run app.py

pause