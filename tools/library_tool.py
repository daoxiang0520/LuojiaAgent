# tools/library_tool.py

import time
import re
import json
import traceback
from playwright.sync_api import sync_playwright
from langchain_core.tools import tool
from typing import Annotated
from langgraph.prebuilt import InjectedState
from .captcha_solver import solve_captcha

# 武汉大学图书馆分馆大楼 19位雪花 ID 映射
LIBRARY_MAPPING = {
    "总馆": "1812737769937670144",
    "主馆": "1812737769937670144",
    "信息分馆": "1812738485913751552",
    "信息学部分馆": "1812738485913751552",
    "工学分馆": "1812738878798401536",
    "工学部分馆": "1812738878798401536",
    "医学分馆": "1812739190351302656",
    "医学部分馆": "1812739190351302656"
}

# ==================== 辅助函数：统一完成 CAS 重定向及多安全头捕获 ====================
def _harvest_library_session(raw_cookies: list) -> dict:
    """内部辅助函数：通过 Playwright 极速完成学校 CAS 免密流转并捕获最新四大金刚请求头。"""
    captured = {"token": "", "hmac": "", "xdate": "", "xid": "", "jwt_token": ""}
    
    def handle_request(request):
        if "frontApi" in request.url:
            headers = request.headers
            token = headers.get("token") or headers.get("Token")
            hmac = headers.get("x-hmac-request-key") or headers.get("X-hmac-request-key")
            xdate = headers.get("x-request-date") or headers.get("X-request-date")
            xid = headers.get("x-request-id") or headers.get("X-request-id")
            
            if token and hmac and xdate and xid:
                captured["token"] = token
                captured["hmac"] = hmac
                captured["xdate"] = xdate
                captured["xid"] = xid

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        page.on("request", handle_request)

        # 访问官方重定向认证端点
        lib_oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(lib_oauth_url)
        
        try:
            page.wait_for_url(lambda url: "token=" in url, timeout=15000)
            match = re.search(r"token=([^&]+)", page.url)
            captured["jwt_token"] = match.group(1) if match else ""
        except Exception as e:
            browser.close()
            raise TimeoutError(f"统一身份认证会话同步超时: {str(e)}")

        # 循环等待异步 frontApi 请求拦截完毕
        for _ in range(50):
            if captured["token"] and captured["hmac"] and captured["xdate"] and captured["xid"]:
                break
            time.sleep(0.1)
            
        browser.close()
        
    if not captured["token"] or not captured["jwt_token"]:
        raise ValueError("未能截获自习室核心双 Token 凭证")
        
    return captured


# ==================== 1. 查询分馆座位大盘工具 ====================
@tool
def query_library_seats(
    query_date: str, 
    library_name: str = "总馆",
    state: Annotated[dict, InjectedState] = None
) -> str:
    """查询武汉大学图书馆某个分馆在指定日期的所有自习区域座位空闲概览。

    用途：用户想了解某个图书馆整体座位情况时调用。返回各楼层各区域的名称、总座位数、空闲数和区域ID。
    调用时机：用户问"总馆明天有座位吗"、"信息分馆还有空位吗"等。这是座位查询的第一步，后续如需看具体座位排布，再用 query_empty_seats_in_area。

    参数:
    - query_date: 查询日期，格式 YYYY-MM-DD（如 "2026-07-10"）。用户说"明天"时需要根据系统时间锚点换算。
    - library_name: 分馆名称。支持: 总馆/主馆、信息分馆/信息学部分馆、工学分馆/工学部分馆、医学分馆/医学部分馆。默认"总馆"。
    - state: 系统自动注入的凭证，无需传入。

    返回: 各区域列表，每行含楼层、区域名、总座位、空闲数、区域ID（后续查座位图或预约需要此ID）。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    matched_id = "1812737769937670144" # 默认总馆
    target_name = "总馆"
    for name, b_id in LIBRARY_MAPPING.items():
        if name in library_name:
            matched_id = b_id
            target_name = name
            break
            
    print(f"--- [自习室查询] 正在通过浏览器内核代签查询【{target_name}】{query_date} 的座位... ---")
    
    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：获取自习室登录会话失败: {str(e)}"
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        
        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")
            
            api_path = f"/jsq/static/frontApi/res/findRoomDuration/{matched_id}/{query_date}"
            eval_js = f"""
            async () => {{
                const response = await fetch('{api_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{creds["token"]}',
                        'X-hmac-request-key': '{creds["hmac"]}',
                        'X-request-date': '{creds["xdate"]}',
                        'X-request-id': '{creds["xid"]}',
                        'loginType': 'PC'
                    }},
                    body: JSON.stringify({{
                        "beginMinute": 492,
                        "currentPage": 1,
                        "endMinute": 0,
                        "floorId": 0,
                        "minMinute": 0,
                        "pageSize": 200,
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
            res_json = page.evaluate(eval_js)
            browser.close()
            
            if not res_json.get("status"):
                return f"【查询失败】：自习室系统报错：'{res_json.get('message', '鉴权错误')}'。"
                
            data_body = res_json.get("data", {})
            room_list = data_body.get("pageList", []) if isinstance(data_body, dict) else []
            
            if not room_list:
                return f"系统提示：在 {query_date} 未查询到【{target_name}】任何自习室余量信息。"
                
            cleaned_lines = [f"🏢 武汉大学图书馆【{target_name}】{query_date} 座位空闲情况："]
            for room in room_list:
                cleaned_lines.append(
                    f"  • 【{room.get('floorName', '1楼')}】{room.get('name')} | 总座位: {room.get('seatTotal')} | 空闲: {room.get('seatFree')} | 区域ID: `{room.get('id')}`"
                )
            return "\n".join(cleaned_lines)
            
        except Exception as e:
            browser.close()
            return f"【系统错误】：通过代签接口抓取座位失败: {str(e)}"


# ==================== 2. 查询区域具体座位排布工具（可视化座位图） ====================
@tool
def query_empty_seats_in_area(
    query_date: str,
    area_id: str,
    begin_time: str = "08:12",
    state: Annotated[dict, InjectedState] = None
) -> str:
    """查询指定自习区域内所有座位的实时状态，按排(Row)展示空闲🟢/占用🔴分布图。

    用途：用户想选一个具体座位时，先调用此工具查看该区域每排每座的空闲情况，然后选一个空闲座位号去预约。
    调用时机：在 query_library_seats 之后，用户说"看看A1区有哪些空位"、"3楼自主学习区还有什么座位"时调用。
    前置条件：需要先从 query_library_seats 的返回结果中获取目标区域的 area_id（19位数字）。

    参数:
    - query_date: 查询日期，格式 YYYY-MM-DD。
    - area_id: 区域ID（19位雪花ID，从 query_library_seats 返回的 `区域ID` 字段获取）。
    - begin_time: 查询起始时间，格式 HH:MM（如 "08:12"），默认 "08:12"。
    - state: 系统自动注入，无需传入。

    返回: 按排(行)展示的座位图，每个座位显示座位号和🟢空闲/🔴占用状态。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    try:
        h, m = map(int, begin_time.split(":"))
        begin_minute = h * 60 + m
    except Exception:
        begin_minute = 492
        
    print(f"--- [自习室地图构建] 正在绘制区域 {area_id} 的座位图... ---")

    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：获取自习室登录会话失败: {str(e)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()

        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}"
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
                        'token': '{creds["token"]}',
                        'X-hmac-request-key': '{creds["hmac"]}',
                        'X-request-date': '{creds["xdate"]}',
                        'X-request-id': '{creds["xid"]}',
                        'loginType': 'PC'
                    }},
                    body: JSON.stringify({{ "beginMinute": {begin_minute}, "endMinute": 0 }})
                }});
                return await response.json();
            }}
            """
            res_json = page.evaluate(eval_js)
            browser.close()

            if not res_json.get("status"):
                return f"【查询失败】：学校座位系统返回：{res_json.get('message', '未知错误')}。"

            seats_dict = res_json.get("data", {})
            if not isinstance(seats_dict, dict) or not seats_dict:
                return f"系统提示：在 {query_date} 该区域内没有可用的座位数据。"

            # 将座位按“行（Row）”进行物理排布归类，节省 Token
            row_map = {}
            for seat in seats_dict.values():
                label = seat.get("label", "??")
                name_coord = seat.get("name", "0行0列")
                status_icon = "🟢" if seat.get("status") == "FREE" else "🔴"
                
                row_match = re.search(r"(\d+)行", name_coord)
                row_num = int(row_match.group(1)) if row_match else 999
                
                if row_num not in row_map:
                    row_map[row_num] = []
                row_map[row_num].append((label, f"{label}号({status_icon})"))

            sorted_row_keys = sorted(row_map.keys())
            cleaned_lines = [f"🏢 自习室区域 {area_id} 实时选座图（🟢空闲 | 🔴占用）："]
            for row in sorted_row_keys:
                row_map[row].sort(key=lambda x: int(x[0]) if x[0].isdigit() else 999)
                row_seats_str = " | ".join([item[1] for item in row_map[row]])
                cleaned_lines.append(f"  📍 第 {row} 行：{row_seats_str}")

            return "\n".join(cleaned_lines)

        except Exception as e:
            browser.close()
            return f"【系统错误】：自习室地图构建异常: {str(e)}"


# ==================== 3. 极速提交座位预约（addReserve + 滑块验证码自动绕过） ====================
@tool
def reserve_library_seat(
    query_date: str,
    library_name: str,
    area_id: str,
    seat_label: str,
    begin_time: str,
    end_time: str,
    state: Annotated[dict, InjectedState]
) -> str:
    """预约图书馆座位。自动完成座位号→物理ID转换，遇到滑块验证码自动破解重试。

    用途：用户选好座位后执行预约。全自动流程：座位号对齐 → 提交预约 → 如触发验证码则自动破解 → 带token重试。
    调用时机：用户已通过 query_library_seats + query_empty_seats_in_area 选定了目标区域和座位号，明确说"帮我预约XX号座位"时调用。
    前置条件：需要 area_id（从 query_library_seats 获取）和 seat_label（从 query_empty_seats_in_area 的座位图中选一个空闲座位号）。

    参数:
    - query_date: 预约日期，格式 YYYY-MM-DD（如 "2026-07-10"）。
    - library_name: 分馆名称（总馆/信息分馆/工学分馆/医学分馆），用于匹配 venueId。
    - area_id: 区域ID（19位雪花ID，从 query_library_seats 返回的区域ID获取）。
    - seat_label: 座位号（如 "005"、"163"），即桌贴号。必须是从 query_empty_seats_in_area 中确认空闲的座位。
    - begin_time: 开始时间，格式 HH:MM（如 "08:00"）。
    - end_time: 结束时间，格式 HH:MM（如 "12:00"）。注意：短时段（如30分钟）比长时段更容易成功。
    - state: 系统自动注入，无需传入。

    返回: 预约成功/失败的消息。成功时建议告知用户签到时间和地点。常见失败原因：预约窗口未开放（需22:45后）、座位已被抢、时段不可用。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    username = cookies.get("library_token", "2025302114221")
    # 从 JWT 中提取学号
    jwt = cookies.get("library_jwt_token", "")
    if jwt:
        import base64 as _b64
        try:
            payload = json.loads(_b64.b64decode(jwt.split(".")[1] + "==").decode())
            username = payload.get("sub", username)
        except:
            pass

    target_name = "总馆"
    for name in LIBRARY_MAPPING.keys():
        if name in library_name:
            target_name = name
            break

    try:
        bh, bm = map(int, begin_time.split(":"))
        eh, em = map(int, end_time.split(":"))
        begin_minute = bh * 60 + bm
        end_minute = eh * 60 + em
    except Exception:
        return "【格式错误提示】：时间格式不正确，必须为 'HH:MM' 格式。"

    print(f"\n--- [自习室极速预约] 开始处理【{target_name}】{seat_label}号座位 ({begin_time} - {end_time}) ---")

    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：获取自习室登录会话失败: {str(e)}"

    # 嵌套工具函数（reserve_path 将在 matched_seat_uuid 解析后于下方定义）
    def _do_add_reserve(page, cap_token=""):
        """执行 freeBook API 调用"""
        url = reserve_path
        if cap_token:
            url += f"?capToken={cap_token}"
        eval_js = f"""
        async () => {{
            const response = await fetch('{url}', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'token': '{creds["token"]}',
                    'X-hmac-request-key': '{creds["hmac"]}',
                    'X-request-date': '{creds["xdate"]}',
                    'X-request-id': '{creds["xid"]}',
                    'loginType': 'PC'
                }},
                body: JSON.stringify({{}})
            }});
            return await response.json();
        }}
        """
        return page.evaluate(eval_js)

    def _get_seat_id(page):
        """将桌贴号转换为 19位 物理 ID"""
        map_path = f"/jsq/static/frontApi/res/freeSeatIdsDuration/{area_id}/{query_date}"
        eval_js = f"""
        async () => {{
            const response = await fetch('{map_path}', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'token': '{creds["token"]}',
                    'X-hmac-request-key': '{creds["hmac"]}',
                    'X-request-date': '{creds["xdate"]}',
                    'X-request-id': '{creds["xid"]}',
                    'loginType': 'PC'
                }},
                body: JSON.stringify({{ "beginMinute": {begin_minute}, "endMinute": 0 }})
            }});
            return await response.json();
        }}
        """
        return page.evaluate(eval_js)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()

        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            # 阶段 A：座位号 → 物理 ID
            map_json = _get_seat_id(page)
            matched_seat_uuid = ""
            seats_dict = map_json.get("data", {})
            for uuid, seat_info in seats_dict.items():
                if seat_info.get("label") == seat_label:
                    matched_seat_uuid = uuid
                    break

            if not matched_seat_uuid:
                browser.close()
                return f"【预约失败】：在该时段内未找到可用的【{target_name}】{seat_label}号座位，可能已被他人占用。"

            print(f"[✔] 座位对齐成功！桌号 {seat_label} -> ID: {matched_seat_uuid}")
            reserve_path = f"/jsq/static/frontApi/make/freeBook/{matched_seat_uuid}/{query_date}/{begin_minute}/{end_minute}"

            # 阶段 B：直接预约（无验证码）
            res_json = _do_add_reserve(page)
            msg = res_json.get("message", "")

            # 阶段 C：触发验证码 → 自动破解 → 带 capToken 重试
            if not res_json.get("status") and ("验证" in msg or "滑块" in msg or "captcha" in msg.lower()):
                print(f"[!] 触发验证码: {msg}，正在自动破解...")
                try:
                    captcha_result = solve_captcha(username=username, max_retries=3)
                    if captcha_result.get("success"):
                        token = captcha_result.get("data", {}).get("token", "")
                        if token:
                            print(f"[✔] 验证码破解成功，重试预约...")
                            res_json = _do_add_reserve(page, cap_token=token)
                        else:
                            print("[!] 验证码通过但未返回 token")
                    else:
                        print(f"[!] 验证码破解失败: {captcha_result}")
                except Exception as ce:
                    print(f"[!] 验证码破解异常: {ce}")

            browser.close()

            if res_json.get("status"):
                return f"🎉 【预约成功】：已为您成功锁定【{target_name}】{query_date} {begin_time}~{end_time} 的 {seat_label}号座位！"
            else:
                return f"❌ 【预约失败】：学校选座系统返回：'{res_json.get('message', '未知错误')}'。"

        except Exception as e:
            browser.close()
            return f"【系统错误】：执行预约事务异常: {str(e)}"


# ==================== 4. 查询当前预约记录与历史账单 ====================
@tool
def query_user_reservations(
    query_type: str = "active",  # 可选：'active' (查当前未开始和使用中) 或 'all' (包含历史已取消/已结束)
    state: Annotated[dict, InjectedState] = None
) -> str:
    """查询用户的图书馆预约记录，返回预约单列表（含预约单ID、日期、时段、座位号、状态）。

    用途：查看当前有哪些预约、获取退订所需的 reservation_id、确认预约是否生效。
    调用时机：用户问"我的预约"、"查看我的预约记录"、"帮我取消预约"（先查记录获取ID再取消）时调用。
    前置条件：需要先登录（login_to_whu_portal）。如果用户直接给了 reservation_id 则不需要此步。

    参数:
    - query_type: "active"（默认，仅返回待签到/使用中的有效预约）或 "all"（含历史已取消/已结束）。
    - state: 系统自动注入，无需传入。

    返回: 预约记录列表，每条含 预约单ID(`id`)、日期、时间、位置、状态。预约单ID 是 cancel_library_reservation 的必要参数。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    print(f"--- [自习室历史查询] 正在拉取用户的预约账单... ---")

    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：获取自习室登录会话失败: {str(e)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()

        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            api_path = "/jsq/static/frontApi/user/history/1/15"
            eval_js = f"""
            async () => {{
                const response = await fetch('{api_path}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'token': '{creds["token"]}',
                        'X-hmac-request-key': '{creds['hmac']}',
                        'X-request-date': '{creds['xdate']}',
                        'X-request-id': '{creds['xid']}',
                        'loginType': 'PC'
                    }},
                    body: JSON.stringify({{}})
                }});
                return await response.json();
            }}
            """
            
            # 由于 eval 内部需要直接借用外层的拦截 headers，此处动态转写
            eval_js = eval_js.replace("{library_token}", creds["token"])
            eval_js = eval_js.replace("{library_hmac}", creds["hmac"])
            eval_js = eval_js.replace("{library_request_date}", creds["xdate"])
            eval_js = f"async () => {{ const response = await fetch('{api_path}', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json', 'token': '{creds['token']}', 'X-hmac-request-key': '{creds['hmac']}', 'X-request-date': '{creds['xdate']}', 'X-request-id': '{creds['xid']}', 'loginType': 'PC' }}, body: JSON.stringify({{ 'currentPage': 1, 'pageSize': 15 }}) }}); return await response.json(); }}"
            
            res_json = page.evaluate(eval_js)
            browser.close()

            if not res_json.get("status"):
                return f"【查询失败】：自习室个人中心无法返回数据，原因: {res_json.get('message', '鉴权失效')}"

            data_body = res_json.get("data", {})
            page_list = data_body.get("pageList", []) if isinstance(data_body, dict) else []
            
            if not page_list:
                return "系统提示：您当前没有任何自习室预约记录。"

            cleaned_lines = [f"📋 【武汉大学图书馆】您的个人自习室预约记录（最近15笔）："]
            for item in page_list:
                r_id = item.get("id")
                date_str = item.get("date", "未知")
                time_range = f"{item.get('beginTime', '??')}-{item.get('endTime', '??')}"
                room_name = item.get("roomName", "自习室")
                seat_label = item.get("seatLabel") or item.get("seatNo", "未编号")
                status_name = item.get("statusName", "状态未知")
                
                if query_type == "active" and status_name in ["已结束", "已取消", "违规已签退"]:
                    continue

                status_icon = "🟢" if "待" in status_name or "使用" in status_name or "进行" in status_name else "⚪"
                cleaned_lines.append(
                    f"  • {status_icon} 【{status_name}】 | 日期: {date_str} | 时间: {time_range}\n"
                    f"    位置: {room_name} - {seat_label}号座位 | 预约单ID: `{r_id}`"
                )
                
            if len(cleaned_lines) == 1:
                return "系统提示：当前无符合条件的有效预约记录。"
                
            return "\n".join(cleaned_lines)

        except Exception as e:
            browser.close()
            return f"【系统错误】：获取个人预约历史账单异常: {str(e)}"


# ==================== 5. 取消座位预约工具 ====================
@tool
def cancel_library_reservation(
    reservation_id: str = None,
    query_date: str = None,
    seat_label: str = None,
    state: Annotated[dict, InjectedState] = None
) -> str:
    """取消一个尚未入座的图书馆座位预约，释放座位供他人使用。

    用途：退订预约。支持两种定位方式：1) 直接传 reservation_id；2) 传 query_date + seat_label 自动查找。
    调用时机：用户说"取消预约"、"退订座位"、"我不去了帮我取消"时调用。
    前置条件：如果用户没有提供 reservation_id，建议先调用 query_user_reservations 查记录获取ID。
    限制：每天最多取消2次。

    参数:
    - reservation_id: 预约单ID（19位雪花ID，从 query_user_reservations 返回的 `预约单ID` 获取）。有则直接取消，最快。
    - query_date: 预约日期，格式 YYYY-MM-DD。reservation_id 为空时必填，用于匹配预约记录。
    - seat_label: 座位号（如 "050"）。reservation_id 为空时必填。
    - state: 系统自动注入，无需传入。

    返回: 取消成功/失败的消息。常见失败：已达每日取消上限(2次)、预约已生效无法取消、预约单不存在。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    
    if not reservation_id and (not query_date or not seat_label):
        return "【错误提示】：请提供具体的预约单ID，或者提供预约日期和座位号，以便在后台定位您的预约订单。"

    print(f"--- [自习室取消预约] 开始处理退订事务... ---")

    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：获取自习室登录会话失败: {str(e)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()

        target_url = f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}"
        try:
            page.goto(target_url, timeout=12000)
            page.wait_for_load_state("networkidle")

            target_reservation_id = reservation_id

            # 自动匹配退订 ID 模式
            if not target_reservation_id:
                index_path = "/jsq/static/frontApi/user/history/1/15"
                eval_index_js = f"async () => {{ const response = await fetch('{index_path}', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json', 'token': '{creds['token']}', 'X-hmac-request-key': '{creds['hmac']}', 'X-request-date': '{creds['xdate']}', 'X-request-id': '{creds['xid']}', 'loginType': 'PC' }}, body: JSON.stringify({{}}) }}); return await response.json(); }}"
                index_json = page.evaluate(eval_index_js)
                
                page_list = index_json.get("data", {}).get("pageList", []) if isinstance(index_json.get("data"), dict) else []
                for order in page_list:
                    o_date = order.get("date")
                    o_label = order.get("seatLabel") or order.get("seatNo")
                    o_status = order.get("statusName", "")
                    
                    if o_date == query_date and o_label == seat_label and ("待" in o_status or "进行" in o_status):
                        target_reservation_id = order.get("id")
                        break
                
                if not target_reservation_id:
                    browser.close()
                    return f"【取消失败】：未在您的有效账单中找到【{query_date}】第【{seat_label}号】座位的待签到订单。"

            # 🚀 完美匹配：执行对齐 ham 实现的 cancel POST 请求 [1.2, 3.1]
            cancel_path = f"/jsq/static/frontApi/make/cancel/{target_reservation_id}"
            eval_cancel_js = f"async () => {{ const response = await fetch('{cancel_path}', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json', 'token': '{creds['token']}', 'X-hmac-request-key': '{creds['hmac']}', 'X-request-date': '{creds['xdate']}', 'X-request-id': '{creds['xid']}', 'loginType': 'PC' }}, body: JSON.stringify({{}}) }}); return await response.json(); }}"
            
            res_json = page.evaluate(eval_cancel_js)
            browser.close()

            if res_json.get("status"):
                return f"🎉 【取消成功】：您已成功退订预约单 `{target_reservation_id}`（对应的座位和时间段已释放）。"
            else:
                return f"❌ 【取消失败】：学校座位系统返回拒绝原因：'{res_json.get('message', '预约已生效或已被他人取消')}'。"

        except Exception as e:
            browser.close()
            return f"【系统错误】：执行取消事务时发生未知异常: {str(e)}"


# ==================== 6. 查询当前使用中座位 ====================
@tool
def get_current_usage(
    state: Annotated[dict, InjectedState] = None
) -> str:
    """查询当前正在使用中的座位（已签到入座状态），返回位置、时段、预约单ID等信息。

    用途：确认自己当前在哪个座位、还有多久结束、获取签退所需信息。
    调用时机：用户问"我现在在哪个座位"、"我的座位还有多久"、"帮我签退"（先查再签退）时调用。
    区别于 query_user_reservations：本工具只查「已签到入座」状态，query_user_reservations 查「已预约但可能未签到」。

    参数:
    - state: 系统自动注入，无需传入。

    返回: 当前使用中座位的完整信息（房间名、座位号、日期、时段、预约单ID），或提示无正在使用的座位。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    print("--- [当前使用] 正在查询... ---")

    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：{str(e)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        try:
            page.goto(f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}", timeout=12000)
            page.wait_for_load_state("networkidle")
            eval_js = f"""
            async () => {{
                const r = await fetch('/jsq/static/frontApi/user/currentUseMake', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'token': '{creds["token"]}',
                        'X-hmac-request-key': '{creds["hmac"]}', 'X-request-date': '{creds["xdate"]}',
                        'X-request-id': '{creds["xid"]}', 'loginType': 'PC' }},
                    body: JSON.stringify({{}})
                }});
                return await r.json();
            }}
            """
            res = page.evaluate(eval_js)
            browser.close()
            if not res.get("status"):
                return f"【查询失败】：{res.get('message', '鉴权失效')}"
            data = res.get("data", {})
            if not data:
                return "📭 当前没有正在使用中的座位。"
            return (
                f"🟢 【正在使用】\n"
                f"  位置: {data.get('roomName','')} {data.get('seatLabel','')}号\n"
                f"  日期: {data.get('date','')} | {data.get('beginTime','')}~{data.get('endTime','')}\n"
                f"  预约单ID: `{data.get('id','')}`"
            )
        except Exception as e:
            browser.close()
            return f"【系统错误】：{str(e)}"


# ==================== 7. 结束使用（签退） ====================
@tool
def stop_library_usage(
    state: Annotated[dict, InjectedState] = None
) -> str:
    """结束当前正在使用的座位（签退释放），将座位归还供他人预约。

    用途：提前离开图书馆时签退，释放座位。
    调用时机：用户说"我要走了"、"签退"、"结束使用"、"释放座位"时调用。
    前置条件（建议）：先调用 get_current_usage 确认当前确实有在使用中的座位，避免空操作。
    注意：签退后无法撤销，请确认用户确实要离开后再调用。

    参数:
    - state: 系统自动注入，无需传入。

    返回: 签退成功/失败的消息。"""
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])
    print("--- [结束使用] 正在签退... ---")

    try:
        creds = _harvest_library_session(raw_cookies)
    except Exception as e:
        return f"【系统错误】：{str(e)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()
        try:
            page.goto(f"https://seat.lib.whu.edu.cn/seat/#/login?token={creds['jwt_token']}", timeout=12000)
            page.wait_for_load_state("networkidle")
            eval_js = f"""
            async () => {{
                const r = await fetch('/jsq/static/frontApi/make/stop', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'token': '{creds["token"]}',
                        'X-hmac-request-key': '{creds["hmac"]}', 'X-request-date': '{creds["xdate"]}',
                        'X-request-id': '{creds["xid"]}', 'loginType': 'PC' }},
                    body: JSON.stringify({{}})
                }});
                return await r.json();
            }}
            """
            res = page.evaluate(eval_js)
            browser.close()
            if res.get("status"):
                return "🎉 【签退成功】座位已释放！"
            return f"❌ 【签退失败】：{res.get('message', '未知错误')}"
        except Exception as e:
            browser.close()
            return f"【系统错误】：{str(e)}"