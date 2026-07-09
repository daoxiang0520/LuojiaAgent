"""
Playwright 方案：让浏览器 TAC SDK 处理滑块验证码

思路：
1. Playwright 加载图书馆页面 (带有效 cookies + JWT)
2. 触发滑块验证码弹窗
3. 用 Playwright 模拟鼠标拖拽滑块
4. 让 TAC SDK 自动完成加密 + check 请求
5. 拦截 check 响应，提取 captcha token

相比纯 Python 方案的优势：
- TAC SDK 负责加密，100% 兼容
- 不需要 OpenCV 识别缺口（TAC SDK 处理一切）
- 不需要手动构造请求

使用方法:
    from tools.captcha_playwright import solve_captcha_with_browser
    result = solve_captcha_with_browser(raw_cookies, jwt_token, username)
"""

import time
import random
import re
import json
from playwright.sync_api import sync_playwright


def solve_captcha_with_browser(
    raw_cookies: list,
    jwt_token: str,
    username: str = "2025302114221",
    max_attempts: int = 5
) -> dict:
    """
    用 Playwright 浏览器自动完成滑块验证码。

    参数:
        raw_cookies: 登录后获取的 cookie 列表 (来自 login_helper)
        jwt_token: 图书馆 JWT 授权密钥
        username: 学号
        max_attempts: 最大尝试次数

    返回:
        {"success": True, "token": "captcha_token"}
        或 {"success": False, "error": "错误信息"}
    """

    captured_token = {"value": ""}

    def _intercept_check_response(response):
        """拦截 check 请求的响应，提取 token"""
        if "/cap/cg/check" in response.url and response.status == 200:
            try:
                body = response.json()
                if body.get("success"):
                    token = body.get("data", {}).get("token", "")
                    if token:
                        captured_token["value"] = token
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()

        # 拦截 check 响应
        page.on("response", _intercept_check_response)

        # 访问图书馆页面
        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={jwt_token}"
        page.goto(target_url, timeout=15000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        for attempt in range(max_attempts):
            print(f"[Attempt {attempt+1}/{max_attempts}]")

            # 1. 点击一个座位触发验证码弹窗
            try:
                # 先选择一个区域 (点击左侧导航的座位)
                page.evaluate("""
                    // 尝试找到第一个空闲座位
                    const seats = document.querySelectorAll('[class*="seat"]');
                    for (const seat of seats) {
                        if (seat.textContent && !seat.classList.contains('disabled')) {
                            seat.click();
                            break;
                        }
                    }
                """)
                time.sleep(1)
            except Exception:
                pass

            # 2. 检查验证码弹窗是否出现
            captcha_visible = page.evaluate("""
                () => {
                    const el = document.querySelector('#show-code-check-wrap');
                    return el && el.children.length > 0;
                }
            """)
            if not captcha_visible:
                print("  Captcha dialog not found, trying to trigger...")
                continue

            # 3. 读取 TAC 配置 (end=最大滑动距离)
            slider_config = page.evaluate("""
                () => {
                    // 尝试从 TAC SDK 获取配置
                    if (typeof TAC !== 'undefined') {
                        return { key: TAC.enc?.rsaPublicKey?.substring(0, 30) || 'N/A' };
                    }
                    return { error: 'TAC not found' };
                }
            """)
            print(f"  TAC config: {slider_config}")

            # 4. 模拟滑块拖拽
            # 尝试多个偏移量
            offsets_to_try = [120, 150, 180, 210, 240, 160, 200, 140, 220]
            for off_idx, target_x in enumerate(offsets_to_try):
                if captured_token["value"]:
                    break

                # 重新获取验证码（如果前一次失败了）
                if off_idx > 0:
                    # 点刷新按钮
                    try:
                        page.click("#tianai-captcha-slider-refresh-btn", timeout=2000)
                        time.sleep(0.5)
                    except Exception:
                        pass

                # 获取滑块按钮位置
                btn_box = page.evaluate("""
                    () => {
                        const btn = document.querySelector('#tianai-captcha-slider-move-btn');
                        if (!btn) return null;
                        const rect = btn.getBoundingClientRect();
                        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                    }
                """)
                if not btn_box:
                    continue

                start_x = btn_box["x"] + btn_box["width"] / 2
                start_y = btn_box["y"] + btn_box["height"] / 2

                print(f"  Trying offset={target_x}px...")

                # 模拟人类拖拽
                page.mouse.move(start_x, start_y)
                page.mouse.down()
                time.sleep(random.uniform(0.05, 0.15))

                cur = 0
                while cur < target_x:
                    step = random.randint(1, 5)
                    cur += step
                    page.mouse.move(
                        start_x + min(cur, target_x),
                        start_y + random.choice([-1, 0, 0, 1]),
                        steps=1
                    )
                    time.sleep(random.uniform(0.005, 0.015))

                time.sleep(random.uniform(0.1, 0.3))
                page.mouse.up()

                # 等待 check 请求完成
                time.sleep(2)

                if captured_token["value"]:
                    print(f"  SUCCESS at offset={target_x}px!")
                    browser.close()
                    return {
                        "success": True,
                        "token": captured_token["value"],
                        "offset": target_x
                    }

                # 检查是否验证失败
                failed = page.evaluate("""
                    () => {
                        const tips = document.querySelector('#tianai-captcha-tips');
                        return tips && tips.classList.contains('tianai-captcha-tips-error');
                    }
                """)
                if failed:
                    print(f"    Verification failed, captcha consumed")

            if captured_token["value"]:
                break

        browser.close()

    if captured_token["value"]:
        return {"success": True, "token": captured_token["value"]}
    return {"success": False, "error": "Failed to solve captcha after all attempts"}


if __name__ == "__main__":
    print("This module is designed to be imported from library_tool.py")
    print("It requires raw_cookies and jwt_token from login_helper")
