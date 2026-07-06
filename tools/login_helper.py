# tools/login_helper.py
import time
from playwright.sync_api import sync_playwright

def interactive_whu_login() -> str:
    """启动有界面的 Chromium 浏览器，引导用户在武大统一身份认证页面登录。
    一旦检测到 PORTAL-TOKEN 生成，立即提取 Cookie 并关闭浏览器。
    """
    print("\n" + "="*50)
    print("【系统安全提示】正在启动武汉大学统一身份认证弹窗...")
    print(" 请在弹出的浏览器中手动登录（输入账号密码/短信验证/扫码登录均可）。")
    print(" 登录成功后，系统会自动关闭窗口并为您提供服务。")
    print("="*50 + "\n")

    with sync_playwright() as p:
        # 1. 启动有界面的浏览器
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 2. 直接访问带 service 参数的 CAS 回调地址，确保能成功跳回并写入关键 Cookie
        login_url = "https://cas.whu.edu.cn/authserver/login?service=https%3A%2F%2Fzhlj.whu.edu.cn%2FcasLogin"
        page.goto(login_url)

        max_wait = 180  # 最长等待3分钟
        elapsed = 0
        cookie_str = ""

        # 3. 循环监听 Cookie 的生成状态
        # tools/login_helper.py 循环检测部分修改

        while elapsed < max_wait:
            cookies = context.cookies()
            
            # 【新增调试日志】打印当前的网页地址和已经拿到的 Cookie 数量
            print(f"[调试] 正在检测... 当前页面: {page.url[:50]}... | 捕获 Cookie 数: {len(cookies)}")
            
            has_portal_token = any(c['name'] == 'PORTAL-TOKEN' and c['value'] for c in cookies)
            
            if has_portal_token:
                print("\n🎉 统一身份认证成功！正在提取 Cookie 凭证...")
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                break
            
            time.sleep(1)
            elapsed += 1

        # 4. 自动关闭浏览器
        browser.close()

        if not cookie_str:
            raise TimeoutError("登录超时，未能在规定时间内完成统一身份认证。")

        return cookie_str