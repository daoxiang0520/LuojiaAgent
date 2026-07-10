FROM python:3.12-slim

WORKDIR /app

# 系统依赖 + Playwright 浏览器
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates fonts-noto-cjk \
    libgl1 libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 浏览器
RUN python -m playwright install chromium
RUN python -m playwright install-deps chromium

# 项目代码
COPY . .

# API key 通过环境变量注入
ENV DEEPSEEK_API_KEY=""

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
