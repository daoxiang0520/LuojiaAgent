# tools/courses_tool.py

import datetime
import requests
from langchain_core.tools import tool

@tool
def query_whu_schedule(cookie_str: str, query_date: str) -> str:
    """查询武汉大学智慧珞珈系统学生在指定日期（或该日期所在周）的课表数据。

    Args:
        cookie_str: 登录智慧珞珈后获取的完整 Cookie 字符串（必须包含 PORTAL-TOKEN, JSESSIONID 等）。
        query_date: 需要查询的日期（或该周内的任意一天），格式为 'YYYY-MM-DD'，例如 '2026-07-06'。
    """
    url = "https://zhlj.whu.edu.cn/whdxSchedule/getScheduleData"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Content-Length": "74", # 精准契合 74 字节
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Host": "zhlj.whu.edu.cn",
        "Origin": "https://zhlj.whu.edu.cn",
        "Referer": "https://zhlj.whu.edu.cn/newPc/index",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    }
    
    # ==================== 核心算法：自动计算 query_date 所在周的周日 ====================
    try:
        dt = datetime.datetime.strptime(query_date, "%Y-%m-%d")
        # dt.weekday() 在 Python 中周一是 0，周日是 6。
        # 我们计算该周周日的日期（智慧珞珈系统以周日作为一周的起点）
        offset = (dt.weekday() + 1) % 7
        sunday_date = dt - datetime.timedelta(days=offset)
        sunday_str = sunday_date.strftime("%Y-%m-%d")
        print(f"--- [自动对齐] 用户查询日期: {query_date}，已自动对齐该周周日: {sunday_str} ---")
    except Exception as e:
        return f"【格式错误提示】：您传入的日期格式不对，必须为 'YYYY-MM-DD'。原因：{str(e)}"
    # ===================================================================================

    # 完美拼装成 74 字节的真实请求负载
    payload = {
        "date": sunday_str,
        "dateType": 3,
        "priority": "",
        "searchTitle": "",
        "type": 1
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            res_json = response.json()
            
            if res_json.get("result") != 1:
                return f"【系统提示】：智慧珞珈系统未能成功返回数据，原因：{res_json.get('message', '未知错误')}"
            
            days_data = res_json.get("data", [])
            if not days_data:
                return f"系统提示：在 {sunday_str} 这一周未查询到任何课表数据。"
                
            # 数据清洗，只保留核心信息喂给大模型，节省 Token 消耗
            cleaned_lines = []
            for day in days_data:
                date_str = day.get("date")
                week_str = day.get("week")
                schedule_list = day.get("whdxScheduleVoList", [])
                
                if not schedule_list:
                    continue  # 当天没课直接跳过
                
                cleaned_lines.append(f"📅 {date_str} ({week_str}):")
                for item in schedule_list:
                    title = item.get("title", "未知课程")
                    teacher = item.get("describeContent", "未知老师").replace("授课老师：", "")
                    start_time = item.get("beginHour", "待定")
                    address = item.get("address", "未知地点")
                    
                    cleaned_lines.append(f"  • 【{start_time}】 {title} | 教师: {teacher} | 地点: {address}")
            
            if not cleaned_lines:
                return f"系统提示：您在 {sunday_str} 这周没有任何课程安排。"
                
            return "\n".join(cleaned_lines)
            
        elif response.status_code == 401:
            return "【登录失效】：您的智慧珞珈认证 Cookie 已过期，请重新登录并提供新的 Cookie。"
        else:
            return f"【系统异常】：课表接口请求失败，状态码: {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        return f"【网络异常】：无法连接到武汉大学课表系统，原因为: {str(e)}"