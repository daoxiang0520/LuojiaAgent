# login_helper.py

import time
import re
from playwright.sync_api import sync_playwright
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from typing import Annotated


def interactive_whu_login() -> dict:
    """
    一键登录，多路静默并发收割。\n    流程：智慧珞珈登录 → 图书馆OAuth免密流转 → 直接访问jwgl获取教务Cookie。
    """
    print("\n" + "=" * 60)
    print("【双路凭证收割器】正在启动浏览器...")
    print(" 1. 请在弹出的窗口中手动扫码/密码登录【智慧珞珈】。")
    print(" 2. 登录成功后，程序将自动通过 OAuth 同步图书馆会话。")
    print(" 3. 程序会自动访问教务系统，收割 Cookie。")
    print(" 4. 运行结束时，控制台将高亮输出两套完整的 Cookie 串。")
    print("=" * 60 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # -------------------- 【步骤 1：登录智慧珞珈】 --------------------
        login_url = "https://cas.whu.edu.cn/authserver/login?service=https%3A%2F%2Fzhlj.whu.edu.cn%2FcasLogin"
        page.goto(login_url)

        max_wait = 120  # 从 180 秒缩短到 120 秒
        elapsed = 0
        zhlj_cookie_str = ""

        while elapsed < max_wait:
            cookies = context.cookies()
            has_portal_token = any(c['name'] == 'PORTAL-TOKEN' and c['value'] for c in cookies)

            if has_portal_token:
                print("\n[✔] 智慧珞珈门户鉴权成功！正在抓取 zhlj Cookie...")
                zhlj_cookie_list = context.cookies(urls=["https://zhlj.whu.edu.cn/"])
                zhlj_cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in zhlj_cookie_list])
                break

            time.sleep(0.5)  # 从 1 秒缩短到 0.5 秒
            elapsed += 1

        if not zhlj_cookie_str:
            browser.close()
            raise TimeoutError("智慧珞珈登录超时或失败。")

        # -------------------- 【步骤 2：拦截自习室 Token】 --------------------
        captured_credentials = {"token": "", "hmac": "", "xdate": "", "xid": ""}

        def handle_request(request):
            if "frontApi" in request.url:
                headers = request.headers
                token = headers.get("token") or headers.get("Token")
                hmackey = headers.get("x-hmac-request-key")
                xdate = headers.get("x-request-date")
                xid = headers.get("x-request-id")
                if token:
                    captured_credentials["token"] = token
                if hmackey:
                    captured_credentials["hmac"] = hmackey
                if xdate:
                    captured_credentials["xdate"] = xdate
                if xid:
                    captured_credentials["xid"] = xid

        page.on("request", handle_request)

        # -------------------- 【步骤 3：图书馆系统】 --------------------
        print("[✔] [后台免密流转 1/2] 正在通过图书馆 OAuth 重定向接口同步会话...")
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)

        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=10000)  # 从 15 秒缩短到 10 秒
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
            print(f"🎉 成功截获 JWT 授权密钥: {jwt_token[:20]}...")
        except Exception as e:
            print(f"警告：未能自动从 URL 提取 JWT 密钥: {str(e)}")
            jwt_token = ""

        # ================================================================
        # Step 4: Visit educational system directly to harvest cookies
        # ================================================================
        print("[OK] [Step 4] Visiting jwgl.whu.edu.cn for educational cookies...")
        page.goto("https://jwgl.whu.edu.cn/")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            print("[OK] Educational system page loaded.")
        except Exception as e:
            print(f"[WARN] Load timeout: {e}")

        # Brief wait to ensure cookies are written
        #time.sleep(2)

        # Collect all cookies before closing browser (for library_tool)
        all_cookies = context.cookies()

        # -------------------- Step 5: Harvest educational cookies --------------------
        print("[OK] Harvesting educational system cookies...")
        jwgl_cookie_list = context.cookies(urls=["https://jwgl.whu.edu.cn/"])
        browser.close()
        print("[✔] 浏览器已自动关闭。")

        jwgl_cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in jwgl_cookie_list])

        required_keys = ["_dx_captcha_vid", "_dx_uzZo5y", "JSESSIONID", "SF_cookie_1"]
        missing_keys = [key for key in required_keys if key not in jwgl_cookie_str]

        if missing_keys:
            print(f"\n⚠️ [提示] 部分 Cookie 键未在本次流转中写入: {missing_keys}")
            print(f"   当前教务 Cookie 内容: {jwgl_cookie_str}")
        else:
            print("\n✅ [成功] 教务系统 4 个核心 Cookie 已全部收割！")

        return {
            "cookie_str": zhlj_cookie_str,
            "jwgl_cookie_str": jwgl_cookie_str,
            "library_token": captured_credentials["token"],
            "library_jwt_token": jwt_token,
            "library_hmac": captured_credentials["hmac"],
            "library_request_date": captured_credentials["xdate"],
            "library_request_id": captured_credentials["xid"],
            "raw_cookies": all_cookies
        }


# ==========================================================
# LangGraph 工具封装
# ==========================================================
@tool
def login_to_whu_portal(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """启动网页弹窗，引导用户进行武汉大学统一身份认证登录并自动激活各端凭证。"""
    try:
        payload = interactive_whu_login()
        cookies_dict = {
            "zhlj": payload.get("cookie_str", ""),
            "educational": payload.get("jwgl_cookie_str", ""),
            "library_cookie": payload.get("raw_cookies", []),  # 注入专供 Playwright 用的 List[dict]
            "library_token": payload.get("library_token", ""),
            "library_jwt_token": payload.get("library_jwt_token", ""),
            "library_hmac": payload.get("library_hmac", ""),
            "library_request_date": payload.get("library_request_date", ""),
            "library_request_id": payload.get("library_request_id", "")
        }
        return Command(
            update={
                "cookies": cookies_dict,
                "messages": [ToolMessage(
                    content="【系统消息】统一身份认证成功！已成功截获智慧珞珈、教务系统、图书馆三端凭证并注入系统环境。",
                    tool_call_id=tool_call_id
                )]
            }
        )
    except Exception as e:
        return Command(
            update={
                "messages": [ToolMessage(
                    content=f"【系统消息】登录失败，原因：{str(e)}",
                    tool_call_id=tool_call_id
                )]
            }
        )


# ==========================================================
# 🚀 本地测试入口
# ==========================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=== 开始运行 login_helper 本地登录与双路 Cookie 收割调试 ===\n")
    try:
        res = interactive_whu_login()

        print("\n" + "=" * 80)
        print("🎯 【两套独立 Cookie 收割核对报告】")
        print("=" * 80)
        print("💡 1. 智慧珞珈 [zhlj.whu.edu.cn] Cookie 串:")
        print("-" * 80)
        print(res["cookie_str"])
        print("-" * 80)

        print("\n💡 2. 本科教务系统 [jwgl.whu.edu.cn] 完整 Cookie 串:")
        print("   (请检查是否已收割齐 4 个核心键: _dx_captcha_vid, _dx_uzZo5y, JSESSIONID, SF_cookie_1)")
        print("-" * 80)
        print(res["jwgl_cookie_str"])
        print("-" * 80)

        print("\n🎫 3. 图书馆自习室及选座 Token 校验数据:")
        print(f"   - 自习室 48位短 Token: {res['library_token']}")
        print(f"   - 图书馆 JWT 授权长密钥: {res['library_jwt_token'][:30] if res['library_jwt_token'] else 'None'}...")
        print("=" * 80 + "\n")
        print("[成功] 独立调试运行结束。")

    except Exception as e:
        print(f"\n❌ [异常] 调试运行失败: {str(e)}")