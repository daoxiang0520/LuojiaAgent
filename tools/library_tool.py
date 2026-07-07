# tools/library_tool.py

import time
import uuid
import requests
from langchain_core.tools import tool

# ==================== 武汉大学图书馆分馆 ID 映射字典 ====================
LIBRARY_MAPPING = {
    "总馆": "1812737769937670144",
    "主馆": "1812737769937670144",
    
    "信息分馆": "1812738485913751552",
    "信息学部分馆": "1812738485913751552",
    
    "工学分馆": "1812738878798401536",
    "工学部分馆": "1812738878798401536",
    
    "医学分馆": "1812738878798401536", # 依据抓包数据暂时对齐工学部ID
    "医学部分馆": "1812738878798401536"
}

@tool
def query_library_seats(token: str, hmac_key: str, query_date: str, library_name: str = "总馆") -> str:
    """查询武汉大学图书馆各个分馆在指定日期的自习室/座位空闲余量。

    Args:
        token: 选座系统所需的 Token（可从登录抓包中获取的 48位 token 字符串）。
        hmac_key: 动态请求签名 X-hmac-request-key。
        query_date: 需要查询的日期，格式为 'YYYY-MM-DD'，例如 '2026-07-07'。
        library_name: 想要查询的馆区，可选值有: '总馆', '信息分馆', '工学分馆', '医学分馆'。
    """
    # 1. 核心：通过字典自动将中文馆名转化为真实的 19位 接口 ID
    # 模糊匹配：如果输入含有“信息”，自动归类到信息分馆；如果没匹配到，默认查总馆
    matched_id = "1812737769937670144" # 默认总馆ID
    target_name = "总馆"
    
    for name, b_id in LIBRARY_MAPPING.items():
        if name in library_name:
            matched_id = b_id
            target_name = name
            break
            
    print(f"--- [自习室查询] 识别到分馆名称: '{library_name}'，自动匹配真实大楼ID: {matched_id} ---")
    
    # 2. 拼接接口 URL
    url = f"https://seat.lib.whu.edu.cn/jsq/static/frontApi/res/findRoomDuration/{matched_id}/{query_date}"
    
    current_timestamp = str(int(time.time() * 1000))
    random_uuid = str(uuid.uuid4())
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Host": "seat.lib.whu.edu.cn",
        "Origin": "https://seat.lib.whu.edu.cn",
        "Referer": f"https://seat.lib.whu.edu.cn/seat/?token={token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "token": token,
        "X-hmac-request-key": hmac_key,
        "X-request-date": current_timestamp,
        "X-request-id": random_uuid,
        "loginType": "PC"
    }
    
    payload = {
        "beginMinute": 492, # 早上 8:12 左右
        "currentPage": 1,
        "endMinute": 0,
        "floorId": 0,
        "minMinute": 0,
        "pageSize": 12,
        "power": False,
        "roomType": False,
        "sortField": "",
        "sortType": "",
        "windows": False
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            res_json = response.json()
            
            if not res_json.get("status"):
                return f"【系统提示】：图书馆系统未能成功返回数据，原因：{res_json.get('message', '鉴权签名错误')}"
            
            data_body = res_json.get("data", {})
            room_list = data_body.get("pageList", [])
            
            if not room_list:
                return f"系统提示：在 {query_date} 未查询到【{target_name}】任何自习室余量信息。"
                
            # 数据清洗：提炼核心状态，剔除无效 null，压缩 Token
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
            
        elif response.status_code == 401 or response.status_code == 403:
            return "【凭证失效】：选座 Token 或 HMAC 签名已过期，请在网页端重新获取。"
        else:
            return f"【系统异常】：图书馆选座接口请求失败，状态码: {response.status_code}"
            
    except Exception as e:
        return f"【网络异常】：无法连接到图书馆选座系统，原因为: {str(e)}"