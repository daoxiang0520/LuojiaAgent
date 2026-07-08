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
    raw_cookies=state.get("cookie_str")
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
# tools/library_tool.py 内部 query_empty_seats_in_area 完整适配版

# tools/library_tool.py 中的 query_empty_seats_in_area

@tool
def query_empty_seats_in_area(
    query_date: str,
    area_id: str,
    begin_time: str = "08:12",
    state: Annotated[dict, InjectedState] = None
) -> str:
    """查询指定自习室区域内所有具体座位（包含空闲🟢和占用🔴）的排布和编号分布。

    Args:
        query_date: 查询日期，格式为 'YYYY-MM-DD'，例如 '2026-07-08'。
        area_id: 19位自习室区域ID，例如 '1916679262728880128'。
        begin_time: 开始时间，格式为 'HH:MM'，默认为 '08:12'。
    """
    raw_cookies = state.get("raw_cookies")
    try:
        h, m = map(int, begin_time.split(":"))
        begin_minute = h * 60 + m
    except Exception:
        begin_minute = 492
        
    print(f"--- [自习室地图构建] 正在绘制区域 {area_id} 的座位图... ---")

    captured_credentials = {"token": ""}
    def handle_request(request):
        if "frontApi" in request.url:
            token = request.headers.get("token") or request.headers.get("Token")
            if token:
                captured_credentials["token"] = token

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        page.on("request", handle_request)

        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
        except Exception as e:
            browser.close()
            return f"【错误】：同步自习室会话失败: {str(e)}"

        for _ in range(30):
            if captured_credentials.get("token"):
                break
            time.sleep(0.1)

        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={jwt_token}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            api_path = f"/jsq/static/frontApi/res/freeSeatIdsDuration/{area_id}/{query_date}"
            
            eval_js = f"""
            async () => {{
                const response = await fetch('{api_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{captured_credentials["token"]}'
                    }},
                    body: JSON.stringify({{
                        "beginMinute": {begin_minute},
                        "endMinute": 0
                    }})
                }});
                return await response.json();
            }}
            """
            res_json = page.evaluate(eval_js)
            browser.close()

            if not res_json.get("status"):
                return f"【查询失败】：{res_json.get('message', '接口报错')}。"

            seats_dict = res_json.get("data", {})
            if not isinstance(seats_dict, dict) or not seats_dict:
                return f"系统提示：未能在 {query_date} 找到该区域的任何座位数据。"

            # 🚀 核心逻辑：将所有座位按照“行（Row）”进行物理归类
            row_map = {} # 键: 行号(int), 值: 该行座位的格式化字符串列表
            
            for seat in seats_dict.values():
                label = seat.get("label", "??") # 物理座位号，如 "163"
                name_coord = seat.get("name", "0行0列") # 坐标，如 "1行7列"
                status_icon = "🟢" if seat.get("status") == "FREE" else "🔴"
                
                # 正则提取行号
                row_match = re.search(r"(\d+)行", name_coord)
                row_num = int(row_match.group(1)) if row_match else 999
                
                if row_num not in row_map:
                    row_map[row_num] = []
                    
                # 记录单个座位的信息（座位号 + 状态图标）
                row_map[row_num].append((label, f"{label}号({status_icon})"))

            # 排序：行号升序排列；每一行内部按照座位 label（桌号）升序排列
            sorted_row_keys = sorted(row_map.keys())
            
            cleaned_lines = []
            cleaned_lines.append(f"🏢 自习室区域 {area_id} 实时选座图（🟢空闲 | 🔴占用）：")
            
            for row in sorted_row_keys:
                # 行内座位排序
                row_map[row].sort(key=lambda x: int(x[0]) if x[0].isdigit() else 999)
                row_seats_str = " | ".join([item[1] for item in row_map[row]])
                cleaned_lines.append(f"  📍 第 {row} 行：{row_seats_str}")

            return "\n".join(cleaned_lines)

        except Exception as e:
            browser.close()
            return f"【系统错误】：自习室地图构建异常: {str(e)}"
@tool
def reserve_library_seat(
    query_date: str,
    library_name: str,
    area_id: str,         # 自习室区域ID，如 '1916679262728880128'
    seat_label: str,      # 🌟 物理座位号，例如 '163'
    begin_time: str,      # 开始时间，格式 'HH:MM'，如 '08:30'
    end_time: str,        # 结束时间，格式 'HH:MM'，如 '12:30'
    state: Annotated[dict, InjectedState]
) -> str:
    """自动将中文座位号转换为 19位 物理 ID，并调用学校 App 受信任绿色通道（addReserve）免滑块预约座位。

    Args:
        query_date: 预约日期，格式为 'YYYY-MM-DD'，例如 '2026-07-08'。
        library_name: 馆区名称，可选值有: '总馆', '信息分馆', '工学分馆', '医学分馆'。
        area_id: 19位自习室区域ID。
        seat_label: 想要预约的物理桌贴号，例如 '163'。
        begin_time: 开始时间，格式为 'HH:MM'，例如 '08:30'。
        end_time: 结束时间，格式为 'HH:MM'，例如 '12:30'。
    """
    # 1. 提取全局 Session Cookies
    raw_cookies = state.get("raw_cookies")
    
    # 自动对齐馆区
    target_name = "总馆"
    for name in LIBRARY_MAPPING.keys():
        if name in library_name:
            target_name = name
            break

    # 换算时间分钟数
    try:
        bh, bm = map(int, begin_time.split(":"))
        eh, em = map(int, end_time.split(":"))
        begin_minute = bh * 60 + bm
        end_minute = eh * 60 + em
    except Exception:
        return "【格式错误提示】：时间格式不正确，必须为 'HH:MM' 格式。"

    print(f"\n--- [自习室极速预约] 开始处理【{target_name}】{seat_label}号座位 ({begin_time} - {end_time}) ---")

    captured_credentials = {
        "token": "",
        "hmac": "",
        "xdate": "",
        "xid": ""
    }

    # 捕获最新有效的签名头，用于发起免滑块请求
    def handle_request(request):
        if "frontApi" in request.url:
            headers = request.headers
            token = headers.get("token") or headers.get("Token")
            hmackey = headers.get("x-hmac-request-key") or headers.get("X-hmac-request-key")
            xdate = headers.get("x-request-date") or headers.get("X-request-date")
            xid = headers.get("x-request-id") or headers.get("X-request-id")
            
            if token and hmackey and xdate and xid:
                captured_credentials["token"] = token
                captured_credentials["hmac"] = hmackey
                captured_credentials["xdate"] = xdate
                captured_credentials["xid"] = xid

    # 2. 启动轻量级无头浏览器进行 Session 复活
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        page.on("request", handle_request)

        # 3. 访问官方 SSO 重定向接口，免密授权并获取最新的 JWT 长密钥 [3.1]
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
        except Exception as e:
            browser.close()
            return f"【预约失败】：统一身份认证会话同步超时: {str(e)}"

        # 等待后台拦截完成
        for _ in range(50):
            if (captured_credentials.get("token") and 
                captured_credentials.get("hmac") and 
                captured_credentials.get("xdate") and 
                captured_credentials.get("xid")):
                break
            time.sleep(0.1)

        library_token = captured_credentials['token']
        library_hmac = captured_credentials['hmac']
        library_request_date = captured_credentials['xdate']
        library_request_id = captured_credentials['xid']

        # 4. 加载选座前端环境
        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={jwt_token}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            # ================== 阶段 A：将座位号转换为 19位 物理 ID ==================
            # 查出当前时间段所有的座位分布图
            map_path = f"/jsq/static/frontApi/res/freeSeatIdsDuration/{area_id}/{query_date}"
            eval_map_js = f"""
            async () => {{
                const response = await fetch('{map_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{library_token}',
                        'X-hmac-request-key': '{library_hmac}',
                        'X-request-date': '{library_request_date}',
                        'X-request-id': '{library_request_id}',
                        'loginType': 'PC'
                    }},
                    body: JSON.stringify({{ "beginMinute": {begin_minute}, "endMinute": 0 }})
                }});
                return await response.json();
            }}
            """
            map_json = page.evaluate(eval_map_js)
            
            # 字典匹配
            matched_seat_uuid = ""
            seats_dict = map_json.get("data", {})
            for uuid, seat_info in seats_dict.items():
                if seat_info.get("label") == seat_label:
                    matched_seat_uuid = uuid
                    break
                    
            if not matched_seat_uuid:
                browser.close()
                return f"【预约失败】：在该时段内未找到可用的【{target_name}】{seat_label}号座位，可能已被他人占用。"

            print(f"[✔] 座位对齐成功！桌号 {seat_label} 对应的 19位 ID 为: {matched_seat_uuid}")

            # ================== 阶段 B：提交 addReserve 极速免滑块预约 ==================
            # 调用免滑块的 App 级 addReserve 接口，利用浏览器原生的 HMAC 拦截器代签发送！ [1.1, 1.2]
            reserve_path = "/jsq/static/frontApi/res/addReserve"
            eval_reserve_js = f"""
            async () => {{
                const response = await fetch('{reserve_path}', {{
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
                        "beginMinute": {begin_minute},
                        "endMinute": {end_minute},
                        "date": "{query_date}",
                        "seatId": "{matched_seat_uuid}"
                    }})
                }});
                return await response.json();
            }}
            """
            res_json = page.evaluate(eval_reserve_js)
            browser.close()

            # 解析最终预约结果
            if res_json.get("status"):
                return f"🎉 【预约成功】：已为您成功锁定【{target_name}】{query_date} {begin_time}~{end_time} 的 {seat_label}号座位！系统已为您自动在后台免滑块过检放行 [1.1, 1.2]！"
            else:
                return f"❌ 【预约失败】：座位预约冲突，学校选座系统返回原因：'{res_json.get('message', '未知错误')}'。"

        except Exception as e:
            browser.close()
            return f"【系统错误】：执行预约事务异常，原因: {str(e)}"
# tools/library_tool.py 追加以下两个工具

@tool
def query_user_reservations(
    query_type: str = "active",  # 可选：'active' (待使用/进行中) 或 'all' (包含历史已结束/已取消)
    state: Annotated[dict, InjectedState] = None
) -> str:
    """查询当前登录用户在自习室选座系统中的预约记录和历史订单，用于获取退订所需的 reservation_id。

    Args:
        query_type: 查询类型，'active' 代表查当前未开始或使用中的预约；'all' 代表查包含已结束、已取消的全部历史记录。
    """
    raw_cookies = state.get("raw_cookies")
    print(f"--- [自习室历史查询] 正在拉取用户的预约账单... ---")

    captured_credentials = {"token": ""}
    def handle_request(request):
        if "frontApi" in request.url:
            token = request.headers.get("token") or request.headers.get("Token")
            if token:
                captured_credentials["token"] = token

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        page.on("request", handle_request)

        # 1. 登录流转
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
        except Exception as e:
            browser.close()
            return f"【查询失败】：统一身份认证会话同步超时: {str(e)}"

        # 等待拦截 Token
        for _ in range(50):
            if captured_credentials.get("token"):
                break
            time.sleep(0.1)

        # 2. 访问自习室前端，在控制台代理 fetch 个人中心数据
        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={jwt_token}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            # 预约主单接口
            api_path = "/jsq/static/frontApi/reserve/index"
            
            # 如果是 active 只查未完成；如果是 all 不限状态
            status_param = 0 if query_type == "active" else -1
            
            eval_js = f"""
            async () => {{
                const response = await fetch('{api_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{captured_credentials["token"]}'
                    }},
                    body: JSON.stringify({{
                        "currentPage": 1,
                        "pageSize": 10
                    }})
                }});
                return await response.json();
            }}
            """
            res_json = page.evaluate(eval_js)
            browser.close()

            if not res_json.get("status"):
                return f"【查询失败】：自习室个人中心无法返回数据，原因: {res_json.get('message', '鉴权失效')}"

            data_body = res_json.get("data", {})
            page_list = data_body.get("pageList", []) if isinstance(data_body, dict) else []
            
            if not page_list:
                return "系统提示：您当前没有任何自习室预约记录。"

            cleaned_lines = []
            cleaned_lines.append(f"📋 【武汉大学图书馆】您的个人自习室预约账单（最近10笔）：")
            
            for item in page_list:
                r_id = item.get("id")                        # 12位单号，如 '202607060124'
                date_str = item.get("date", "未知日期")
                time_range = f"{item.get('beginTime', '??')}-{item.get('endTime', '??')}"
                room_name = item.get("roomName", "自习室")
                seat_label = item.get("seatLabel") or item.get("seatNo", "未编号")
                status_name = item.get("statusName", "状态未知") # 例如：'待履约', '使用中', '已结束', '已取消'
                
                # 如果是 active 模式，过滤掉已经失效的订单
                if query_type == "active" and status_name in ["已结束", "已取消", "违规已签退"]:
                    continue

                status_icon = "🟢" if "待" in status_name or "使用" in status_name else "⚪"
                cleaned_lines.append(
                    f"  • {status_icon} 【{status_name}】 | 日期: {date_str} | 时间: {time_range}\n"
                    f"    位置: {room_name} - {seat_label}号座位 | 预约单ID: `{r_id}`"
                )
                
            if len(cleaned_lines) == 1:
                return "系统提示：当前无任何生效中的预约订单。"
                
            return "\n".join(cleaned_lines)

        except Exception as e:
            browser.close()
            return f"【系统错误】：获取个人预约历史账单异常: {str(e)}"


@tool
def cancel_library_reservation(
    reservation_id: str = None,  # 模式 A：直接根据单号取消
    query_date: str = None,      # 模式 B：后备可选，想要取消的日期，格式 'YYYY-MM-DD'
    seat_label: str = None,      # 模式 B：后备可选，物理桌贴号如 '163'
    state: Annotated[dict, InjectedState] = None
) -> str:
    """取消用户在武汉大学图书馆已预约、但尚未入座签到的某个有效座位。

    Args:
        reservation_id: 想退订的12位预约单ID (例如 '202607060124'，若不提供，将根据日期与桌号在后台自动检索对齐)。
        query_date: 想要取消预约的具体日期，格式为 'YYYY-MM-DD'。
        seat_label: 想要取消的物理桌贴号，例如 '163'。
    """
    raw_cookies = state.get("raw_cookies")
    
    # 检测是否满足基本参数条件
    if not reservation_id and (not query_date or not seat_label):
        return "【错误提示】：请提供具体的预约单ID，或者提供预约日期和座位号，以便在后台定位您的预约订单。"

    print(f"--- [自习室取消预约] 开始处理退订事务... ---")

    captured_credentials = {"token": ""}
    def handle_request(request):
        if "frontApi" in request.url:
            token = request.headers.get("token") or request.headers.get("Token")
            if token:
                captured_credentials["token"] = token

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        page.on("request", handle_request)

        # 1. 登录流转
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            match = re.search(r"token=([^&]+)", page.url)
            jwt_token = match.group(1) if match else ""
        except Exception as e:
            browser.close()
            return f"【退订失败】：会话同步超时: {str(e)}"

        for _ in range(50):
            if captured_credentials.get("token"):
                break
            time.sleep(0.1)

        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={jwt_token}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            target_reservation_id = reservation_id

            # 🚀 模式 B 自动检索：如果用户没给 ID，先静默请求 /reserve/index 帮他找到那个 ID
            if not target_reservation_id:
                print(f"--- [后台自定位] 正在检索 {query_date} 桌号 {seat_label}号 对应的有效预约单 ID... ---")
                index_path = "/jsq/static/frontApi/reserve/index"
                eval_index_js = f"""
                async () => {{
                    const response = await fetch('{index_path}', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'token': '{captured_credentials["token"]}'
                        }},
                        body: JSON.stringify({{ "currentPage": 1, "pageSize": 10 }})
                    }});
                    return await response.json();
                }}
                """
                index_json = page.evaluate(eval_index_js)
                
                # 遍历查找符合 query_date 和 seat_label 的有效（待使用）单号
                page_list = index_json.get("data", {}).get("pageList", []) if isinstance(index_json.get("data"), dict) else []
                for order in page_list:
                    # 匹配日期、物理座位名，并且状态为待签到
                    o_date = order.get("date")
                    o_label = order.get("seatLabel") or order.get("seatNo")
                    o_status = order.get("statusName", "")
                    
                    if o_date == query_date and o_label == seat_label and ("待" in o_status or "进行" in o_status):
                        target_reservation_id = order.get("id")
                        break
                
                if not target_reservation_id:
                    browser.close()
                    return f"【取消失败】：未在您的未完成账单中找到【{query_date}】第【{seat_label}号】座位的有效预约单。"
                    
                print(f"[✔] 成功自动匹配！退订目标预约单号为: {target_reservation_id}")

            # 2. 正式向取消接口发起 POST 请求
            cancel_path = f"/jsq/static/frontApi/reserve/cancel/{target_reservation_id}"
            eval_cancel_js = f"""
            async () => {{
                const response = await fetch('{cancel_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{captured_credentials["token"]}'
                    }},
                    body: JSON.stringify({{}})
                }});
                return await response.json();
            }}
            """
            res_json = page.evaluate(eval_cancel_js)
            browser.close()

            if res_json.get("status"):
                return f"🎉 【取消成功】：您已成功退订预约单 `{target_reservation_id}`（对应的座位和时间段已释放）。"
            else:
                return f"❌ 【取消失败】：学校座位系统返回拒绝原因：'{res_json.get('message', '未知原因')}'。"

        except Exception as e:
            browser.close()
            return f"【系统错误】：执行取消事务时发生未知异常: {str(e)}"