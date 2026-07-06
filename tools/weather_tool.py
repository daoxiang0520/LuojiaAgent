import requests
import time
from datetime import datetime
from langchain_core.tools import tool

# 内部辅助函数：用来将 API 的 ISO 8601 时间格式化为人性化的 AM/PM 及天数描述
def format_forecast_time(iso_time_str: str) -> str:
    """
    输入: "2026-07-07T15:00"
    输出: "明天下午 03:00 (PM)" 或 "今天上午 09:00 (AM)"
    """
    dt = datetime.fromisoformat(iso_time_str)
    now = datetime.now()
    
    # 1. 判断是否是明天（第二天）
    if dt.date() > now.date():
        day_prefix = "明天"
    else:
        day_prefix = "今天"
        
    # 2. 转换为 12 小时制并判断 AM/PM
    hour = dt.hour
    if hour == 0:
        ampm_str = "凌晨 12:00 (AM)"
    elif hour < 12:
        ampm_str = f"上午 {hour:02d}:00 (AM)"
    elif hour == 12:
        ampm_str = "中午 12:00 (PM)"
    else:
        # 下午时间转换，例如 15 点转为 3 点
        ampm_str = f"下午 {hour - 12:02d}:00 (PM)"
        
    return f"{day_prefix}{ampm_str}"


@tool
def get_whu_rain_forecast() -> str:
    """
    专门针对【武汉大学】（珞珈山校区）的精准降雨及温度预测工具。
    能够分析未来3小时内的即时降雨风险、未来12小时的下雨持续时间、起止时间（带AM/PM及日期转换），
    并提供具体的带伞提醒和基于温差的穿衣防晒建议。
    """
    lat, lon = 30.54, 114.36
    
    # 增加温度查询接口：temperature_2m
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=precipitation_probability,precipitation,temperature_2m"
        f"&timezone=Asia/Shanghai"
    )
    
    # --- 1. 架构设计：工具内部的局部重试机制 ---
    max_attempts = 3
    response = None
    
    for attempt in range(max_attempts):
        try:
            # 5秒超时
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                break  # 请求成功，跳出重试循环
        except requests.exceptions.RequestException as e:
            # 如果是最后一次尝试也失败了，直接抛出友好错误
            if attempt == max_attempts - 1:
                return f"工具异常：天气接口连接失败，已尝试重试{max_attempts}次，原因: {str(e)}"
            # 否则等待 1 秒后重试
            time.sleep(1)
            
    if not response or response.status_code != 200:
        return f"工具异常：天气服务器返回了非正常状态码: {response.status_code if response else 'None'}"
        
    # --- 2. 解析天气序列数据 ---
    data = response.json()
    hourly_data = data.get("hourly", {})
    
    times = hourly_data.get("time", [])
    probabilities = hourly_data.get("precipitation_probability", [])
    precipitations = hourly_data.get("precipitation", [])
    temperatures = hourly_data.get("temperature_2m", [])
    
    if not times:
        return "工具异常：气象接口返回的数据结构不完整。"
        
    # --- 3. 分析未来 3 小时内的即时降水 ---
    next_3_hours_rain = False
    max_prob_3_hours = 0
    
    for i in range(3):
        if i < len(probabilities):
            prob = probabilities[i]
            max_prob_3_hours = max(max_prob_3_hours, prob)
            # 降水概率达到30%或有实际雨量，即判定为有下雨风险
            if prob >= 30 or precipitations[i] > 0.1:
                next_3_hours_rain = True
                
    # --- 4. 计算未来 12 小时的降水持续时间与首次降雨时间 ---
    rain_duration = 0
    rain_start_index = -1
    
    for i in range(12):
        if i < len(probabilities):
            if probabilities[i] >= 30:
                rain_duration += 1
                if rain_start_index == -1:
                    rain_start_index = i
                    
    # --- 5. 获取未来 12 小时的温度数据并提供建议 ---
    temp_12h = temperatures[:12] if temperatures else []
    current_temp = temp_12h[0] if temp_12h else 25.0
    min_temp = min(temp_12h) if temp_12h else 20.0
    max_temp = max(temp_12h) if temp_12h else 30.0
    temp_diff = max_temp - min_temp
    
    # --- 6. 构造人性化的分析报告 ---
    current_time_str = datetime.now().strftime("%H:%M")
    analysis = f"【武汉大学（珞珈山）专属气象分析（更新于 {current_time_str}）】\n\n"
    
    # 降水与带伞提醒逻辑
    if next_3_hours_rain:
        analysis += (
            f"⚠️ 降水提醒：**未来 3 小时内有明显的降雨风险！** 最大下雨概率达 {max_prob_3_hours}%。\n"
            f"💡 **请千万记得带伞！** 如果有户外出行计划，建议暂缓或调整为室内活动。\n\n"
        )
    else:
        analysis += f"✅ 降水提醒：未来 3 小时内天气相对安全，降雨概率较低。\n"
        if rain_duration > 0:
            analysis += f"💡 提示：虽然近3小时无雨，但后续时段有降雨预警，**建议出门仍随身携带便携雨伞以防万一**。\n\n"
        else:
            analysis += f"💡 提示：未来半天无降雨风险，出门无需带伞，可以尽情享受校园生活。\n\n"
            
    # 下雨时间段与持续时间检测
    if rain_duration > 0:
        raw_start_time = times[rain_start_index]
        formatted_start_time = format_forecast_time(raw_start_time)
        analysis += f"🌧️ 持续时间预测：未来 12 小时内，预计会累计出现约 {rain_duration} 个小时的降水。降雨预计最快会于 **{formatted_start_time}** 左右开始，请注意防范。\n\n"
    else:
        analysis += f"☀️ 持续时间预测：未来 12 小时内武大校区无连续降雨时段，非常适合去九一二操场或者教五大草坪散步。\n\n"
        
    # 温度与穿衣防晒建议
    analysis += f"🌡️ 温度与穿衣提示：当前气温为 {current_temp:.1f}℃。\n"
    analysis += f"未来 12 小时内最低气温 {min_temp:.1f}℃，最高气温 {max_temp:.1f}℃（昼夜温差约 {temp_diff:.1f}℃）。\n"
    
    if temp_diff >= 8.0:
        analysis += "👚 穿衣建议：武大今天温差较大，早晚偏凉，建议采用洋葱式穿衣法（内里短袖/衬衫，外搭一件轻薄外套），方便根据气温增减。\n"
    elif max_temp >= 30.0:
        analysis += "🌞 防晒建议：天气较热，紫外线较强，出门请注意涂抹防晒霜，并在包里备好防晒帽或晴雨伞。\n"
    else:
        analysis += "🧥 穿衣建议：温度适宜，穿着普通的春秋装（如长袖T恤、卫衣、牛仔裤）即可舒适出行。\n"
        
    return analysis


# ==========================================
# 本地测试入口
# ==========================================
if __name__ == "__main__":
    print("开始获取武汉大学精准天气降雨分析...")
    report = get_whu_rain_forecast.invoke({})
    print(report)