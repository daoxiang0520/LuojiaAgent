# tools/login_helper.py

import time
import re # 导入正则库
from playwright.sync_api import sync_playwright

def interactive_whu_login() -> dict:
    """一键登录，多路静默并发收割，并导出全局多域名 Cookie 列表及双 Token 凭证。"""
    print("\n" + "="*50)
    print("【统一凭证自动收割器】正在启动浏览器窗口...")
    print(" 1. 请在弹出的浏览器中手动登录智慧珞珈。")
    print(" 2. 登录成功后，系统会自动在后台同步并收割全套图书馆安全凭证。")
    print("="*50 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 1. 引导用户登录智慧珞珈
        login_url = "https://cas.whu.edu.cn/authserver/login?service=https%3A%2F%2Fzhlj.whu.edu.cn%2FcasLogin"
        page.goto(login_url)

        max_wait = 180
        elapsed = 0
        cookie_str = ""

        # 等待智慧珞珈课表 Cookie 生成
        while elapsed < max_wait:
            cookies = context.cookies()
            has_portal_token = any(c['name'] == 'PORTAL-TOKEN' and c['value'] for c in cookies)
            
            if has_portal_token:
                print("\n[✔] 智慧珞珈登录成功！正在提取课表 Cookie...")
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                break
            
            time.sleep(1)
            elapsed += 1

        if not cookie_str:
            browser.close()
            raise TimeoutError("智慧珞珈登录超时或失败。")

        # 2. 设置请求拦截监听器，截获图书馆选座系统的 48位短 Token Headers
        captured_credentials = {
            "token": ""
        }

        def handle_request(request):
            if "frontApi" in request.url:
                headers = request.headers
                token = headers.get("token") or headers.get("Token")
                hmackey=headers.get("x-hmac-request-key")
                xdate=headers.get("x-request-date")
                xid=headers.get("x-request-id") 
                if token:
                    captured_credentials["token"] = token
                if hmackey:
                    captured_credentials["hmac"] = hmackey
                if xdate:
                    captured_credentials["xdate"] = xdate
                if xid:
                    captured_credentials["xid"] = xid

        #page.on("request", handle_request)

        # 3. 后台自动免密跳转到图书馆的官方 OAuth 回调接口
        '''print("[✔] [后台免密流转] 正在通过图书馆官方 OAuth 重定向接口同步登录状态...")
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        
        # 🚀 修复 1：使用 Lambda 表达式作为判断器，只要 URL 中包含 "token="，立即放行（完美兼容 #/login 哈希路由）
        print("[✔] 正在提取图书馆 JWT 授权密钥...")
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            
            # 🚀 修复 2：使用正则表达式从当前地址中精准剥离出 JWT 长密钥，防止 urlparse 受到 #/ 干扰
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
            print(f"🎉 成功截获 JWT 授权密钥: {jwt_token[:20]}...")
        except Exception as e:
            print(f"警告：未能自动从 URL 提取 JWT 密钥: {str(e)}")
            jwt_token = ""

        # 等待拦截自习室 48位短 Token (最长等 10 秒)
        for _ in range(10):
            if captured_credentials["token"]:
                print("🎉 成功截获自习室核心 48位 会话 Token 凭证！")
                break
            time.sleep(1)
'''
        # 4. 导出当前上下文里所有的多域名 Cookie 列表
        raw_cookies = context.cookies()
        browser.close()

        #if not captured_credentials["token"] or not jwt_token:
        #    raise TimeoutError("未能成功截获图书馆选座系统的 Token。")

        return {
            "cookie_str": cookie_str,
            "raw_cookies": raw_cookies
        }
# tools/login_helper.py (在您原有代码下方追加以下内容)

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from typing import Annotated

@tool
def login_to_whu_portal(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """启动网页弹窗，引导用户进行武汉大学统一身份认证登录。
    当系统提示未登录、登录失效、或用户显式要求“登录/身份认证”时，必须调用此工具。
    """
    try:
        # 调用您写好的 Playwright 登录函数
        cookie_str = interactive_whu_login()
        
        # 返回 Command 对象：同时更新全局 State 里的 cookie_str，并向大模型反馈结果
        return Command(
            update={
                "cookie_str": cookie_str,
                "messages": [ToolMessage(content="【系统消息】统一身份认证成功！已成功获取 PORTAL-TOKEN 并安全注入系统环境。", tool_call_id=tool_call_id)]
            }
        )
    except Exception as e:
        # 如果超时或失败，向大模型反馈错误信息
        return Command(
            update={
                "messages": [ToolMessage(content=f"【系统消息】登录失败，原因：{str(e)}", tool_call_id=tool_call_id)]
            }
        )