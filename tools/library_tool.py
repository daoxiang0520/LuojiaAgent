# tools/library_tool.py

import time
import re
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
    "医学分馆": "1812738878798401536",
    "医学部分馆": "1812738878798401536"
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
    """查询武汉大学图书馆各个分馆在指定日期的自习室/座位整体空闲大盘余量。"""
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
    """查询指定自习室区域（如 A1座位区）内所有具体座位（包含空闲🟢和占用🔴）的横向排布分布图。"""
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
    """自动将中文座位号转换为 19位 物理 ID，调用学校 App 受信任绿色通道预约座位。
    如遇滑块验证码要求，自动调用 TAC 验证码破解引擎绕过。"""
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

    # 预约请求体
    reserve_path = f"/jsq/static/frontApi/make/freeBook/{matched_seat_uuid}/{query_date}/{begin_minute}/{end_minute}"

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
    """查询当前登录用户在自习室选座系统中的历史及当前有效预约单记录，用于获取退订所需的 reservation_id。"""
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

            api_path = "/jsq/static/frontApi/reserve/index"
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
                    body: JSON.stringify({{
                        "currentPage": 1,
                        "pageSize": 10
                    }})
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
    """取消用户在武汉大学图书馆已预约、但尚未入座签到的某个有效座位。"""
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
                index_path = "/jsq/static/frontApi/reserve/index"
                eval_index_js = f"async () => {{ const response = await fetch('{index_path}', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json', 'token': '{creds['token']}', 'X-hmac-request-key': '{creds['hmac']}', 'X-request-date': '{creds['xdate']}', 'X-request-id': '{creds['xid']}', 'loginType': 'PC' }}, body: JSON.stringify({{ 'currentPage': 1, 'pageSize': 15 }}) }}); return await response.json(); }}"
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
            cancel_path = f"/jsq/static/frontApi/reserve/cancel/{target_reservation_id}"
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
    """查询当前登录用户在图书馆正在使用中的座位（已签到入座），返回座位信息和剩余时间。"""
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
    """结束当前正在使用的座位（签退释放）。调用前建议先用「查询当前使用」确认。"""
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