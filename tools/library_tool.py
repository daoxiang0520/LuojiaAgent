# tools/library_tool.py
# 武汉大学图书馆座位系统全套工具
# 架构：state 缓存优先 → HMAC 直接 HTTP → 过期才走浏览器 harvest → 更新 state

import time
import re
import json
import uuid
import hmac as _hmac
import hashlib
import base64
import urllib3
import requests
from playwright.sync_api import sync_playwright
from langchain_core.tools import tool
from typing import Annotated
from langgraph.prebuilt import InjectedState
from .captcha_solver import solve_captcha

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── sessionStorage key 前缀（实测为 jsq_p-） ──
_SSTOKEN = "jsq_p-token"
_SSSYSINFO = "jsq_p-systemInfo"

# ── hmacKey 解密（app.js I.decrypt: AES-CBC, key="server_date_time", IV="client_date_time"）──
def _get_hmac_key(raw_hmac_key: str) -> bytes:
    """AES-CBC 解密 hmacKey，失败则回退到直接 base64 decode"""
    try:
        from Cryptodome.Cipher import AES as _AES
        from Cryptodome.Util.Padding import unpad as _unpad
        ct = base64.b64decode(raw_hmac_key)
        cipher = _AES.new(b"server_date_time", _AES.MODE_CBC, b"client_date_time")
        return _unpad(cipher.decrypt(ct), _AES.block_size)
    except Exception:
        return base64.b64decode(raw_hmac_key)

# ==================== 分馆 ID 映射 ====================
LIBRARY_MAPPING = {
    "总馆": "1812737769937670144",     "主馆": "1812737769937670144",
    "信息分馆": "1812738485913751552",   "信息学部分馆": "1812738485913751552",
    "工学分馆": "1812738878798401536",   "工学部分馆": "1812738878798401536",
    "医学分馆": "1812739190351302656",   "医学部分馆": "1812739190351302656",
}


# ==================== HMAC 签名（纯 Python） ====================
def _make_signed_headers(token: str, hmac_key_val: str, method: str = "POST") -> dict:
    """用 token + hmacKey 生成带 HMAC-SHA256 签名的请求头"""
    key = _get_hmac_key(hmac_key_val)
    rid = str(uuid.uuid4())
    ts = str(int(time.time() * 1000))
    sign_str = f"seat::{rid}::{ts}::{method.upper()}"
    sig = _hmac.new(key, sign_str.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "token": token, "loginType": "PC",
        "X-request-id": rid, "X-request-date": ts, "X-hmac-request-key": sig,
    }


# ==================== Layer 1：直接 HTTP 调用（使用 state 缓存凭证） ====================
def _call_api_direct(state: dict, path: str, body: dict = None, method: str = "POST") -> dict:
    """用 state 里缓存的 library_token + library_hmac_key 直接调 API，~0.5s"""
    c = state.get("cookies", {})
    token = c.get("library_token", "")
    hmac_key = c.get("library_hmac_key", "")

    if not token or not hmac_key:
        raise ValueError("state 中缺少 library_token 或 library_hmac_key")

    headers = _make_signed_headers(token, hmac_key, method)
    url = f"https://seat.lib.whu.edu.cn{path}"
    payload = json.dumps(body or {}, ensure_ascii=False)

    for attempt in range(3):
        try:
            resp = requests.post(url, data=payload, headers=headers, timeout=15, verify=False)
            break
        except requests.exceptions.RequestException:
            if attempt == 2:
                raise ConnectionError(f"图书馆 API 连接失败（重试3次）")
            time.sleep(1)

    try:
        result = resp.json()
    except json.JSONDecodeError:
        raise ValueError(f"API 返回非 JSON: {resp.text[:200]}")

    # 判断 token 是否过期
    if not result.get("status"):
        msg = str(result.get("message", ""))
        if any(kw in msg for kw in ["登录", "过期", "token", "Token", "鉴权", "失效", "认证"]):
            raise PermissionError(f"Token 已过期: {msg}")

    return result


# ==================== Layer 2：浏览器 harvest 刷新凭证 + 写入 state ====================
import threading
_harvest_lock = threading.Lock()

def _harvest_library_session(state: dict) -> None:
    """
    用 state 里的 raw_cookies（含 CASTGC）走 CAS SSO → 图书馆 OAuth → SPA，
    从 sessionStorage 提取 token + hmac_key，直接写入 state["cookies"]。

    带互斥锁，防止并发调用时开多个浏览器互相踩。
    """
    # 如果已有其他线程在 harvest，等它完成即可
    if not _harvest_lock.acquire(blocking=False):
        print("[Harvest] 等待其他线程完成 harvest...")
        _harvest_lock.acquire(blocking=True)
        # 检查 state 是否已被其他线程更新
        c = state.get("cookies", {})
        if c.get("library_token") and c.get("library_hmac_key"):
            print("[Harvest] state 已被其他线程更新，跳过")
            _harvest_lock.release()
            return
    try:
        _do_harvest(state)
    finally:
        _harvest_lock.release()


def _do_harvest(state: dict) -> None:
    cookies = state.get("cookies", {})
    raw_cookies = cookies.get("library_cookie", [])

    if not raw_cookies:
        raise RuntimeError("state 中无 raw_cookies，请调用 login_to_whu_portal 重新登录")

    captured = {"token": "", "jwt_token": "", "hmac_key": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(raw_cookies)
        page = context.new_page()

        # Step 1: CAS SSO → 图书馆 OAuth → JWT
        oauth_url = "https://seat.lib.whu.edu.cn/rem/static/sso/login?redirectUrl=https://seat.lib.whu.edu.cn/seat"
        page.goto(oauth_url, timeout=30000)
        try:
            page.wait_for_url(lambda u: "token=" in u, timeout=30000)
            m = re.search(r"token=([^&]+)", page.url)
            captured["jwt_token"] = m.group(1) if m else ""
            print(f"[Harvest] JWT: {captured['jwt_token'][:20]}...")
        except Exception as e:
            browser.close()
            raise TimeoutError(f"CAS SSO 到图书馆失败（CASTGC 可能已过期，请重新登录）: {e}")

        if not captured["jwt_token"]:
            browser.close()
            raise RuntimeError("未能从 OAuth 重定向中提取 JWT")

        # Step 2: CAS 重定向已经停在 SPA + JWT，SPA 自动处理 token
        # 不能再 goto（JWT 一次性），只需等 SPA 完成 auth/cas → sessionStorage
        page.wait_for_load_state("networkidle", timeout=30000)

        # 等待 token（auth/cas 后写入 jsq_p-token）
        for _ in range(100):
            token = page.evaluate(f"() => sessionStorage.getItem('{_SSTOKEN}')")
            if token:
                captured["token"] = token
                break
            time.sleep(0.15)

        # 等待 systemInfo（jsq_p-systemInfo）
        if captured["token"]:
            print(f"[Harvest] token: {captured['token'][:20]}...")
            for _ in range(60):
                raw = page.evaluate(f"() => sessionStorage.getItem('{_SSSYSINFO}')")
                if raw:
                    try:
                        sys_info = json.loads(raw)
                        hk = sys_info.get("hmacKey", "")
                        if hk:
                            captured["hmac_key"] = hk
                            print(f"[Harvest] hmacKey: {hk[:20]}...")
                            break
                    except Exception:
                        pass
                time.sleep(0.2)
            if not captured["hmac_key"]:
                print("[Harvest] WARN: hmacKey 未获取到")

        # Step 4: 更新 raw_cookies
        all_cookies = context.cookies()
        browser.close()

    if not captured["token"]:
        raise RuntimeError("sessionStorage.token 为空，SPA CAS 认证未完成，请重试")

    cookies["library_token"] = captured["token"]
    cookies["library_jwt_token"] = captured["jwt_token"]
    cookies["library_hmac_key"] = captured["hmac_key"]
    cookies["library_cookie"] = all_cookies

    print(f"[Harvest] state 已更新: token={'OK' if captured['token'] else 'NO'}, "
          f"hmac_key={'OK' if captured['hmac_key'] else 'NO'}")


# ==================== 统一入口：缓存优先 → 过期 harvest → 重试 ====================
def _call_api(state: dict, path: str, body: dict = None, method: str = "POST") -> dict:
    """
    Layer 1: 尝试用 state 缓存的 token+hmac_key 直接 HTTP 调用
    Layer 2: token 过期 → _harvest_library_session 刷新凭证 → 写回 state → 重试 Layer 1
    Layer 3: harvest 也失败 → 提示重新登录
    """
    # Layer 1
    try:
        result = _call_api_direct(state, path, body, method)
        print("[API] Layer 1 直接 HTTP 成功")
        return result
    except (ValueError, PermissionError) as e:
        print(f"[API] Layer 1 失败 ({e})，进入 harvest...")

    # Layer 2
    try:
        _harvest_library_session(state)
        result = _call_api_direct(state, path, body, method)
        print("[API] Layer 2 harvest + 重试成功")
        return result
    except TimeoutError as e:
        raise RuntimeError(
            f"【会话已过期】CASTGC 票据已失效，请重新点击「🔐 点击登录」完成认证。\n{e}"
        )
    except Exception as e:
        raise RuntimeError(f"【图书馆 API 调用失败】{e}")


# ==================== 1. 查询分馆座位大盘 ====================
@tool
def query_library_seats(
    query_date: str,
    library_name: str = "总馆",
    begin_time: str = "now",
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """查询武汉大学图书馆某个分馆在指定日期的所有自习区域座位空闲概览。

    用途：用户想了解某个图书馆整体座位情况时调用。返回各楼层各区域的名称、总座位数、空闲数和区域ID。
    调用时机：用户问"总馆明天有座位吗"、"信息分馆还有空位吗"等。这是座位查询的第一步，后续如需看具体座位排布，再用 query_empty_seats_in_area。

    参数:
    - query_date: 查询日期，格式 YYYY-MM-DD（如 "2026-07-10"）。用户说"明天"时需要根据系统时间锚点换算。
    - library_name: 分馆名称。支持: 总馆/主馆、信息分馆/信息学部分馆、工学分馆/工学部分馆、医学分馆/医学部分馆。默认"总馆"。
    - begin_time: 起始时间，格式 HH:MM（如 "08:12"）或 "now"（当前时间取整到下一个时段）。默认 "now"。
    - state: 系统自动注入的凭证，无需传入。

    返回: 各区域列表，每行含楼层、区域名、总座位、空闲数、区域ID（后续查座位图或预约需要此ID）。"""
    matched_id = "1812737769937670144"
    target_name = "总馆"
    for name, b_id in LIBRARY_MAPPING.items():
        if name in library_name:
            matched_id = b_id
            target_name = name
            break

    # 计算 beginMinute
    if begin_time == "now":
        import datetime as _dt
        now = _dt.datetime.now()
        begin_minute = now.hour * 60 + now.minute
    else:
        try:
            h, m = map(int, begin_time.split(":"))
            begin_minute = h * 60 + m
        except Exception:
            begin_minute = 492

    print(f"--- [座位大盘] {target_name} {query_date} beginMinute={begin_minute} ---")

    path = f"/jsq/static/frontApi/res/findRoomDuration/{matched_id}/{query_date}"
    body = {
        "beginMinute": begin_minute, "currentPage": 1, "endMinute": 0,
        "floorId": 0, "minMinute": 0, "pageSize": 200,
        "power": False, "roomType": False, "sortField": "", "sortType": "", "windows": False,
    }

    try:
        res_json = _call_api(state, path, body)
    except Exception as e:
        return f"【查询失败】：{e}"

    if not res_json.get("status"):
        return f"【查询失败】：{res_json.get('message', '鉴权错误')}"

    room_list = res_json.get("data", {}).get("pageList", []) if isinstance(res_json.get("data"), dict) else []
    if not room_list:
        return f"系统提示：在 {query_date} 未查询到【{target_name}】任何自习室余量信息。"

    lines = [f"🏢 武汉大学图书馆【{target_name}】{query_date} 座位空闲情况："]
    for room in room_list:
        lines.append(
            f"  • 【{room.get('floorName', '1楼')}】{room.get('name')} | "
            f"总座位: {room.get('seatTotal')} | 空闲: {room.get('seatFree')} | 区域ID: `{room.get('id')}`"
        )
    return "\n".join(lines)


# ==================== 2. 查询区域座位图 ====================
@tool
def query_empty_seats_in_area(
    query_date: str,
    area_id: str,
    begin_time: str = "08:12",
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """查询指定自习区域内所有座位的实时状态，按排(Row)展示空闲/占用分布图。

    用途：用户想选一个具体座位时，先调用此工具查看该区域每排每座的空闲情况，然后选一个空闲座位号去预约。
    调用时机：在 query_library_seats 之后，用户说"看看A1区有哪些空位"、"3楼自主学习区还有什么座位"时调用。
    前置条件：需要先从 query_library_seats 的返回结果中获取目标区域的 area_id（19位数字）。

    参数:
    - query_date: 查询日期，格式 YYYY-MM-DD。
    - area_id: 区域ID（19位雪花ID，从 query_library_seats 返回的 `区域ID` 字段获取）。
    - begin_time: 查询起始时间，格式 HH:MM（如 "08:12"），默认 "08:12"。
    - state: 系统自动注入，无需传入。

    返回: 按排(行)展示的座位图，每个座位显示座位号和空闲/占用状态。"""
    try:
        h, m = map(int, begin_time.split(":"))
        begin_minute = h * 60 + m
    except Exception:
        begin_minute = 492

    print(f"--- [座位图] area={area_id} date={query_date} ---")

    path = f"/jsq/static/frontApi/res/freeSeatIdsDuration/{area_id}/{query_date}"
    body = {"beginMinute": begin_minute, "endMinute": 0}

    try:
        res_json = _call_api(state, path, body)
    except Exception as e:
        return f"【查询失败】：{e}"

    if not res_json.get("status"):
        return f"【查询失败】：{res_json.get('message', '未知错误')}"

    seats_dict = res_json.get("data", {})
    if not isinstance(seats_dict, dict) or not seats_dict:
        return f"系统提示：在 {query_date} 该区域内没有可用的座位数据。"

    row_map = {}
    for seat in seats_dict.values():
        label = seat.get("label", "??")
        name_coord = seat.get("name", "0行0列")
        is_free = seat.get("status") == "FREE"
        icon = "🟢" if is_free else "🔴"

        row_match = re.search(r"(\d+)行", name_coord)
        row_num = int(row_match.group(1)) if row_match else 999
        row_map.setdefault(row_num, []).append(f"{label}号{icon}")

    lines = [f"自习室区域 {area_id} 实时选座图（🟢空闲 | 🔴占用）："]
    for row in sorted(row_map.keys()):
        row_map[row].sort(key=lambda x: int(re.search(r"(\d+)", x).group(1)) if re.search(r"(\d+)", x) else 999)
        lines.append(f"  * 第 {row} 行：{' | '.join(row_map[row])}")
    return "\n".join(lines)


# ==================== 3. 座位预约 ====================
@tool
def reserve_library_seat(
    query_date: str,
    library_name: str,
    area_id: str,
    seat_label: str,
    begin_time: str,
    end_time: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """预约图书馆座位。自动完成座位号到物理ID转换，遇到滑块验证码自动破解重试。

    用途：用户选好座位后执行预约。全自动流程：座位号对齐 → 提交预约 → 如触发验证码则自动破解 → 带token重试。
    调用时机：用户已通过 query_library_seats + query_empty_seats_in_area 选定了目标区域和座位号，明确说"帮我预约XX号座位"时调用。
    前置条件：需要 area_id（从 query_library_seats 获取）和 seat_label（从 query_empty_seats_in_area 的座位图中选一个空闲座位号）。

    参数:
    - query_date: 预约日期，格式 YYYY-MM-DD。
    - library_name: 分馆名称（总馆/信息分馆/工学分馆/医学分馆）。
    - area_id: 区域ID（19位雪花ID）。
    - seat_label: 座位号（如 "005"、"163"），即桌贴号。
    - begin_time: 开始时间，格式 HH:MM（如 "08:00"）。
    - end_time: 结束时间，格式 HH:MM（如 "12:00"）。
    - state: 系统自动注入，无需传入。

    返回: 预约成功/失败的消息。"""
    cookies = state.get("cookies", {})
    username = "2025302114221"
    jwt = cookies.get("library_jwt_token", "")
    if jwt:
        try:
            payload = json.loads(base64.b64decode(jwt.split(".")[1] + "==").decode())
            username = payload.get("sub", username)
        except Exception:
            pass

    try:
        bh, bm = map(int, begin_time.split(":"))
        eh, em = map(int, end_time.split(":"))
        begin_minute = bh * 60 + bm
        end_minute = eh * 60 + em
    except Exception:
        return "【格式错误】：时间格式必须为 'HH:MM'。"

    print(f"--- [预约] {seat_label}号 {begin_time}-{end_time} ---")

    # Step 1: 获取座位映射
    path_map = f"/jsq/static/frontApi/res/freeSeatIdsDuration/{area_id}/{query_date}"
    try:
        map_json = _call_api(state, path_map, {"beginMinute": begin_minute, "endMinute": 0})
    except Exception as e:
        return f"【预约失败】：获取座位映射出错 - {e}"

    matched_seat_uuid = ""
    for uuid_key, info in map_json.get("data", {}).items():
        if info.get("label") == seat_label:
            matched_seat_uuid = uuid_key
            break
    if not matched_seat_uuid:
        return f"【预约失败】：未找到 {seat_label}号座位，可能已被占用。"

    print(f"[OK] 座位对齐: {seat_label} -> {matched_seat_uuid[:16]}...")

    # Step 2: 提交预约
    reserve_path = f"/jsq/static/frontApi/make/freeBook/{matched_seat_uuid}/{query_date}/{begin_minute}/{end_minute}"
    try:
        res_json = _call_api(state, reserve_path, {})
    except Exception as e:
        return f"【预约失败】：{e}"

    msg = res_json.get("message", "")

    # Step 3: 触发验证码 → 自动破解 → 带 token 重试
    if not res_json.get("status") and ("验证" in msg or "滑块" in msg or "captcha" in msg.lower()):
        print(f"[!] 触发验证码: {msg}")
        try:
            captcha_result = solve_captcha(username=username, max_retries=3)
            if captcha_result.get("success"):
                cap_token = captcha_result.get("data", {}).get("token", "")
                if cap_token:
                    print("[OK] 验证码破解成功，带 token 重试...")
                    res_json = _call_api(state, f"{reserve_path}?capToken={cap_token}", {})
        except Exception as ce:
            print(f"[!] 验证码异常: {ce}")

    if res_json.get("status"):
        return f"【预约成功】{query_date} {begin_time}~{end_time} {seat_label}号座位！"
    return f"【预约失败】：{res_json.get('message', '未知错误')}。"


# ==================== 4. 查询预约记录 ====================
@tool
def query_user_reservations(
    query_type: str = "all",
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """查询用户的图书馆预约记录，返回预约单列表（含预约单ID、日期、时段、座位号、状态）。

    用途：查看当前有哪些预约、获取退订所需的 reservation_id、确认预约是否生效。
    调用时机：用户问"我的预约"、"查看我的预约记录"、"帮我取消预约"（先查记录获取ID再取消）时调用。
    前置条件：需要先登录（login_to_whu_portal）。

    参数:
    - query_type: "active"（默认，仅返回待签到/使用中的有效预约）或 "all"（含历史已取消/已结束）。
    - state: 系统自动注入，无需传入。

    返回: 预约记录列表，每条含预约单ID、日期、时间、位置、状态。"""
    print("--- [预约记录] 查询 ---")

    path = "/jsq/static/frontApi/user/history/0/50"
    try:
        res_json = _call_api(state, path, {})
    except Exception as e:
        return f"【查询失败】：{e}"

    if not res_json.get("status"):
        return f"【查询失败】：{res_json.get('message', '鉴权失败，请重新登录')}"
    data = res_json.get("data", {}) if isinstance(res_json.get("data"), dict) else {}
    page_list = data.get("list", data.get("pageList", []))
    if not page_list:
        return "系统提示：当前没有任何预约记录（含历史）。"

    STATUS_CN = {"CANCEL": "已取消", "STOP": "已结束", "LEAVE_EARLY": "早退签退",
                 "已结束": "已结束", "已取消": "已取消", "违规已签退": "违规已签退", "已完成": "已完成"}
    finished_codes = {"CANCEL", "STOP", "LEAVE_EARLY", "已结束", "已取消", "违规已签退", "已完成"}
    active_items, history_items = [], []

    for item in page_list:
        code = item.get("status", item.get("statusName", "未知"))
        s = STATUS_CN.get(code, code)
        date = item.get("date") or item.get("makeDateStr", "?")
        begin = item.get("beginTime") or item.get("makeBeginStr", "?")
        end = item.get("endTime") or item.get("makeEndStr", "?")
        line = (
            f"  * {s} | {date} | {begin}~{end} | "
            f"{item.get('roomName', '')} {item.get('seatLabel', '?')}号 | ID: `{item.get('id')}`"
        )
        (history_items if code in finished_codes else active_items).append(line)

    lines = ["武汉大学图书馆 个人预约记录："]
    total = len(page_list)

    if query_type == "active":
        lines.append(f"\n📌 进行中/待处理 ({len(active_items)} 条)：")
        lines.extend(active_items or ["  无"])
        if history_items:
            lines.append(f"\n📋 历史记录 ({len(history_items)} 条，已隐藏，使用 query_type='all' 查看)")
    else:
        if active_items:
            lines.append(f"\n📌 进行中/待处理 ({len(active_items)} 条)：")
            lines.extend(active_items)
        if history_items:
            lines.append(f"\n📋 历史记录 ({len(history_items)} 条)：")
            lines.extend(history_items)

    lines.append(f"\n📊 共 {total} 条记录")
    return "\n".join(lines)


# ==================== 5. 取消预约 ====================
@tool
def cancel_library_reservation(
    reservation_id: str = None,
    query_date: str = None,
    seat_label: str = None,
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """取消一个尚未入座的图书馆座位预约，释放座位供他人使用。

    用途：退订预约。支持两种定位方式：直接传 reservation_id；或传 query_date + seat_label 自动查找。
    调用时机：用户说"取消预约"、"退订座位"、"我不去了帮我取消"时调用。
    前置条件：如果用户没有提供 reservation_id，建议先调用 query_user_reservations 查记录获取ID。
    限制：每天最多取消2次。

    参数:
    - reservation_id: 预约单ID（19位雪花ID）。有则直接取消，最快。
    - query_date: 预约日期，格式 YYYY-MM-DD。reservation_id 为空时必填。
    - seat_label: 座位号。reservation_id 为空时必填。
    - state: 系统自动注入，无需传入。

    返回: 取消成功/失败的消息。"""
    target_id = reservation_id

    if not target_id and (not query_date or not seat_label):
        return "【错误】：请提供 reservation_id，或 query_date + seat_label。"

    print("--- [取消预约] ---")

    # 无 ID 时自动查找
    if not target_id:
        try:
            history = _call_api(state, "/jsq/static/frontApi/user/history/0/100", {})
        except Exception as e:
            return f"【查询失败】：{e}"

        page_list = history.get("data", {}).get("pageList", []) if isinstance(history.get("data"), dict) else []
        for order in page_list:
            if (order.get("date") == query_date
                and (order.get("seatLabel") or order.get("seatNo")) == seat_label
                and order.get("status", order.get("statusName", "")) not in {"CANCEL", "STOP", "LEAVE_EARLY", "已结束", "已取消"}):
                target_id = order.get("id")
                break
        if not target_id:
            return f"【取消失败】：未找到 {query_date} {seat_label}号 的有效预约。"

    cancel_path = f"/jsq/static/frontApi/make/cancel/{target_id}"
    try:
        res_json = _call_api(state, cancel_path, {})
    except Exception as e:
        return f"【取消失败】：{e}"

    if res_json.get("status"):
        return f"【取消成功】预约单 `{target_id}` 已退订，座位已释放。"
    return f"【取消失败】：{res_json.get('message', '未知错误')}。"


# ==================== 6. 查询当前使用中座位 ====================
@tool
def get_current_usage(
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """查询当前正在使用中的座位（已签到入座状态），返回位置、时段、预约单ID等信息。

    用途：确认自己当前在哪个座位、还有多久结束、获取签退所需信息。
    调用时机：用户问"我现在在哪个座位"、"我的座位还有多久"、"帮我签退"（先查再签退）时调用。
    区别于 query_user_reservations：本工具只查「已签到入座」状态。

    参数:
    - state: 系统自动注入，无需传入。

    返回: 当前使用中座位的完整信息，或提示无正在使用的座位。"""
    print("--- [当前使用] 查询 ---")

    try:
        res_json = _call_api(state, "/jsq/static/frontApi/user/currentUseMake", {})
    except Exception as e:
        return f"【查询失败】：{e}"

    if not res_json.get("status"):
        return f"【查询失败】：{res_json.get('message', '鉴权失效')}"

    data = res_json.get("data", {})
    if not data:
        return "当前没有正在使用中的座位。"

    return (
        f"【正在使用】\n"
        f"  位置: {data.get('roomName', '')} {data.get('seatLabel', '')}号\n"
        f"  日期: {data.get('date', '')} | {data.get('beginTime', '')}~{data.get('endTime', '')}\n"
        f"  预约单ID: `{data.get('id', '')}`"
    )


# ==================== 7. 结束使用（签退） ====================
@tool
def stop_library_usage(
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """结束当前正在使用的座位（签退释放），将座位归还供他人预约。

    用途：提前离开图书馆时签退，释放座位。
    调用时机：用户说"我要走了"、"签退"、"结束使用"、"释放座位"时调用。
    前置条件（建议）：先调用 get_current_usage 确认当前确实有在使用中的座位。
    注意：签退后无法撤销，请确认用户确实要离开后再调用。

    参数:
    - state: 系统自动注入，无需传入。

    返回: 签退成功/失败的消息。"""
    print("--- [签退] ---")

    try:
        res_json = _call_api(state, "/jsq/static/frontApi/make/stop", {})
    except Exception as e:
        return f"【签退失败】：{e}"

    if res_json.get("status"):
        return "【签退成功】座位已释放！"
    return f"【签退失败】：{res_json.get('message', '未知错误')}"
