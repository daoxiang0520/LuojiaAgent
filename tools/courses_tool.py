import requests
from langchain_core.tools import tool

@tool
def query_whu_schedule(cookie_str: str, begin_date: str, end_date: str) -> str:
    """查询武汉大学智慧珞珈系统的学生课表数据。

    Args:
        cookie_str: 登录智慧珞珈后获取的完整 Cookie 字符串（必须包含 PORTAL-TOKEN, JSESSIONID 等）。
        begin_date: 查询课表的开始日期，格式为 'YYYY-MM-DD'，例如 '2026-07-06'。
        end_date: 查询课表的结束日期，格式为 'YYYY-MM-DD'，例如 '2026-07-11'。
    """
    url = "https://zhlj.whu.edu.cn/whdxSchedule/getScheduleData"
    
    # 1. 填入你抓包获取的浏览器标头（Headers）
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": cookie_str, # 动态传入你的 Cookie，防止硬编码失效
        "Host": "zhlj.whu.edu.cn",
        "Origin": "https://zhlj.whu.edu.cn",
        "Referer": "https://zhlj.whu.edu.cn/newPc/index",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    }
    
    # 2. 构造 POST 载荷 (根据 74 字节的长度估算)
    # 学校接口通常需要开始日期和结束日期来拉取列表
    payload = {
        "beginDate": begin_date,
        "endDate": end_date
    }
    
    try:
        # 3. 发送 POST 请求
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            res_json = response.json()
            
            # 判断学校系统返回的状态标识
            if res_json.get("result") != 1:
                return f"【系统提示】：智慧珞珈系统未能成功返回数据，原因：{res_json.get('message', '未知错误')}"
            
            days_data = res_json.get("data", [])
            if not days_data:
                return f"系统提示：在 {begin_date} 至 {end_date} 期间未查询到任何课表数据。"
                
            # 4. 【核心】数据清洗（Data Slimming）
            # 原始数据有几十个 null 字段，我们只提取大模型关心的：日期、星期、课程名、老师、时间、地点。
            cleaned_lines = []
            for day in days_data:
                date_str = day.get("date")
                week_str = day.get("week")
                schedule_list = day.get("whdxScheduleVoList", [])
                
                # 如果当天没有课，直接跳过，节省大模型的上下文 Token
                if not schedule_list:
                    continue
                
                cleaned_lines.append(f"📅 {date_str} ({week_str}):")
                for item in schedule_list:
                    title = item.get("title", "未知课程")
                    # 提取老师名字（去掉多余前缀）
                    teacher = item.get("describeContent", "未知老师").replace("授课老师：", "")
                    start_time = item.get("beginHour", "待定")
                    address = item.get("address", "未知地点")
                    
                    cleaned_lines.append(f"  • 【{start_time}】 {title} | 教师: {teacher} | 地点: {address}")
            
            # 如果整周都没课
            if not cleaned_lines:
                return f"系统提示：在 {begin_date} 到 {end_date} 期间，您没有任何课程安排。"
                
            # 返回清洗、排版整齐后的文本
            return "\n".join(cleaned_lines)
            
        elif response.status_code == 401:
            return "【登录失效】：您的智慧珞珈认证 Cookie 已过期，请在网页端重新登录并提供新的 Cookie。"
        else:
            return f"【系统异常】：课表接口请求失败，状态码: {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        return f"【网络异常】：无法连接到武汉大学课表系统，原因为: {str(e)}"