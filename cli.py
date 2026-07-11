"""Entry point for LuojiaAgent — pip install . && luojia"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent


def _ensure_api_key():
    """Check if DeepSeek API key is configured; prompt if missing."""
    key_file = PROJECT_DIR / "api.key"

    # 1. api.key 文件存在且非空
    if key_file.exists():
        content = key_file.read_text().strip()
        if content:
            return content

    # 2. 环境变量
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key

    # 3. 交互式输入
    print("=" * 50)
    print("🔑 未检测到 DeepSeek API Key")
    print(f"   获取地址: https://platform.deepseek.com/api_keys")
    print()
    print("   配置方式（任选其一）:")
    print(f"   1. 现在输入 → 保存到 {key_file}")
    print(f"   2. Ctrl+C 退出 → 设置环境变量 export DEEPSEEK_API_KEY=...")
    print("=" * 50)

    try:
        key = input("API Key: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print("❌ 未配置 API Key，已取消启动。")
        print(f"   可通过环境变量设置: export DEEPSEEK_API_KEY=...")
        sys.exit(1)

    if not key:
        print("❌ 输入为空，已取消启动。")
        sys.exit(1)

    key_file.write_text(key)
    print(f"✅ 已保存到 {key_file}")
    return key


def _ensure_playwright():
    """Check if Playwright chromium works; auto-install if missing."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return
    except Exception:
        pass

    print("🔧 首次运行：安装 Playwright 浏览器 (~150 MB)...")
    subprocess.check_call(
        [sys.executable, "-m", "playwright", "install", "chromium"]
    )

    if sys.platform == "linux":
        print("🔧 安装 Playwright 系统依赖（可能需要 sudo）...")
        try:
            subprocess.check_call(
                ["sudo", sys.executable, "-m", "playwright", "install-deps", "chromium"],
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  系统依赖安装失败，请手动运行：")
            print("   sudo python -m playwright install-deps chromium")
            print("   或参考: https://playwright.dev/python/docs/intro")


def main():
    _ensure_api_key()
    _ensure_playwright()

    from streamlit.web import cli as stcli

    app_path = PROJECT_DIR / "app.py"
    sys.argv = ["streamlit", "run", str(app_path), *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
