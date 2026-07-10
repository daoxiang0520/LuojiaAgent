# login_helper.py

import time
import re
import json
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

        # -------------------- 【步骤 1：直接登录 CAS】 --------------------
        # CAS 登录检测：用 CASTGC 票据（只有登录成功后 CAS 才会签发）
        # 不能用 JSESSIONID（CAS 页面一加载就会设，是匿名会话）
        login_url = "https://cas.whu.edu.cn/authserver/login"
        page.goto(login_url)
        print("[INFO] 请在弹出的浏览器窗口中扫码或输入密码登录 CAS...")
        max_wait = 120
        elapsed = 0
        saved_cookies = []
        castgc_value = ""

        while elapsed < max_wait:
            cookies = context.cookies()
            # CASTGC = CAS Ticket Granting Cookie，登录成功后才存在
            has_castgc = any(c['name'] == 'CASTGC' and c['value'] for c in cookies)

            if has_castgc:
                print("\n[OK] CAS 统一身份认证成功！CASTGC 票据已获取。")
                saved_cookies = context.cookies()
                # 提取 CASTGC 值（从列表中取出第一个匹配的）
                _castgc_list = [c['value'] for c in cookies if c['name'] == 'CASTGC']
                castgc_value = _castgc_list[0] if _castgc_list else ""
                print(f"[OK] CASTGC: {castgc_value[:30]}...")
                break

            time.sleep(0.5)
            elapsed += 1

        if not saved_cookies:
            browser.close()
            raise TimeoutError("CAS 登录超时或失败，未获取到 CASTGC 票据。请在 120 秒内完成扫码/密码登录。")

        # 关闭有头浏览器，后续全部用 headless
        browser.close()
        print("[OK] 登录完成，关闭交互窗口，切换为后台无头模式...")

        # -------------------- 步骤 2：开 headless 浏览器，注入 Cookie 继续 --------------------
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

        browser2 = p.chromium.launch(headless=True)
        context2 = browser2.new_context()
        context2.add_cookies(saved_cookies)
        page2 = context2.new_page()
        page2.on("request", handle_request)

        # -------------------- 步骤 3：图书馆 OAuth 免密流转 --------------------
        print("[OK] [后台免密流转 1/3] 正在通过图书馆 OAuth 重定向接口同步会话...")
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page2.goto(lib_oauth_url)

        try:
            page2.wait_for_url(lambda url: "token=" in url, timeout=10000)
            match = re.search(r"token=([^&]+)", page2.url)
            jwt_token = match.group(1) if match else ""
            print(f"[OK] 成功截获 JWT 授权密钥: {jwt_token[:20]}...")
        except Exception as e:
            print(f"[WARN] 未能自动从 URL 提取 JWT 密钥: {str(e)}")
            jwt_token = ""

        # ── 加载图书馆 SPA，触发 frontApi 请求以捕获 library_token ──
        hmac_key = ""
        library_token_val = ""
        hmac_key = ""
        if jwt_token:
            try:
                print("[OK] [后台免密流转 2/3] 等待 SPA 完成 CAS 认证...")
                # OAuth 重定向已停在 SPA + JWT，不能再 goto（JWT 一次性）
                page2.wait_for_load_state("networkidle", timeout=15000)

                # 从 sessionStorage 直接读 token（key 前缀 jsq_p-）
                for _ in range(80):
                    library_token_val = page2.evaluate("() => sessionStorage.getItem('jsq_p-token')")
                    if library_token_val:
                        break
                    time.sleep(0.15)

                # 从 sessionStorage 读 hmac_key
                raw = page2.evaluate("() => sessionStorage.getItem('jsq_p-systemInfo')")
                if raw:
                    try:
                        hmac_key = json.loads(raw).get("hmacKey", "")
                    except:
                        hmac_key = ""

                print(f"[OK] library_token: {'OK' if library_token_val else 'FAIL'}, "
                      f"hmac_key: {'OK' if hmac_key else 'FAIL'}")
            except Exception as e:
                print(f"[WARN] 图书馆 SPA 提取异常: {e}")

        # -------------------- 步骤 4：访问教务系统收割 Cookie --------------------
        print("[OK] [后台免密流转 3/3] 正在访问教务系统获取 Cookie...")
        page2.goto("https://cas.whu.edu.cn/authserver/login?service=https%3A%2F%2Fjwgl.whu.edu.cn%2F")
        try:
            page2.wait_for_load_state("domcontentloaded", timeout=15000)
            print("[OK] 教务系统页面加载完成。")
        except Exception as e:
            print(f"[WARN] 教务系统加载超时: {e}")

        # 收集 Cookie + 收割教务系统 Cookie
        all_cookies = context2.cookies()
        print("[OK] 正在收割教务系统 Cookie...")
        jwgl_cookie_list = context2.cookies(urls=["https://jwgl.whu.edu.cn/"])
        browser2.close()
        print("[OK] 浏览器已自动关闭。")

        jwgl_cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in jwgl_cookie_list])

        required_keys = ["_dx_captcha_vid", "_dx_uzZo5y", "JSESSIONID", "SF_cookie_1"]
        missing_keys = [key for key in required_keys if key not in jwgl_cookie_str]

        if missing_keys:
            print(f"\n⚠️ [提示] 部分 Cookie 键未在本次流转中写入: {missing_keys}")
            print(f"   当前教务 Cookie 内容: {jwgl_cookie_str}")
        else:
            print("\n✅ [成功] 教务系统 4 个核心 Cookie 已全部收割！")
        print(captured_credentials)
        return {
            "cookie_str": "",  # 不再依赖 zhlj PORTAL-TOKEN，CAS CASTGC 已覆盖
            "castgc": castgc_value,
            "jwgl_cookie_str": jwgl_cookie_str,
            "library_token": captured_credentials["token"],
            "library_jwt_token": jwt_token,
            "library_hmac": captured_credentials["hmac"],
            "library_request_date": captured_credentials["xdate"],
            "library_request_id": captured_credentials["xid"],
            "raw_cookies": all_cookies,
            "library_hmac_key": hmac_key,
        }


# ==========================================================
# 代理模式：用 CASTGC 收割图书馆+教务凭证（无需弹窗）
# ==========================================================
def harvest_from_castgc(castgc: str) -> dict:
    """
    用 CASTGC 票据免弹窗收割图书馆+教务凭证。

    Args:
        castgc: CASTGC 值（如 "TGT-112146--..."）

    Returns:
        dict: 含 educational, library_token, library_hmac_key 等
    """
    saved_cookies = [{
        "name": "CASTGC", "value": castgc,
        "domain": "cas.whu.edu.cn", "path": "/authserver",
        "httpOnly": True, "secure": False, "sameSite": "Lax",
    }]

    captured = {"token": "", "hmac_key": "", "jwt_token": ""}
    jwgl_cookie_str = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(saved_cookies)
        page = ctx.new_page()

        # ── 图书馆 OAuth → JWT ──
        oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(oauth_url, timeout=30000)
        try:
            page.wait_for_url(lambda u: "token=" in u, timeout=30000)
            m = re.search(r"token=([^&]+)", page.url)
            captured["jwt_token"] = m.group(1) if m else ""
            print(f"[Harvest] JWT: {captured['jwt_token'][:20]}...")
        except Exception as e:
            browser.close()
            raise TimeoutError(f"CAS SSO 失败: {e}")

        # ── SPA → sessionStorage token + hmacKey ──
        page.wait_for_load_state("networkidle", timeout=30000)
        for _ in range(100):
            t = page.evaluate("() => sessionStorage.getItem('jsq_p-token')")
            if t:
                captured["token"] = t
                break
            time.sleep(0.15)

        if captured["token"]:
            for _ in range(60):
                raw = page.evaluate("() => sessionStorage.getItem('jsq_p-systemInfo')")
                if raw:
                    try:
                        si = json.loads(raw)
                        if si.get("hmacKey"):
                            captured["hmac_key"] = si["hmacKey"]
                            break
                    except Exception:
                        pass
                time.sleep(0.2)

        # ── 教务系统 Cookie ──
        page.goto("https://cas.whu.edu.cn/authserver/login?service=https%3A%2F%2Fjwgl.whu.edu.cn%2F")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        jwgl = ctx.cookies(urls=["https://jwgl.whu.edu.cn/"])
        jwgl_cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in jwgl)

        all_cookies = ctx.cookies()
        browser.close()

    print(f"[Harvest] token={'OK' if captured['token'] else 'FAIL'}, "
          f"hmac_key={'OK' if captured['hmac_key'] else 'FAIL'}, "
          f"jwgl={'OK' if jwgl_cookie_str else 'FAIL'}")

    return {
        "educational": jwgl_cookie_str,
        "library_token": captured["token"],
        "library_jwt_token": captured["jwt_token"],
        "library_hmac_key": captured["hmac_key"],
        "library_cookie": all_cookies,
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
            "castgc": payload.get("castgc", ""),
            "educational": payload.get("jwgl_cookie_str", ""),
            "library_cookie": payload.get("raw_cookies", []),
            "library_token": payload.get("library_token", ""),
            "library_jwt_token": payload.get("library_jwt_token", ""),
            "library_hmac": payload.get("library_hmac", ""),
            "library_hmac_key": payload.get("library_hmac_key", ""),
            "library_request_date": payload.get("library_request_date", ""),
            "library_request_id": payload.get("library_request_id", ""),
        }
        print(cookies_dict)
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