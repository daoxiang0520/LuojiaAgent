#!/bin/bash
# LuojiaAgent 一键安装
set -e

echo "=== LuojiaAgent 安装 ==="

# Python 依赖
pip install -r requirements.txt

# Playwright 浏览器
python -m playwright install chromium

# 配置 API Key
if [ ! -f api.key ]; then
    read -p "输入 DeepSeek API Key: " key
    echo "$key" > api.key
fi

echo "=== 完成！启动: streamlit run app.py ==="
