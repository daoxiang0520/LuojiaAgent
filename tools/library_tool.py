# tools/library_tool.py

import traceback
from playwright.sync_api import sync_playwright
from langchain_core.tools import tool
from typing import Annotated
from langgraph.prebuilt import InjectedState
import requests
import re
import time

# 19位大楼 ID 映射
LIBRARY_MAPPING = {
    "总馆": "1812737769937670144",
    "主馆": "1812737769937670144",
    "信息分馆": "1812738485913751552",
    "信息学部分馆": "1812738485913751552",
    "工学分馆": "1812738878798401536",
    "工学部分馆": "1812738878798401536",
    "医学分馆": "1812738878798401536",
    "医学部分馆": "1812738878798401536"
}

@tool
def query_library_seats(
    #raw_cookies: list, 
    #library_token: str, 
    #library_jwt_token: str, 
    #library_hmac: str, 
    #library_request_date: str, 
    #library_request_id: str, 
    query_date: str, 
    library_name: str,
    state:Annotated[dict ,InjectedState]
) -> str:
    """查询武汉大学图书馆各个分馆在指定日期的自习室/座位空闲余量。

    Args:
        query_date: 需要查询的日期，格式为 'YYYY-MM-DD'，例如 '2026-07-07'。
        library_name: 想要查询的馆区，可选值有: '总馆', '信息分馆', '工学分馆', '医学分馆'。
    """
    # 1. 自动对齐馆区 ID
    matched_id = "1812737769937670144" # 默认总馆
    target_name = "总馆"
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])  # 提取出 Playwright 专用的 List[dict] 数组
    
    if not raw_cookies:
        return "【系统提示】：未检测到有效的图书馆 Cookie 凭证，请先对我说“我要登录”。"


    for name, b_id in LIBRARY_MAPPING.items():
        if name in library_name:
            matched_id = b_id
            target_name = name
            break
            
    print(f"--- [自习室查询] 正在通过浏览器内核代签查询【{target_name}】{query_date} 的座位... ---")
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
    for _ in range(50): # 每次等0.1秒，最多等5秒
        if (captured_credentials.get("token") and 
            captured_credentials.get("hmac") and 
            captured_credentials.get("xdate") and 
            captured_credentials.get("xid")):
            break
        time.sleep(0.1)
    # 2. 启动一个轻量级的无头浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context()
        
        # 将第一步保存的完整多域名 Cookie 列表一次性注入进浏览器
        context.add_cookies(raw_cookies)
        page=context.new_page()
        page.on("request", handle_request)
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            
            # 🚀 修复 2：使用正则表达式从当前地址中精准剥离出 JWT 长密钥，防止 urlparse 受到 #/ 干扰
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
            print(f"🎉 成功截获 JWT 授权密钥: {jwt_token[:20]}...")
        except Exception as e:
            print(f"警告：未能自动从 URL 提取 JWT 密钥: {str(e)}")
            jwt_token = ""
        library_token=captured_credentials['token']
        library_hmac=captured_credentials['hmac']
        library_request_date=captured_credentials['xdate']
        library_request_id=captured_credentials['xid']
        #page = context.new_page()
        # 带上长密钥去加载网页，初始化网页的前端登录状态
        target_url = f"https://seat.lib.whu.edu.cn/seat/?token={jwt_token}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")
            
            # 浏览器内的 API 路径
            api_path = f"/jsq/static/frontApi/res/findRoomDuration/{matched_id}/{query_date}"
            
            # 🚀 核心对齐：在 fetch 请求头中，完整、原封不动地补齐四大金刚安全请求头！
            eval_js = f"""
            async () => {{
                const response = await fetch('{api_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{library_token}',
                        'X-hmac-request-key': '{library_hmac}',
                        'X-request-date': '{library_request_date}',
                        'X-request-id': '{library_request_id}',
                        'loginType': 'PC'
                    }},
                    body: JSON.stringify({{
                        "beginMinute": 492,
                        "currentPage": 1,
                        "endMinute": 0,
                        "floorId": 0,
                        "minMinute": 0,
                        "pageSize": 12,
                        "power": false,
                        "roomType": false,
                        "sortField": "",
                        "sortType": "",
                        "windows": false
                    }})
                }});
                return await response.json();
            }}
            """
            
            # 执行并获取自动签名并成功返回的 JSON 结果
            res_json = page.evaluate(eval_js)
            browser.close()
            print(res_json)
            # 5. 解析并清洗数据
            if not res_json.get("status"):
                return f"【系统提示】：图书馆系统未能成功返回数据，原因：{res_json.get('message', '鉴权/签名错误')}"
                
            data_body = res_json.get("data", {})
            room_list = data_body.get("pageList", [])
            
            if not room_list:
                return f"系统提示：在 {query_date} 未查询到【{target_name}】任何自习室余量信息。"
                
            cleaned_lines = []
            cleaned_lines.append(f"🏢 武汉大学图书馆【{target_name}】{query_date} 座位空闲情况：")
            
            for room in room_list:
                name = room.get("name", "未知区域")
                floor = room.get("floorName", "未知楼层")
                total = room.get("seatTotal", 0)
                free = room.get("seatFree", 0)
                max_min = room.get("maxMinute", 900)
                max_hours = round(max_min / 60, 1)
                
                cleaned_lines.append(
                    f"  • {floor} - {name} | 空闲座位: {free}/{total} | 最长可约: {max_hours}小时"
                )
                
            return "\n".join(cleaned_lines)
            
        except Exception as e:
            # 调试信息打印
            print("\n❌ 自习室查询工具运行发生异常：")
            traceback.print_exc()
            print("=========================================\n")
            
            browser.close()
            return f"【系统错误】：通过浏览器代签查询图书馆失败，原因为: {str(e)}"